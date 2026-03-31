"""QR code generation endpoint using a local library."""
from io import BytesIO

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from segno import make as make_qr

router = APIRouter(prefix="/api", tags=["qr"])

DEFAULT_SIZE = 256
MAX_SIZE = 1024
MIN_SIZE = 64
MAX_DATA_LENGTH = 1024


@router.get("/qr", response_class=StreamingResponse)
def generate_qr_code(
    data: str = Query(
        ...,
        min_length=1,
        max_length=MAX_DATA_LENGTH,
        description="Payload encoded into the QR code"
    ),
    size: int = Query(
        DEFAULT_SIZE,
        ge=MIN_SIZE,
        le=MAX_SIZE,
        description="Approximate width/height for the returned PNG (square)"
    ),
) -> StreamingResponse:
    """Return a PNG QR code for the requested data."""
    try:
        qr = make_qr(data, error="m")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    module_width, _ = qr.symbol_size()
    scale = max(1, size // max(module_width, 1))
    scale = min(scale, 32)

    buffer = BytesIO()
    qr.save(
        buffer,
        kind="png",
        scale=scale,
        border=2,
        dark="#000000",
        light="#ffffff",
    )
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="image/png")
