from .common import *



def test_get_empty_queue(client):
    """Test getting empty queue."""
    response = client.get("/api/queue/")
    assert response.status_code == 200
    assert response.json() == []

def test_get_queue_with_items(client):
    """Test getting queue with items."""
    # Add items
    client.post(
        "/api/queue/",
        json={
            "youtube_id": "test1",
            "title": "Song 1",
            "is_karaoke": False,
        },
    )
    client.post(
        "/api/queue/",
        json={
            "youtube_id": "test2",
            "title": "Song 2",
            "is_karaoke": True,
        },
    )

    # Get queue
    response = client.get("/api/queue/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["title"] == "Song 1"
    assert data[1]["title"] == "Song 2"

def test_get_current_item_empty(client):
    """Test getting current item when queue is empty."""
    response = client.get("/api/queue/current")
    assert response.status_code == 200
    assert response.json() is None

def test_get_next_item_empty(client):
    """Test getting next item when queue is empty."""
    response = client.get("/api/queue/next")
    assert response.status_code == 200
    assert response.json() is None

def test_queue_page_loads(client):
    """Test queue page renders."""
    response = client.get("/queue")
    assert response.status_code == 200
    assert b"Karaoke Queue" in response.content
    assert b'id="queue-singer-name"' in response.content
    assert b'id="singer-name-modal"' in response.content
    assert b"queue-config-modal" in response.content
    assert b"Configure Queue" in response.content
    assert b"queue-toast" in response.content
    assert b"queue-config-lyrics-detail" in response.content
    assert b"flex-none shrink-0" in response.content
    assert 'id="stage-remote-vocals-toggle-btn"' in response.text
    assert 'id="stage-remote-vocals-volume-slider"' in response.text
    assert 'id="stage-remote-vocals-volume-label"' in response.text
    assert 'id="stage-remote-lyrics-toggle-btn"' in response.text
    assert 'id="stage-remote-seek-forward-btn"' in response.text
    assert 'id="qr-toggle-btn"' not in response.text
    assert 'id="queue-library-shortcuts"' in response.text
    assert 'href="/media"' in response.text
    assert 'href="/upload"' in response.text
    assert 'href="/queue/lyrics"' in response.text
    assert response.text.index('id="search-input"') < response.text.index('id="stage-remote-play-pause-btn"')
    assert 'id="queue-as-settings-panel"' not in response.text
    assert 'id="queue-config-queue-as-panel"' not in response.text
    assert 'id="clear-all-btn"' not in response.text
    assert "queue-move-up-" not in response.text
    assert "skipToSong(" not in response.text
    assert 'aria-label="Settings"' not in response.text
    assert 'aria-label="Stage"' not in response.text
    assert 'aria-label="Upload"' not in response.text
    assert "shield_person" not in response.text

def test_queue_lyrics_page_loads(client):
    """Queue lyrics page should render the lyrics viewer shell."""
    response = client.get("/queue/lyrics")

    assert response.status_code == 200
    assert "Lyrics Viewer" in response.text
    assert 'id="lyrics-scroll-container"' in response.text
    assert 'id="queue-lyrics-chinese-toggle"' in response.text
    assert 'id="queue-lyrics-pinyin-toggle"' in response.text
    assert "/static/queue_lyrics.js" in response.text
    assert 'href="/queue"' in response.text

def test_queue_page_admin_shows_queue_as_controls(client):
    """Admin queue page should expose queue-as device controls and modal."""
    authenticate_admin_client(client)

    response = client.get("/queue")

    assert response.status_code == 200
    assert 'id="queue-as-settings-panel"' in response.text
    assert 'id="queue-as-enabled-toggle"' in response.text
    assert 'id="queue-as-modal"' in response.text
    assert 'id="queue-config-queue-as-panel"' in response.text
    assert response.text.index('href="/queue/lyrics"') < response.text.index('id="queue-as-settings-panel"')
    assert response.text.index('id="queue-as-settings-panel"') < response.text.index('id="search-results"')

def test_queue_page_renders_simplified_chinese_locale(client):
    """Queue page should use the selected frontend locale cookie."""
    response = client.get("/queue", cookies={LOCALE_COOKIE: "zh-CN"})

    assert response.status_code == 200
    assert '<html class="dark" lang="zh-CN">' in response.text
    assert "卡拉 OK 队列" in response.text
    assert "搜索本地媒体库和 YouTube" in response.text
    assert 'id="language-select"' in response.text

def test_queue_page_renders_requester_label(client):
    """Queue page should render requester labels without template errors."""
    client.cookies.set("karaoke_singer", "Alex")
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "queue-ui-requester", "title": "Requester UI", "is_karaoke": False},
    )
    assert created.status_code == 200

    response = client.get("/queue")

    assert response.status_code == 200
    assert "Requested by Alex" in response.text

