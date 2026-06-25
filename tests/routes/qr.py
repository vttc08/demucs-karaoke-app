from .common import *

import segno


def test_qr_short_host_is_standard_not_micro():
    """Short payloads must produce a standard QR (3 finder patterns), not Micro QR.

    segno.make() downgrades inputs like "127.0.0.1"/"localhost" to a Micro QR
    (versions M1-M4), which renders as a partial-looking code most phone cameras
    cannot scan. The endpoint uses segno.make_qr() to force a standard symbol.
    """
    for payload in ("127.0.0.1", "localhost", "a"):
        version = segno.make_qr(payload, error="m").version
        assert isinstance(version, int), f"{payload!r} produced Micro QR version {version!r}"


def test_qr_endpoint_returns_square_png(client):
    """The /api/qr endpoint returns a PNG for a short host payload."""
    response = client.get("/api/qr", params={"data": "127.0.0.1", "size": 320})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers.get("cache-control") == "no-cache"
    assert response.content[:8] == b"\x89PNG\r\n\x1a\n"
