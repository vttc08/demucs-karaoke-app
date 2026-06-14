from .common import *



def test_lyrics_service_default_provider_order_includes_netease_between_musixmatch_and_lrclib():
    """Default provider chain should keep NetEase between Musixmatch and LRCLib."""
    original_token = settings.musixmatch_token
    original_netease_enabled = settings.lyrics_provider_netease_enabled
    original_lrclib_enabled = settings.lyrics_provider_lrclib_enabled
    try:
        settings.musixmatch_token = "token123"
        settings.lyrics_provider_netease_enabled = True
        settings.lyrics_provider_lrclib_enabled = True
        service = LyricsService()
    finally:
        settings.musixmatch_token = original_token
        settings.lyrics_provider_netease_enabled = original_netease_enabled
        settings.lyrics_provider_lrclib_enabled = original_lrclib_enabled

    provider_names = [provider.name for provider in service.providers]
    assert provider_names == ["musixmatch", "netease", "lrclib"]

def test_lyrics_service_default_provider_order_respects_runtime_toggles():
    """Default provider list should honor runtime enable/disable toggles."""
    original_token = settings.musixmatch_token
    original_netease_enabled = settings.lyrics_provider_netease_enabled
    original_lrclib_enabled = settings.lyrics_provider_lrclib_enabled
    try:
        settings.musixmatch_token = "token123"
        settings.lyrics_provider_netease_enabled = False
        settings.lyrics_provider_lrclib_enabled = True
        service = LyricsService()
        provider_names = [provider.name for provider in service.providers]
    finally:
        settings.musixmatch_token = original_token
        settings.lyrics_provider_netease_enabled = original_netease_enabled
        settings.lyrics_provider_lrclib_enabled = original_lrclib_enabled

    assert provider_names == ["musixmatch", "lrclib"]

def test_netease_provider_prefers_cjk_candidate_and_rejects_low_confidence():
    """Candidate selector should avoid unrelated songs and pick CJK-near matches."""
    from services import lyrics_providers as lp_module
    from services import lyrics_service as ls_module

    inferred = ls_module.InferredSong(
        title="月亮惹的禍 Troubled By The Moon",
        artist="張宇 Phil Chang",
        source="lastfm",
    )

    unrelated = lp_module._NeteaseSongCandidate(
        song_id=2051231725,
        title="Üher",
        artists=["NaraBara"],
        album="Other",
        duration_ms=180000,
    )
    expected = lp_module._NeteaseSongCandidate(
        song_id=190526,
        title="月亮惹的祸",
        artists=["张宇"],
        album="月亮 太阳",
        duration_ms=262466,
    )

    selected = lp_module.NeteaseLyricsProvider._select_best_candidate(
        [unrelated, expected], inferred
    )
    assert selected is not None
    assert selected.song_id == 190526

    low_conf_only = lp_module.NeteaseLyricsProvider._select_best_candidate([unrelated], inferred)
    assert low_conf_only is None

def test_lyrics_service_parse():
    """Test lyrics parsing."""
    service = LyricsService()
    lyrics = "Line 1\nLine 2\n\nLine 3\n"

    lines = service.parse_lyrics_to_lines(lyrics)

    assert len(lines) == 3
    assert lines[0] == "Line 1"
    assert lines[1] == "Line 2"
    assert lines[2] == "Line 3"

def test_lyrics_service_parse_lrc_to_cues_with_offset_and_multi_timestamps():
    """LRC parser should support offsets and multiple timestamps per line."""
    service = LyricsService()
    lyrics = "\n".join(
        [
            "[offset:500]",
            "[00:00.00][00:02.00]Hello line",
            "[00:04.50]Next line",
        ]
    )

    cues = service.parse_lrc_to_cues(lyrics)

    assert cues == [
        {"time": 0.5, "text": "Hello line"},
        {"time": 2.5, "text": "Hello line"},
        {"time": 5.0, "text": "Next line"},
    ]

def test_lyrics_service_parse_json_to_cues_normalizes_shape():
    """JSON parser should accept alternate time/text keys and sort cues."""
    service = LyricsService()
    payload = """
    {
        "cues": [
            {"start": 5.2, "line": "Later line"},
            {"time": 1.0, "text": "First line"},
            {"timestamp": 3.4, "lyric": "Middle line"}
        ]
    }
    """

    cues = service.parse_json_to_cues(payload)

    assert cues == [
        {"time": 1.0, "text": "First line"},
        {"time": 3.4, "text": "Middle line"},
        {"time": 5.2, "text": "Later line"},
    ]

def test_lyrics_service_parse_json_to_cues_accepts_aligned_segments():
    """JSON parser should normalize WhisperX-style aligned segments into line cues."""
    service = LyricsService()
    payload = json.dumps(
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
    )

    cues = service.parse_json_to_cues(payload)

    assert cues == [
        {
            "time": 2.5,
            "text": "Hello world",
            "words": [
                {"word": "Hello", "start": 2.5, "end": 3.0},
                {"word": "world", "start": 3.0, "end": 4.0},
            ],
        },
        {
            "time": 5.25,
            "text": "Second line",
            "words": [
                {"word": "Second", "start": 5.25, "end": 5.75},
                {"word": "line", "start": 5.75, "end": 6.25},
            ],
        },
    ]

def test_lyrics_service_parse_json_to_cues_ignores_invalid_aligned_words():
    """JSON parser should keep line cues when nested word timing is unusable."""
    service = LyricsService()
    payload = json.dumps(
        [
            {
                "start": 1.0,
                "text": "Keep this line",
                "words": [
                    {"word": "Keep", "start": 1.0, "end": 1.2},
                    {"word": "missing end", "start": 1.0},
                    {"word": "backwards", "start": 2.0, "end": 1.5},
                    {"word": "", "start": 1.0, "end": 1.5},
                ],
            }
        ]
    )

    assert service.parse_json_to_cues(payload) == [
        {"time": 1.0, "text": "Keep this line"}
    ]

def test_chinese_lyrics_service_simplifies_and_adds_pinyin():
    """Chinese lyrics transformer should simplify Traditional Chinese and preserve mixed text."""
    service = ChineseLyricsService()

    items = service.transform_lines(
        [
            "繁體中文",
            "Hello 世界",
            "No Chinese here",
        ],
        include_pinyin=True,
    )

    assert items[0]["simplified"] == "繁体中文"
    assert items[0]["has_chinese"] is True
    assert items[0]["pinyin"] == "fan ti zhong wen"
    assert items[1]["simplified"] == "Hello 世界"
    assert items[1]["pinyin"] == "Hello shi jie"
    assert items[2]["simplified"] == "No Chinese here"
    assert items[2]["pinyin"] is None