def test_queue_page_hides_left_controls_for_guests(client):
    """Guest queue cards should not render the left-side action column."""
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-left", "title": "Guest Left", "is_karaoke": False},
    ).json()

    db = TestingSessionLocal()
    try:
        row = db.query(QueueItem).filter(QueueItem.id == created["id"]).first()
        row.status = QueueStatus.PLAYING
        db.commit()
    finally:
        db.close()

    response = client.get("/queue")

    assert response.status_code == 200
    assert "queue-move-up-" not in response.text
    assert "queue-move-down-" not in response.text
    assert "equalizer" not in response.text

def test_queue_page_shows_guest_remove_only_for_owned_items(client):
    """Guest queue page should render remove only for owned non-playing items."""
    client.cookies.set("karaoke_guest_id", "guest-owner")
    owned = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-own-remove", "title": "Guest Owned", "is_karaoke": False},
    ).json()

    client.cookies.set("karaoke_guest_id", "guest-other")
    other = client.post(
        "/api/queue/",
        json={"youtube_id": "guest-other-remove", "title": "Guest Other", "is_karaoke": False},
    ).json()

    client.cookies.set("karaoke_guest_id", "guest-owner")
    response = client.get("/queue")

    assert response.status_code == 200
    assert f'onclick="removeSong(\'{owned["id"]}\')"' in response.text
    assert f'onclick="removeSong(\'{other["id"]}\')"' not in response.text

def test_queue_page_uses_dash_in_default_guest_name(client):
    """Default generated guest names should not contain spaces."""
    response = client.get("/queue")

    assert response.status_code == 200
    assert "`${window.KaraokeI18n?.t('common.guest') || 'Guest'}-${Math.floor(1000 + Math.random() * 9000)}`" in response.text

