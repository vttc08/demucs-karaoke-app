from .common import *



def test_youtube_service_search(mock_ytdlp):
    """Test YouTube search service."""
    # Mock yt-dlp search results
    mock_instance = Mock()
    mock_instance.search.return_value = [
        {
            "video_id": "test123",
            "title": "Test Video",
            "channel": "Test Channel",
            "duration": "3:45",
            "thumbnail": "http://example.com/thumb.jpg",
        }
    ]
    mock_ytdlp.return_value = mock_instance

    service = YouTubeService()
    results = service.search("test query")

    assert len(results) == 1
    assert results[0].video_id == "test123"
    assert results[0].title == "Test Video"
    assert results[0].thumbnail == "http://example.com/thumb.jpg"

def test_youtube_service_search_uses_thumbnail_fallback(mock_ytdlp):
    """Search should derive thumbnail URL when missing from yt-dlp output."""
    mock_instance = Mock()
    mock_instance.search.return_value = [
        {
            "video_id": "abc123",
            "title": "Video Without Thumbnail",
            "channel": "Channel Name",
            "duration": "4:00",
            "thumbnail": None,
        }
    ]
    mock_ytdlp.return_value = mock_instance

    service = YouTubeService()
    results = service.search("test query")

    assert len(results) == 1
    assert results[0].video_id == "abc123"
    assert (
        results[0].thumbnail
        == "https://i.ytimg.com/vi/abc123/hqdefault.jpg"
    )

def test_youtube_service_search_marks_downloaded_results(mock_ytdlp, db_session):
    """Search results should be flagged when the video already exists locally."""
    mock_instance = Mock()
    mock_instance.search.return_value = [
        {
            "video_id": "saved123",
            "title": "Already Saved",
            "channel": "Library",
            "duration": "2:00",
            "thumbnail": None,
        }
    ]
    mock_ytdlp.return_value = mock_instance
    db_session.add(
        MediaItem(
            youtube_id="saved123",
            title="Already Saved",
            artist="Library",
            media_path="/media/saved123.mp4",
            missing=False,
        )
    )
    db_session.commit()

    service = YouTubeService()
    results = service.search("totally-unrelated-query", db=db_session)

    assert len(results) == 1
    assert results[0].downloaded is True
    assert results[0].thumbnail == "https://i.ytimg.com/vi/saved123/hqdefault.jpg"
    assert results[0].source == "youtube"

def test_youtube_service_search_prefers_local_and_hides_youtube_duplicates(
    mock_ytdlp, db_session
):
    """Local DB matches should be ordered first and suppress duplicate YouTube hits."""
    local_media = MediaItem(
        youtube_id="dup123",
        title="Bohemian Rhapsody",
        artist="Queen",
        media_path="/media/dup123.mp4",
        missing=False,
    )
    db_session.add(local_media)
    db_session.commit()

    mock_instance = Mock()
    mock_instance.search.return_value = [
        {
            "video_id": "dup123",
            "title": "Bohemian Rhapsody",
            "channel": "Queen Official",
            "duration": "5:55",
            "thumbnail": None,
        },
        {
            "video_id": "yt999",
            "title": "Another Song",
            "channel": "Other Channel",
            "duration": "3:00",
            "thumbnail": None,
        },
    ]
    mock_ytdlp.return_value = mock_instance

    service = YouTubeService()
    results = service.search("bohemian queen", db=db_session)

    assert len(results) == 2
    assert results[0].source == "local"
    assert results[0].media_item_id == local_media.id
    assert results[0].video_id == "dup123"
    assert results[1].source == "youtube"
    assert results[1].video_id == "yt999"

def test_youtube_service_search_returns_local_items_without_youtube_id(
    mock_ytdlp, db_session
):
    """Local results should still be searchable/queueable when youtube_id is null."""
    db_session.add(
        MediaItem(
            youtube_id=None,
            title="Custom Local Track",
            artist="Home Rip",
            media_path="/media/custom-local-track.mp4",
            missing=False,
        )
    )
    db_session.commit()

    mock_instance = Mock()
    mock_instance.search.return_value = []
    mock_ytdlp.return_value = mock_instance

    service = YouTubeService()
    results = service.search("custom local", db=db_session)

    assert len(results) == 1
    assert results[0].source == "local"
    assert results[0].media_item_id is not None
    assert results[0].video_id is None

def test_youtube_service_search_detects_youtube_url(mock_ytdlp):
    """YouTube URL query should resolve via single-video metadata fetch."""
    mock_instance = Mock()
    mock_instance.get_video_info.return_value = {
        "video_id": "dQw4w9WgXcQ",
        "title": "Never Gonna Give You Up",
        "channel": "RickAstleyVEVO",
        "duration": "3:33",
        "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
    }
    mock_ytdlp.return_value = mock_instance

    service = YouTubeService()
    results = service.search("https://youtu.be/dQw4w9WgXcQ")

    assert len(results) == 1
    assert results[0].video_id == "dQw4w9WgXcQ"
    mock_instance.get_video_info.assert_called_once()
    mock_instance.search.assert_not_called()

def test_youtube_service_search_detects_raw_youtube_id(mock_ytdlp):
    """11-char YouTube IDs should be treated as direct video input."""
    mock_instance = Mock()
    mock_instance.get_video_info.return_value = {
        "video_id": "dQw4w9WgXcQ",
        "title": "Direct ID",
        "channel": "Channel",
        "duration": "1:00",
        "thumbnail": None,
    }
    mock_ytdlp.return_value = mock_instance

    service = YouTubeService()
    results = service.search("dQw4w9WgXcQ")

    assert len(results) == 1
    assert results[0].video_id == "dQw4w9WgXcQ"
    called_url = mock_instance.get_video_info.call_args[0][0]
    assert called_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    mock_instance.search.assert_not_called()

