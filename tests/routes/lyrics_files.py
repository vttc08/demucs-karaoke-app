from .common import *



def test_media_file_served_from_media_mount(client):
    """Test files under configured media path are served by app mount."""
    media_file = Path(settings.media_path) / "test-media-file.txt"
    media_file.write_text("ok", encoding="utf-8")
    try:
        response = client.get("/media/test-media-file.txt")
        assert response.status_code == 200
        assert response.text == "ok"
    finally:
        if media_file.exists():
            media_file.unlink()

def test_cache_file_served_from_cache_route(client):
    """Test files under configured cache path are served by /cache route."""
    cache_file = Path(settings.cache_path) / "test-cache-file.txt"
    cache_file.write_text("ok-cache", encoding="utf-8")
    try:
        response = client.get("/cache/test-cache-file.txt")
        assert response.status_code == 200
        assert response.text == "ok-cache"
    finally:
        if cache_file.exists():
            cache_file.unlink()

def test_get_queue_item_lyrics_cues_from_lrc(client):
    """Lyrics cues endpoint should parse LRC sidecar files."""
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "lyric-lrc-1", "title": "Lyric LRC", "is_karaoke": False},
    ).json()

    lyrics_file = Path(settings.media_path) / "route-lyrics.lrc"
    lyrics_file.write_text("[00:00.00]Line one\n[00:03.00]Line two\n", encoding="utf-8")

    db = TestingSessionLocal()
    try:
        row = db.query(QueueItem).filter(QueueItem.id == created["id"]).first()
        assert row is not None
        assert row.media is not None
        row.media.lyrics_path = "/media/route-lyrics.lrc"
        db.commit()
    finally:
        db.close()

    try:
        response = client.get(f"/api/queue/{created['id']}/lyrics-cues")
        assert response.status_code == 200
        payload = response.json()
        assert payload["item_id"] == created["id"]
        assert payload["source_format"] == "lrc"
        assert payload["is_synced"] is True
        assert payload["cues"][0] == {"time": 0.0, "text": "Line one"}
        assert payload["cues"][1] == {"time": 3.0, "text": "Line two"}
        assert payload["lines"] == ["Line one", "Line two"]
    finally:
        if lyrics_file.exists():
            lyrics_file.unlink()

def test_get_queue_item_lyrics_cues_from_json(client):
    """Lyrics cues endpoint should read JSON sidecar files."""
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "lyric-json-1", "title": "Lyric JSON", "is_karaoke": False},
    ).json()

    lyrics_file = Path(settings.cache_path) / "route-lyrics.json"
    lyrics_file.write_text(
        '{"cues":[{"start":4.0,"line":"Fourth"},{"time":1.5,"text":"First"}]}',
        encoding="utf-8",
    )

    db = TestingSessionLocal()
    try:
        row = db.query(QueueItem).filter(QueueItem.id == created["id"]).first()
        assert row is not None
        assert row.media is not None
        row.media.lyrics_path = "/cache/route-lyrics.json"
        db.commit()
    finally:
        db.close()

    try:
        response = client.get(f"/api/queue/{created['id']}/lyrics-cues")
        assert response.status_code == 200
        payload = response.json()
        assert payload["source_format"] == "json"
        assert payload["is_synced"] is True
        assert payload["cues"] == [
            {"time": 1.5, "text": "First"},
            {"time": 4.0, "text": "Fourth"},
        ]
        assert payload["lines"] == ["First", "Fourth"]
    finally:
        if lyrics_file.exists():
            lyrics_file.unlink()

