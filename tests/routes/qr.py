from .common import *

import io
import segno


def _expected_qr_png(data: str, size: int) -> bytes:
    """Reproduce routes.qr.generate_qr_code byte-for-byte, using make_qr.

    Mirrors the endpoint's scale/border/colour params so the bytes only match
    when the route also forces a standard QR (segno.make_qr). Reverting to
    segno.make (Micro QR) changes the output and fails the comparison.
    """
    qr = segno.make_qr(data, error="m")
    module_width, _ = qr.symbol_size()
    scale = min(max(1, size // max(module_width, 1)), 32)
    buf = io.BytesIO()
    qr.save(buf, kind="png", scale=scale, border=2, dark="#000000", light="#ffffff")
    return buf.getvalue()


def test_qr_endpoint_emits_standard_not_micro_qr(client):
    """Endpoint must serve a standard QR (matches make_qr), not a Micro QR.

    segno.make() downgrades short inputs like "127.0.0.1"/"localhost" to a Micro
    QR (one finder pattern), which renders as a partial-looking code most phone
    cameras cannot scan. Byte-equality against the make_qr reference fails if the
    route regresses to segno.make.
    """
    response = client.get("/api/qr", params={"data": "127.0.0.1", "size": 320})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers.get("cache-control") == "no-cache"
    assert response.content == _expected_qr_png("127.0.0.1", 320)
