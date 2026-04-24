import logging

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response

try:
    from .settings import REQUEST_TIMEOUT_SECONDS, UPSTREAM_DEMUCS_API_URL
except ImportError:
    from settings import REQUEST_TIMEOUT_SECONDS, UPSTREAM_DEMUCS_API_URL


app = FastAPI(title="Demucs Stub Service", version="0.1.0")
logger = logging.getLogger(__name__)

_FORWARDED_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
_HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}


def _filter_request_headers(headers) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in _HOP_BY_HOP_HEADERS
        and key.lower() not in {"host", "content-length"}
    }


def _filter_response_headers(headers) -> dict[str, str]:
    return {
        key: value
        for key, value in headers.items()
        if key.lower() not in _HOP_BY_HOP_HEADERS and key.lower() != "content-length"
    }


def _upstream_url(path: str) -> str:
    if not UPSTREAM_DEMUCS_API_URL:
        raise RuntimeError("DEMUCS_API_URL is not configured")

    suffix = path.lstrip("/")
    if not suffix:
        return UPSTREAM_DEMUCS_API_URL
    return f"{UPSTREAM_DEMUCS_API_URL}/{suffix}"


def _stub_health_payload(detail: str | None = None) -> dict[str, object]:
    return {
        "status": "healthy",
        "service": "demucs_stub",
        "detail": detail or "Upstream Demucs backend unavailable; stub health is active",
        "upstream_api_url": UPSTREAM_DEMUCS_API_URL or None,
    }


async def _forward_request(request: Request, path: str) -> Response:
    body = await request.body()
    async with httpx.AsyncClient(
        timeout=REQUEST_TIMEOUT_SECONDS,
        follow_redirects=True,
    ) as client:
        upstream_response = await client.request(
            request.method,
            _upstream_url(path),
            params=request.query_params,
            headers=_filter_request_headers(request.headers),
            content=body if body else None,
        )

    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        headers=_filter_response_headers(upstream_response.headers),
    )


@app.api_route("/health", methods=["GET", "HEAD"])
async def health(request: Request) -> Response:
    try:
        return await _forward_request(request, "health")
    except (httpx.RequestError, RuntimeError) as error:
        logger.warning(
            "Demucs stub health fallback path=%s error=%s",
            request.url.path,
            error,
        )
        if request.method == "HEAD":
            return Response(status_code=200)
        return JSONResponse(status_code=200, content=_stub_health_payload(str(error)))


@app.api_route("/{path:path}", methods=_FORWARDED_METHODS)
async def proxy(path: str, request: Request) -> Response:
    try:
        return await _forward_request(request, path)
    except (httpx.RequestError, RuntimeError) as error:
        logger.warning(
            "Demucs stub upstream unavailable method=%s path=%s error=%s",
            request.method,
            request.url.path,
            error,
        )
        raise HTTPException(
            status_code=500,
            detail="Upstream Demucs backend unavailable",
        ) from error