def test_language_route_sets_cookie_and_redirects_locally(client):
    """Language selection should persist in a cookie and return to the requested page."""
    response = client.post(
        "/language",
        data={"language": "zh-CN", "next": "/media"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/media"
    assert response.cookies.get(LOCALE_COOKIE) == "zh-CN"

def test_language_route_rejects_external_redirect_targets(client):
    """Language route should not redirect to external URLs."""
    response = client.post(
        "/language",
        data={"language": "zh-CN", "next": "https://example.com/phish"},
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/queue"

def test_locale_catalogs_have_matching_keys():
    """Every supported locale should expose the same UI translation keys."""
    locale_dir = Path("locales")
    english_keys = set(json.loads((locale_dir / "en.json").read_text(encoding="utf-8")))
    chinese_keys = set(json.loads((locale_dir / "zh-CN.json").read_text(encoding="utf-8")))

    assert chinese_keys == english_keys

def test_queue_page_shows_admin_queue_controls(client):
    """Admin queue page should show destructive queue controls."""
    authenticate_admin_client(client)
    client.post(
        "/api/queue/",
        json={"youtube_id": "admin-ui-del", "title": "Admin UI Delete", "is_karaoke": False},
    )

    response = client.get("/queue")

    assert response.status_code == 200
    assert 'id="clear-all-btn"' in response.text
    assert 'onclick="removeSong(\'' in response.text
    assert response.text.count('onclick="removeSong(\'') == 1
    assert "queue-move-up-" in response.text
    assert "queue-move-down-" in response.text
    assert "skipToSong(" not in response.text
    assert 'aria-label="Stage"' in response.text
    assert 'aria-label="Settings"' in response.text
    assert 'aria-label="Media"' in response.text
    assert 'aria-label="Upload"' not in response.text

def test_stage_page_requires_admin(client):
    """Guest users should be redirected away from the stage page."""
    response = client.get("/stage", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"

def test_stage_page_loads_for_admin(client):
    """Test stage page renders for a valid admin session."""
    authenticate_admin_client(client)
    with patch(
        "routes.pages.stage_lobby_service.resolve_lobby_media_url",
        return_value="/media/stage-lobby-fallback.mp4",
    ):
        response = client.get("/stage")
    assert response.status_code == 200
    assert b"Stage" in response.content
    assert b"Now Playing" in response.content
    assert b'id="stage-video-player"' in response.content
    assert b'stage-control-cluster--transport' in response.content
    assert b'stage-control-label' in response.content
    assert b'id="stage-playbar-slider"' in response.content
    assert b'stage-vocals-volume-slider' in response.content
    assert b'stage-fullscreen-button' in response.content
    assert b'id="stage-shortcuts-btn"' in response.content
    assert b'id="stage-shortcuts-panel"' in response.content
    assert re.search(rb'id="stage-lyrics-overlay"[^>]*class="[^"]*\bhidden\b', response.content)
    assert b"stage-lyric-word--highlighted" in response.content
    assert b"findActiveLyricWordIndex" in response.content
    assert b'aria-label="Fullscreen"' in response.content

def test_stage_page_renders_audio_mode_for_current_mp3(client, tmp_path):
    """Stage page should bootstrap audio-mode playback for current MP3 items."""
    original_media = settings.media_path
    original_cache = settings.cache_path
    authenticate_admin_client(client)
    try:
        settings.media_path = tmp_path / "media"
        settings.cache_path = tmp_path / "cache"
        settings.media_path.mkdir(parents=True, exist_ok=True)
        settings.cache_path.mkdir(parents=True, exist_ok=True)

        media_file = settings.media_path / "stage-song.mp3"
        media_file.write_bytes(b"audio")
        thumb_path = MediaThumbnailService.thumbnail_path_for_media_file(media_file)
        thumb_path.parent.mkdir(parents=True, exist_ok=True)
        thumb_path.write_bytes(b"thumb")

        with TestingSessionLocal() as db:
            media_item = MediaItem(
                title="Stage Audio",
                artist="Stage Artist",
                media_path="/media/stage-song.mp3",
                missing=False,
            )
            db.add(media_item)
            db.flush()
            db.add(
                QueueItem(
                    media_id=media_item.id,
                    position=1000,
                    requested_karaoke=False,
                    status=QueueStatus.PLAYING,
                )
            )
            db.commit()

        with patch(
            "routes.pages.stage_lobby_service.resolve_lobby_media_url",
            return_value="/media/stage-lobby-fallback.mp4",
        ):
            response = client.get("/stage")

        assert response.status_code == 200
        assert b'id="stage-audio-player"' in response.content
        assert b'id="stage-audio-hero"' in response.content
        assert MediaThumbnailService.thumbnail_url_for_media_file(media_file).encode("utf-8") in response.content
        assert re.search(
            rb'<video[^>]*id="stage-video-player"[\s\S]*?<source src="" type="video/mp4">',
            response.content,
        )
    finally:
        settings.media_path = original_media
        settings.cache_path = original_cache

def test_playback_page_is_removed(client):
    """Legacy playback page should no longer be exposed."""
    response = client.get("/playback")
    assert response.status_code == 404

def test_settings_page_requires_admin(client):
    """Settings page should redirect non-admin guests to admin login."""
    response = client.get("/settings", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"] == "/login"

def test_settings_page_loads_for_admin(client):
    """Test settings page renders for a valid admin session."""
    authenticate_admin_client(client)
    response = client.get("/settings")
    assert response.status_code == 200
    assert b"Settings" in response.content
    assert b"Admin session" in response.content
    assert b"Log out" in response.content
    assert b">Save<" in response.content
    assert b">Refresh<" in response.content
    assert b"Admin Access" not in response.content
    assert 'aria-label="Settings"' in response.text
    assert 'aria-label="Media"' in response.text
    assert 'aria-label="Upload"' not in response.text
    assert "shield_person" not in response.text

def test_admin_login_rejects_invalid_credentials(client):
    """Admin login should not grant access without valid DB credentials."""
    response = client.post(
        "/login",
        data={"type": "admin", "username": "admin", "password": "wrong-password"},
    )

    assert response.status_code == 401
    assert ADMIN_SESSION_COOKIE not in response.cookies
    assert "Invalid admin username or password" in response.text

def test_login_page_is_admin_only(client):
    """Login page should not show guest identification controls."""
    response = client.get("/login")

    assert response.status_code == 200
    assert 'id="admin-form"' in response.text
    assert 'id="guest-form"' not in response.text
    assert "Guest" not in response.text
    assert "Continue to guest queue" in response.text

def test_admin_login_sets_db_backed_session_cookie(client):
    """Valid admin login should create an HttpOnly admin session cookie."""
    with TestingSessionLocal() as db:
        AuthService().create_or_update_admin(
            db, "Admin", "correct horse battery staple"
        )

    response = client.post(
        "/login",
        data={
            "type": "admin",
            "username": "admin",
            "password": "correct horse battery staple",
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "/queue"
    assert ADMIN_SESSION_COOKIE in response.cookies
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "samesite=lax" in response.headers["set-cookie"].lower()

def test_logout_deletes_admin_session(client):
    """Logout should remove the persisted admin session."""
    service = AuthService()
    with TestingSessionLocal() as db:
        admin = service.create_or_update_admin(
            db, "admin", "correct horse battery staple"
        )
        token, _ = service.create_admin_session(db, admin)

    response = client.get(
        "/logout",
        cookies={ADMIN_SESSION_COOKIE: token},
        follow_redirects=False,
    )

    assert response.status_code == 302
    with TestingSessionLocal() as db:
        assert service.get_admin_for_session(db, token) is None

def test_access_restricted_page_loads(client):
    """Test access restricted page renders."""
    response = client.get("/access-restricted")
    assert response.status_code == 200
    assert b"Access restricted" in response.content

def test_app_startup_triggers_media_scan():
    """Application lifespan should run media library scan on startup."""
    with patch(
        "main.media_library_sync_service.scan_library",
        return_value={
            "scanned_files": 0,
            "created": 0,
            "marked_missing": 0,
            "restored": 0,
            "sidecars_updated": 0,
            "skipped_rows": 0,
        },
    ) as mock_scan:
        with TestClient(app) as startup_client:
            response = startup_client.get("/health")
            assert response.status_code == 200

    assert mock_scan.called

def test_qr_endpoint_returns_png(client):
    """QR endpoint should respond with PNG data."""
    response = client.get("/api/qr", params={"data": "stage-karaoke", "size": 256})
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert len(response.content) > 0
