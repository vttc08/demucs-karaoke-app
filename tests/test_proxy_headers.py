"""Verify the Uvicorn proxy setting used by the admin login limiter."""

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from uvicorn import Config


def test_forwarded_client_address_requires_a_trusted_proxy(monkeypatch):
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "172.23.0.0/24")
    app = FastAPI()

    @app.get("/client")
    def client_address(request: Request):
        return {"host": request.client.host, "scheme": request.url.scheme}

    server = Config(app, log_config=None)
    server.load()
    headers = {
        "X-Forwarded-For": "198.51.100.10",
        "X-Forwarded-Proto": "https",
        "X-Real-IP": "203.0.113.20",
    }

    with TestClient(server.loaded_app, client=("172.23.0.5", 50000)) as trusted:
        assert trusted.get("/client", headers=headers).json() == {
            "host": "198.51.100.10",
            "scheme": "https",
        }
        assert trusted.get("/client", headers={"X-Real-IP": "203.0.113.20"}).json() == {
            "host": "172.23.0.5",
            "scheme": "http",
        }

    with TestClient(server.loaded_app, client=("192.0.2.5", 50000)) as untrusted:
        assert untrusted.get("/client", headers=headers).json() == {
            "host": "192.0.2.5",
            "scheme": "http",
        }