def test_youtube_service_search_can_disable_concurrent_karaoke_search(mock_ytdlp):
    """Search should fall back to a single plain YouTube query when concurrency is disabled."""
    mock_instance = Mock()
    mock_instance.search.return_value = [
        {
            "video_id": "plain123",
            "title": "Plain Result",
            "channel": "Channel",
            "duration": "3:00",
            "thumbnail": None,
        }
    ]
    mock_ytdlp.return_value = mock_instance

    service = YouTubeService()
    results = service.search("test query", concurrent=False)

    assert len(results) == 1
    assert results[0].video_id == "plain123"
    mock_instance.search.assert_called_once_with("test query", 10)

def test_youtube_service_download_video_with_audio(mock_ytdlp):
    """Test progressive video+audio download delegation."""
    mock_instance = Mock()
    mock_path = Path("/tmp/karaoke_media/test123.mp4")
    mock_instance.download_video_with_audio.return_value = mock_path
    mock_ytdlp.return_value = mock_instance

    service = YouTubeService()
    result = service.download_video_with_audio("test123")

    assert result == mock_path
    mock_instance.download_video_with_audio.assert_called_once()

def test_youtube_service_uses_latest_media_path_setting(mock_ytdlp, tmp_path):
    """YouTube service should honor runtime media_path changes."""
    mock_instance = Mock()
    mock_instance.download_video_with_audio.return_value = tmp_path / "v.mp4"
    mock_ytdlp.return_value = mock_instance

    original_media = settings.media_path
    try:
        settings.media_path = tmp_path / "media-now"
        service = YouTubeService()
        service.download_video_with_audio("id123")
        called_output_dir = mock_instance.download_video_with_audio.call_args[0][1]
        assert called_output_dir == settings.media_path
    finally:
        settings.media_path = original_media

def test_youtube_service_search_concurrent_staggered_when_enabled(mock_ytdlp):
    """Concurrent mode should stagger normal and karaoke-appended results."""
    original_enabled = settings.concurrent_ytdlp_search_enabled
    settings.concurrent_ytdlp_search_enabled = True
    mock_instance = Mock()
    mock_instance.search.side_effect = [
        [
            {"video_id": "n1", "title": "Normal 1", "channel": "C", "thumbnail": "t1"},
            {"video_id": "n2", "title": "Normal 2", "channel": "C", "thumbnail": "t2"},
        ],
        [
            {"video_id": "k1", "title": "Karaoke 1", "channel": "C", "thumbnail": "t3"},
            {"video_id": "k2", "title": "Karaoke 2", "channel": "C", "thumbnail": "t4"},
        ],
    ]
    mock_ytdlp.return_value = mock_instance
    try:
        service = YouTubeService()
        results = service.search("queen bohemian", max_results=4)
    finally:
        settings.concurrent_ytdlp_search_enabled = original_enabled
    assert [r.video_id for r in results] == ["n1", "k1", "n2", "k2"]
    assert mock_instance.search.call_count == 2

def test_youtube_service_search_single_when_query_has_karaoke(mock_ytdlp):
    """Concurrent mode should bypass when query already contains karaoke."""
    original_enabled = settings.concurrent_ytdlp_search_enabled
    settings.concurrent_ytdlp_search_enabled = True
    mock_instance = Mock()
    mock_instance.search.return_value = [
        {"video_id": "a1", "title": "Result", "channel": "C", "thumbnail": "t1"}
    ]
    mock_ytdlp.return_value = mock_instance
    try:
        service = YouTubeService()
        results = service.search("queen karaoke", max_results=5)
    finally:
        settings.concurrent_ytdlp_search_enabled = original_enabled
    assert [r.video_id for r in results] == ["a1"]
    assert mock_instance.search.call_count == 1

def test_youtube_service_search_single_when_feature_disabled(mock_ytdlp):
    """Feature disabled should keep single-search behavior."""
    original_enabled = settings.concurrent_ytdlp_search_enabled
    settings.concurrent_ytdlp_search_enabled = False
    mock_instance = Mock()
    mock_instance.search.return_value = [
        {"video_id": "a1", "title": "Result", "channel": "C", "thumbnail": "t1"}
    ]
    mock_ytdlp.return_value = mock_instance
    try:
        service = YouTubeService()
        service.search("queen bohemian", max_results=5)
    finally:
        settings.concurrent_ytdlp_search_enabled = original_enabled
    assert mock_instance.search.call_count == 1

def test_youtube_service_search_concurrent_dedupes_video_ids(mock_ytdlp):
    """Interleaved concurrent results should dedupe repeated video ids."""
    original_enabled = settings.concurrent_ytdlp_search_enabled
    settings.concurrent_ytdlp_search_enabled = True
    mock_instance = Mock()
    mock_instance.search.side_effect = [
        [
            {"video_id": "same", "title": "Normal", "channel": "C", "thumbnail": "t1"},
            {"video_id": "n2", "title": "Normal 2", "channel": "C", "thumbnail": "t2"},
        ],
        [
            {"video_id": "same", "title": "Karaoke", "channel": "C", "thumbnail": "t3"},
            {"video_id": "k2", "title": "Karaoke 2", "channel": "C", "thumbnail": "t4"},
        ],
    ]
    mock_ytdlp.return_value = mock_instance
    try:
        service = YouTubeService()
        results = service.search("query", max_results=10)
    finally:
        settings.concurrent_ytdlp_search_enabled = original_enabled
    assert [r.video_id for r in results] == ["same", "n2", "k2"]
