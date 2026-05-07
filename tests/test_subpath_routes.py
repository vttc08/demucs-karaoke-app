"""Tests for serving the app under a reverse-proxy subpath."""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from unittest.mock import patch

from config import settings
from database import ensure_auxiliary_schema, get_db
from services.auth_service import ADMIN_SESSION_COOKIE, AuthService
from main import create_app
from models import Base


def test_app_serves_pages_assets_api_and_websocket_under_configured_subpath(tmp_path):
    original_base_path = settings.karaoke_base_path
    original_media_path = settings.media_path
    original_cache_path = settings.cache_path
    original_database_url = settings.database_url

    db_path = tmp_path / "subpath.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    testing_session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    settings.karaoke_base_path = "/karaoke"
    settings.media_path = tmp_path / "media"
    settings.cache_path = tmp_path / "cache"
    settings.database_url = f"sqlite:///{db_path}"
    settings.media_path.mkdir()
    settings.cache_path.mkdir()
    (settings.media_path / "sample.txt").write_text("media", encoding="utf-8")
    (settings.cache_path / "sample.txt").write_text("cache", encoding="utf-8")

    Base.metadata.create_all(bind=engine)
    ensure_auxiliary_schema(engine)

    subpath_app = create_app()

    def override_get_db():
        try:
            db = testing_session_local()
            yield db
        finally:
            db.close()

    subpath_app.dependency_overrides[get_db] = override_get_db

    try:
        client = TestClient(subpath_app)

        health = client.get("/karaoke/health")
        assert health.status_code == 200
        assert health.json() == {"status": "healthy"}

        root_redirect = client.get("/karaoke/", follow_redirects=False)
        assert root_redirect.status_code == 302
        assert root_redirect.headers["location"] == "/karaoke/queue"

        assert client.get("/queue").status_code == 404

        login_page = client.get("/karaoke/login")
        assert login_page.status_code == 200
        assert 'action="/karaoke/login"' in login_page.text

        queue_page = client.get("/karaoke/queue")
        assert queue_page.status_code == 200
        queue_html = queue_page.text
        assert 'href="/karaoke/queue"' in queue_html
        assert 'href="/queue"' not in queue_html
        assert 'action="/karaoke/language"' in queue_html
        assert "/karaoke/static/app-urls.js" in queue_html
        assert "/karaoke/static/queue.js" in queue_html
        assert 'window.KARAOKE_BASE_PATH = "/karaoke";' in queue_html
        assert 'id="queue-library-shortcuts"' in queue_html
        assert 'href="/karaoke/media"' in queue_html
        assert 'href="/karaoke/upload"' in queue_html

        language_response = client.post(
            "/karaoke/language",
            data={"language": "zh-CN", "next": "/karaoke/stage"},
            follow_redirects=False,
        )
        assert language_response.status_code == 302
        assert language_response.headers["location"] == "/karaoke/stage"

        stage_redirect = client.get("/karaoke/stage", follow_redirects=False)
        assert stage_redirect.status_code == 302
        assert stage_redirect.headers["location"] == "/karaoke/login"

        service = AuthService()
        with testing_session_local() as db:
            admin = service.create_or_update_admin(
                db, "admin", "correct horse battery staple"
            )
            token, _ = service.create_admin_session(db, admin)
        client.cookies.set(ADMIN_SESSION_COOKIE, token)

        with patch(
            "routes.pages.stage_lobby_service.resolve_lobby_media_url",
            return_value="/media/stage-lobby-fallback.mp4",
        ):
            assert client.get("/karaoke/stage").status_code == 200
        assert client.get("/karaoke/settings").status_code == 200
        assert client.get("/karaoke/media").status_code == 200
        assert client.get("/karaoke/upload").status_code == 200
        assert client.get("/karaoke/static/style.css").status_code == 200
        assert client.get("/karaoke/media/sample.txt").text == "media"
        assert client.get("/karaoke/cache/sample.txt").text == "cache"
        assert client.get("/karaoke/api/queue/").status_code == 200

        with client.websocket_connect("/karaoke/api/queue/ws") as websocket:
            connected = websocket.receive_json()
            assert connected["type"] == "connected"
    finally:
        settings.karaoke_base_path = original_base_path
        settings.media_path = original_media_path
        settings.cache_path = original_cache_path
        settings.database_url = original_database_url
        Base.metadata.drop_all(bind=engine)