def test_get_queue_item_lyrics_cues_from_aligned_json_segments(client):
    """Lyrics cues endpoint should normalize aligned segment JSON into line cues."""
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "lyric-segments-1", "title": "Lyric Segments", "is_karaoke": False},
    ).json()

    lyrics_file = Path(settings.cache_path) / "route-aligned-lyrics.json"
    lyrics_file.write_text(
        json.dumps(
            {
                "segments": [
                    {
                        "start": 2.5,
                        "end": 4.0,
                        "text": "Hello world",
                        "words": [
                            {"word": "Hello", "start": 2.5, "end": 3.0},
                            {"word": "world", "start": 3.0, "end": 4.0},
                        ],
                    },
                    {
                        "start": 5.25,
                        "end": 6.25,
                        "words": [
                            {"word": "Second", "start": 5.25, "end": 5.75},
                            {"word": "line", "start": 5.75, "end": 6.25},
                        ],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    db = TestingSessionLocal()
    try:
        row = db.query(QueueItem).filter(QueueItem.id == created["id"]).first()
        assert row is not None
        assert row.media is not None
        row.media.lyrics_path = "/cache/route-aligned-lyrics.json"
        db.commit()
    finally:
        db.close()

    try:
        response = client.get(f"/api/queue/{created['id']}/lyrics-cues")
        assert response.status_code == 200
        payload = response.json()
        assert payload["source_format"] == "json"
        assert payload["is_synced"] is True
        assert payload["cues"] == [
            {
                "time": 2.5,
                "end": 4.0,
                "text": "Hello world",
                "words": [
                    {"word": "Hello", "start": 2.5, "end": 3.0},
                    {"word": "world", "start": 3.0, "end": 4.0},
                ],
            },
            {
                "time": 5.25,
                "end": 6.25,
                "text": "Second line",
                "words": [
                    {"word": "Second", "start": 5.25, "end": 5.75},
                    {"word": "line", "start": 5.75, "end": 6.25},
                ],
            },
        ]
        assert payload["lines"] == ["Hello world", "Second line"]
    finally:
        if lyrics_file.exists():
            lyrics_file.unlink()

def test_get_queue_item_lyrics_cues_from_txt(client):
    """Lyrics cues endpoint should expose plain text lyrics as unsynced lines."""
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "lyric-txt-1", "title": "Lyric TXT", "is_karaoke": False},
    ).json()

    lyrics_file = Path(settings.media_path) / "route-lyrics.txt"
    lyrics_file.write_text("Line one\n\nLine two\n", encoding="utf-8")

    db = TestingSessionLocal()
    try:
        row = db.query(QueueItem).filter(QueueItem.id == created["id"]).first()
        assert row is not None
        assert row.media is not None
        row.media.lyrics_path = "/media/route-lyrics.txt"
        db.commit()
    finally:
        db.close()

    try:
        response = client.get(f"/api/queue/{created['id']}/lyrics-cues")
        assert response.status_code == 200
        payload = response.json()
        assert payload["source_format"] == "txt"
        assert payload["is_synced"] is False
        assert payload["cues"] == []
        assert payload["lines"] == ["Line one", "Line two"]
    finally:
        if lyrics_file.exists():
            lyrics_file.unlink()

def test_transform_chinese_lyrics_endpoint_simplifies_and_pinyinizes(client):
    """Chinese lyrics transform endpoint should simplify Chinese and add optional pinyin."""
    response = client.post(
        "/api/lyrics/chinese-transform",
        json={
            "texts": ["繁體中文", "Hello 世界", "Plain English"],
            "include_pinyin": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["items"][0] == {
        "original": "繁體中文",
        "simplified": "繁体中文",
        "pinyin": "fan ti zhong wen",
        "has_chinese": True,
    }
    assert payload["items"][1] == {
        "original": "Hello 世界",
        "simplified": "Hello 世界",
        "pinyin": "Hello shi jie",
        "has_chinese": True,
    }
    assert payload["items"][2] == {
        "original": "Plain English",
        "simplified": "Plain English",
        "pinyin": None,
        "has_chinese": False,
    }

def test_get_queue_item_lyrics_cues_returns_404_without_lyrics(client):
    """Lyrics cues endpoint should return 404 when no lyrics sidecar exists."""
    created = client.post(
        "/api/queue/",
        json={"youtube_id": "lyric-none-1", "title": "Lyric None", "is_karaoke": False},
    ).json()

    response = client.get(f"/api/queue/{created['id']}/lyrics-cues")
    assert response.status_code == 404
    assert "Lyrics not available" in response.json()["detail"]
