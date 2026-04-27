"""Tests for the standalone Demucs stub proxy service."""

from __future__ import annotations

import importlib
from pathlib import Path

import httpx
from fastapi.testclient import TestClient


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(REPO_ROOT))

stub_app = importlib.import_module("demucs_stub_svc.app")
stub_settings = importlib.import_module("demucs_stub_svc.settings")


def _install_async_client(monkeypatch, responder):
    seen_ctor = {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            seen_ctor["args"] = args
            seen_ctor["kwargs"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def request(self, method, url, **kwargs):
            return await responder(method, url, **kwargs)

    monkeypatch.setattr(stub_app.httpx, "AsyncClient", FakeAsyncClient)
    return seen_ctor


def test_health_returns_stub_healthy_when_upstream_unreachable(monkeypatch):
    monkeypatch.setattr(stub_app, "UPSTREAM_DEMUCS_API_URL", "http://backend:8001")
    monkeypatch.setattr(stub_app, "HEALTH_REQUEST_TIMEOUT_SECONDS", 1.5)

    async def responder(method, url, **kwargs):
        raise httpx.ConnectError("offline")

    seen_ctor = _install_async_client(monkeypatch, responder)

    client = TestClient(stub_app.app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
    assert response.json()["service"] == "demucs_stub"
    assert response.json()["upstream_api_url"] == "http://backend:8001"
    assert seen_ctor["kwargs"]["timeout"].connect == 1.5
    assert seen_ctor["kwargs"]["timeout"].read == 1.5


def test_stub_settings_prefers_explicit_upstream_url():
    config = stub_settings.StubSettings(
        upstream_demucs_api_url="http://backend:8001",
        demucs_api_url="http://localhost:8002",
    )

    assert stub_settings.get_upstream_demucs_api_url(config) == "http://backend:8001"


def test_non_health_request_returns_500_when_upstream_unreachable(monkeypatch):
    monkeypatch.setattr(stub_app, "UPSTREAM_DEMUCS_API_URL", "http://backend:8001")
    monkeypatch.setattr(stub_app, "REQUEST_CONNECT_TIMEOUT_SECONDS", 2.5)
    monkeypatch.setattr(stub_app, "REQUEST_TIMEOUT_SECONDS", 45.0)

    async def responder(method, url, **kwargs):
        raise httpx.ConnectError("offline")

    seen_ctor = _install_async_client(monkeypatch, responder)

    client = TestClient(stub_app.app)
    response = client.post(
        "/separate",
        data={"model": "htdemucs"},
        files={"file": ("input.wav", b"audio-bytes", "audio/wav")},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "Upstream Demucs backend unavailable"
    assert seen_ctor["kwargs"]["timeout"].connect == 2.5
    assert seen_ctor["kwargs"]["timeout"].read == 45.0
    assert seen_ctor["kwargs"]["timeout"].write == 45.0


def test_health_fallback_uses_exception_name_when_error_message_is_blank(monkeypatch):
    monkeypatch.setattr(stub_app, "UPSTREAM_DEMUCS_API_URL", "http://backend:8001")

    async def responder(method, url, **kwargs):
        raise httpx.ConnectTimeout("")

    _install_async_client(monkeypatch, responder)

    client = TestClient(stub_app.app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["detail"] == "ConnectTimeout"


def test_health_forwards_upstream_payload_when_available(monkeypatch):
    monkeypatch.setattr(stub_app, "UPSTREAM_DEMUCS_API_URL", "http://backend:8001")
    seen = {}

    async def responder(method, url, **kwargs):
        seen["method"] = method
        seen["url"] = url
        seen["params"] = dict(kwargs["params"])
        return httpx.Response(
            200,
            json={"status": "degraded", "detail": "gpu busy"},
            headers={"x-upstream": "1"},
        )

    _install_async_client(monkeypatch, responder)

    client = TestClient(stub_app.app)
    response = client.get("/health?source=test")

    assert response.status_code == 200
    assert response.json() == {"status": "degraded", "detail": "gpu busy"}
    assert response.headers["x-upstream"] == "1"
    assert seen == {
        "method": "GET",
        "url": "http://backend:8001/health",
        "params": {"source": "test"},
    }


def test_post_upload_is_forwarded_to_upstream(monkeypatch):
    monkeypatch.setattr(stub_app, "UPSTREAM_DEMUCS_API_URL", "http://backend:8001")
    seen = {}

    async def responder(method, url, **kwargs):
        seen["method"] = method
        seen["url"] = url
        seen["params"] = dict(kwargs["params"])
        seen["headers"] = kwargs["headers"]
        seen["content"] = kwargs["content"]
        return httpx.Response(
            200,
            content=b"zip-data",
            headers={
                "content-type": "application/zip",
                "x-job-id": "job-123",
            },
        )

    _install_async_client(monkeypatch, responder)

    client = TestClient(stub_app.app)
    response = client.post(
        "/separate?mode=zip",
        data={"model": "htdemucs"},
        files={"file": ("input.wav", b"audio-bytes", "audio/wav")},
    )

    assert response.status_code == 200
    assert response.content == b"zip-data"
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["x-job-id"] == "job-123"
    assert seen["method"] == "POST"
    assert seen["url"] == "http://backend:8001/separate"
    assert seen["params"] == {"mode": "zip"}
    assert b'audio-bytes' in seen["content"]
    assert b'name="model"' in seen["content"]
    assert "host" not in {key.lower() for key in seen["headers"]}


def test_get_download_is_forwarded_to_upstream(monkeypatch):
    monkeypatch.setattr(stub_app, "UPSTREAM_DEMUCS_API_URL", "http://backend:8001")
    seen = {}

    async def responder(method, url, **kwargs):
        seen["method"] = method
        seen["url"] = url
        seen["params"] = dict(kwargs["params"])
        return httpx.Response(
            200,
            content=b"artifact-bytes",
            headers={
                "content-type": "application/octet-stream",
                "content-disposition": 'attachment; filename="job-123.zip"',
            },
        )

    _install_async_client(monkeypatch, responder)

    client = TestClient(stub_app.app)
    response = client.get("/artifacts/job-123.zip?download=1")

    assert response.status_code == 200
    assert response.content == b"artifact-bytes"
    assert response.headers["content-disposition"] == 'attachment; filename="job-123.zip"'
    assert seen == {
        "method": "GET",
        "url": "http://backend:8001/artifacts/job-123.zip",
        "params": {"download": "1"},
    }
