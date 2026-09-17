from .common import *

from io import BytesIO

import segno


def _render_expected_standard_qr(data: str, size: int) -> bytes:
    qr = segno.make_qr(data, error="m")
    module_width, _ = qr.symbol_size()
    scale = min(max(1, size // max(module_width, 1)), 32)
    buffer = BytesIO()
    qr.save(
        buffer,
        kind="png",
        scale=scale,
        border=2,
        dark="#000000",
        light="#ffffff",
    )
    return buffer.getvalue()


def test_qr_endpoint_returns_standard_qr_png_for_short_payload(client):
    """Short payloads should remain standard QR codes, not Micro QR codes."""
    data = "localhost"
    size = 256

    assert segno.make(data, error="m").is_micro is True

    response = client.get("/api/qr", params={"data": data, "size": size})

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == _render_expected_standard_qr(data, size)
