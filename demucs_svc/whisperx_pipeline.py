from __future__ import annotations

import json
import logging
import gc
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

try:
    import pylrc  # type: ignore
except Exception:  # pragma: no cover - optional dependency in test environments
    pylrc = None

try:
    import srt  # type: ignore
except Exception:  # pragma: no cover - optional dependency in test environments
    srt = None

try:
    import whisperx  # type: ignore
except Exception:  # pragma: no cover - optional dependency in test environments
    whisperx = None

_TRANSCRIPTION_MODEL_CACHE: dict[tuple[str, str, str], Any] = {}
_ALIGN_MODEL_CACHE: dict[tuple[str, str], tuple[Any, dict[str, Any]]] = {}

_TOKEN_RE = re.compile(
    r"""
    [\u4e00-\u9fff]
    | [A-Za-z]+(?:['’][A-Za-z]+)*
    | \d+(?:[.,]\d+)*
    | [^\s]
    """,
    re.VERBOSE,
)
_ALIGNMENT_TOKEN_CONTENT_RE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9]")
_SRT_TIMING_RE = re.compile(
    r"(?m)^\s*\d{1,2}:\d{2}:\d{2}[,.]\d{3}\s*-->\s*"
    r"\d{1,2}:\d{2}:\d{2}[,.]\d{3}"
)
_LRC_TIMING_RE = re.compile(r"(?m)^\s*\[\d{1,3}:\d{2}(?:[.:]\d{1,3})?\]")
_SUPPORTED_LYRICS_FORMATS = {"lrc", "srt", "txt"}


@dataclass
class ParsedLyricSegment:
    text: str
    start: float
    end: float


def _normalize_compute_type(device: str, compute_type: str | None) -> str:
    if compute_type:
        return compute_type
    return "float16" if device == "cuda" else "float32"


def whisperx_available() -> bool:
    return whisperx is not None


def _normalize_language_code(language_code: str | None, *, default: str | None = None) -> str:
    value = (language_code or default or "").strip().lower()
    if not value:
        raise ValueError("language_code is required")
    return value.split("-")[0]


def _is_cjk_token(token: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in token)


def _join_display_tokens(tokens: Iterable[str]) -> str:
    token_list = [token for token in tokens if token and token.strip()]
    if not token_list:
        return ""
    if any(_is_cjk_token(token) for token in token_list):
        return "".join(token_list)
    return " ".join(token_list)


def _lyric_tokens(text: str | None) -> list[str]:
    if not text:
        return []
    return _TOKEN_RE.findall(text)


def _alignment_tokens(text: str | None) -> list[str]:
    return [token for token in _lyric_tokens(text) if _ALIGNMENT_TOKEN_CONTENT_RE.search(token)]


def _alignment_words(words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        word
        for word in words
        if _ALIGNMENT_TOKEN_CONTENT_RE.search(str(word.get("word", "")))
        and word.get("start") is not None
        and word.get("end") is not None
    ]


def _clean_token(token: str) -> str:
    return re.sub(r"[^\w']+", "", token).lower()


def _preprocess_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or ":" in stripped:
        return None
    if "-" in stripped:
        stripped = stripped.replace("-", " ")
    if "/" in stripped:
        stripped = stripped.split("/", 1)[0].strip()
    return stripped or None


def _parse_plain_text(text: str) -> list[ParsedLyricSegment]:
    lines = [_preprocess_line(line) for line in text.splitlines()]
    return [ParsedLyricSegment(text=line, start=0.0, end=0.0) for line in lines if line]


def _parse_srt(text: str) -> tuple[list[ParsedLyricSegment], bool]:
    if srt is None:
        raise RuntimeError("srt is not installed in this environment")

    segments: list[ParsedLyricSegment] = []
    for subtitle in srt.parse(text):
        lyric_text = _preprocess_line(str(subtitle.content).replace("\n", " "))
        if not lyric_text:
            continue
        segments.append(
            ParsedLyricSegment(
                text=lyric_text,
                start=float(subtitle.start.total_seconds()),
                end=float(subtitle.end.total_seconds()),
            )
        )
    return segments, bool(segments)


def _parse_lrc(text: str) -> tuple[list[ParsedLyricSegment], bool]:
    if pylrc is None:
        raise RuntimeError("pylrc is not installed in this environment")

    parsed_lines = list(pylrc.parse(text) or [])
    if not parsed_lines:
        return _parse_plain_text(text), False

    segments: list[ParsedLyricSegment] = []
    for index, line in enumerate(parsed_lines):
        lyric_text = _preprocess_line(str(getattr(line, "text", "")))
        if not lyric_text:
            continue
        start = float(getattr(line, "time", 0.0) or 0.0)
        if index + 1 < len(parsed_lines):
            next_start = float(getattr(parsed_lines[index + 1], "time", start + 5.0) or (start + 5.0))
            end = max(start, next_start)
        else:
            end = start + 5.0
        segments.append(ParsedLyricSegment(text=lyric_text, start=start, end=end))
    return segments, bool(segments)


def _parse_lyrics(text: str, lyrics_format: str | None) -> tuple[list[ParsedLyricSegment], bool]:
    normalized_format = (lyrics_format or "").strip().lower() or None
    if normalized_format == "txt":
        return _parse_plain_text(text), False

    # The notebook selected the parser from the input file suffix. For API
    # payloads, use an unambiguous timing signature when the format field and
    # the actual content disagree.
    if _SRT_TIMING_RE.search(text):
        return _parse_srt(text)
    if _LRC_TIMING_RE.search(text):
        return _parse_lrc(text)

    if normalized_format == "srt":
        return _parse_srt(text)
    if normalized_format == "lrc":
        return _parse_lrc(text)
    parsed_segments, is_synced = _parse_lrc(text)
    if parsed_segments:
        return parsed_segments, is_synced
    return _parse_plain_text(text), False


def _flatten_segments(segments: list[ParsedLyricSegment], duration: float) -> list[dict[str, Any]]:
    if not segments:
        return []
    combined_text = " ".join(segment.text for segment in segments if segment.text).strip()
    if not combined_text:
        return []
    return [{"text": combined_text, "start": 0.0, "end": duration}]


def _segments_to_dicts(segments: list[ParsedLyricSegment]) -> list[dict[str, Any]]:
    return [{"text": segment.text, "start": segment.start, "end": segment.end} for segment in segments]


def _get_transcription_model(
    model_name: str,
    device: str,
    compute_type: str | None = None,
    language: str | None = None,
):
    if whisperx is None:
        raise RuntimeError("WhisperX is not installed in this environment")

    normalized_compute_type = _normalize_compute_type(device, compute_type)
    cache_key = (model_name, device, normalized_compute_type)
    model = _TRANSCRIPTION_MODEL_CACHE.get(cache_key)
    if model is not None:
        return model

    kwargs: dict[str, Any] = {
        "device": device,
        "compute_type": normalized_compute_type,
    }
    if language:
        kwargs["language"] = language
    model = whisperx.load_model(model_name, **kwargs)
    _TRANSCRIPTION_MODEL_CACHE[cache_key] = model
    return model


def _get_align_model(language_code: str, device: str):
    if whisperx is None:
        raise RuntimeError("WhisperX is not installed in this environment")

    normalized_language = _normalize_language_code(language_code)
    cache_key = (normalized_language, device)
    cached = _ALIGN_MODEL_CACHE.get(cache_key)
    if cached is not None:
        return cached
    model = whisperx.load_align_model(language_code=normalized_language, device=device)
    _ALIGN_MODEL_CACHE[cache_key] = model
    return model


def _detect_language(
    audio: Any,
    *,
    transcription_model: str,
    device: str,
    compute_type: str | None,
) -> str:
    model = _get_transcription_model(transcription_model, device, compute_type=compute_type)
    detected = model.detect_language(audio)
    if isinstance(detected, tuple):
        detected = detected[0]
    if isinstance(detected, dict):
        detected = detected.get("language")
    return _normalize_language_code(str(detected))


def _parse_preload_entries(preload_models: str | None) -> list[tuple[str, str]]:
    if not preload_models:
        return []

    entries: list[tuple[str, str]] = []
    current_kind = "transcription"
    for raw_entry in re.split(r"[,\n]+", preload_models):
        entry = raw_entry.strip()
        if not entry:
            continue
        if "=" in entry:
            kind, value = entry.split("=", 1)
            current_kind = kind.strip().lower()
        elif ":" in entry:
            kind, value = entry.split(":", 1)
            current_kind = kind.strip().lower()
        else:
            kind, value = current_kind, entry
        normalized_kind = kind.strip().lower()
        normalized_value = value.strip()
        if not normalized_value:
            continue
        if normalized_kind in {"align", "alignment", "language"}:
            entries.append(("align", normalized_value))
        else:
            entries.append(("transcription", normalized_value))
    return entries


def preload_models(
    preload_models: str | None,
    *,
    device: str,
    compute_type: str | None = None,
) -> list[str]:
    if whisperx is None:
        return []
    loaded_entries: list[str] = []
    for kind, value in _parse_preload_entries(preload_models):
        loaded_entries.append(f"{kind}={value}")
        if kind == "align":
            _get_align_model(value, device)
        else:
            _get_transcription_model(value, device, compute_type=compute_type)
    return loaded_entries


def unload_models() -> dict[str, int]:
    """Drop WhisperX model references held by this process and release GPU memory."""
    transcription_models = len(_TRANSCRIPTION_MODEL_CACHE)
    align_models = len(_ALIGN_MODEL_CACHE)

    _TRANSCRIPTION_MODEL_CACHE.clear()
    _ALIGN_MODEL_CACHE.clear()

    # Clear any now-unreachable Python objects before asking CUDA to return cached blocks.
    gc.collect()

    try:
        import torch  # type: ignore

        if torch.cuda.is_available():
            torch.cuda.synchronize()
            torch.cuda.empty_cache()
            if hasattr(torch.cuda, "ipc_collect"):
                torch.cuda.ipc_collect()
    except Exception:
        pass

    gc.collect()
    return {
        "transcription_models": transcription_models,
        "align_models": align_models,
    }


def _make_segment(start: int, end: int, words: list[dict[str, Any]]) -> dict[str, Any]:
    current_words = [word for word in words[start:end] if str(word.get("word", "")).strip()]
    if not current_words:
        return {"start": 0.0, "end": 0.0, "text": "", "words": []}
    return {
        "start": float(current_words[0].get("start", 0.0) or 0.0),
        "end": float(current_words[-1].get("end", 0.0) or 0.0),
        "text": _join_display_tokens(str(word.get("word", "")) for word in current_words),
        "words": current_words,
    }


def _realign_easy(segments: list[ParsedLyricSegment], words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aligned_segments: list[dict[str, Any]] = []
    current_index = 0
    for segment in segments:
        token_count = len(_alignment_tokens(segment.text))
        start_index = current_index
        current_index += token_count
        aligned_segments.append(_make_segment(start_index, current_index, words))
    return aligned_segments


def _sequence_boundary_map(source_tokens: list[str], aligned_tokens: list[str]) -> list[int]:
    """Map every source-token boundary to a monotonic aligned-word boundary."""
    boundaries: list[int | None] = [None] * (len(source_tokens) + 1)
    boundaries[0] = 0
    boundaries[-1] = len(aligned_tokens)

    matcher = SequenceMatcher(a=source_tokens, b=aligned_tokens, autojunk=False)
    for tag, source_start, source_end, aligned_start, aligned_end in matcher.get_opcodes():
        source_length = source_end - source_start
        aligned_length = aligned_end - aligned_start

        if tag == "insert":
            boundaries[source_start] = aligned_end
            continue

        for offset in range(source_length + 1):
            if tag == "equal":
                aligned_boundary = aligned_start + offset
            elif tag == "delete":
                aligned_boundary = aligned_start
            else:
                aligned_boundary = aligned_start + round(
                    offset * aligned_length / source_length
                )
            boundaries[source_start + offset] = aligned_boundary

    previous = 0
    resolved: list[int] = []
    for boundary in boundaries:
        current = previous if boundary is None else boundary
        current = max(previous, min(len(aligned_tokens), current))
        resolved.append(current)
        previous = current
    resolved[-1] = len(aligned_tokens)
    return resolved


def _realign_with_sequence(
    segments: list[ParsedLyricSegment],
    words: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    source_tokens: list[str] = []
    line_boundaries = [0]
    for segment in segments:
        source_tokens.extend(
            token
            for token in (_clean_token(token) for token in _alignment_tokens(segment.text))
            if token
        )
        line_boundaries.append(len(source_tokens))

    aligned_tokens = [
        _clean_token(str(word.get("word", "")))
        for word in words
    ]
    boundary_map = _sequence_boundary_map(source_tokens, aligned_tokens)

    return [
        _make_segment(boundary_map[start], boundary_map[end], words)
        for start, end in zip(line_boundaries, line_boundaries[1:])
    ]


def _rebuild_synced_segments(
    original_segments: list[ParsedLyricSegment],
    aligned_words: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    filtered_words = _alignment_words(aligned_words)
    filtered_segments = [
        segment
        for segment in original_segments
        if segment.text.strip() and _alignment_tokens(segment.text)
    ]
    if not filtered_segments or not filtered_words:
        return []

    expected_word_count = sum(len(_alignment_tokens(segment.text)) for segment in filtered_segments)
    if expected_word_count == len(filtered_words):
        return _realign_easy(filtered_segments, filtered_words)
    return _realign_with_sequence(filtered_segments, filtered_words)


def align_lyrics(
    audio_path: Path,
    lyrics_text: str,
    *,
    lyrics_format: str | None,
    transcription_model: str,
    align_language: str | None,
    detect_language: bool,
    use_synced_lyrics: bool,
    device: str,
    compute_type: str | None,
) -> list[dict[str, Any]]:
    if whisperx is None:
        raise RuntimeError("WhisperX is not installed in this environment")

    audio = whisperx.load_audio(str(audio_path))
    audio_length = float(len(audio) / 16000.0) if hasattr(audio, "__len__") else 0.0

    if lyrics_format and lyrics_format not in _SUPPORTED_LYRICS_FORMATS:
        raise ValueError(f"Unsupported lyrics format: {lyrics_format}")

    parsed_segments, parsed_is_synced = _parse_lyrics(lyrics_text, lyrics_format)

    if not parsed_segments:
        return []

    if detect_language or not align_language:
        language_code = _detect_language(
            audio,
            transcription_model=transcription_model,
            device=device,
            compute_type=compute_type,
        )
    else:
        language_code = _normalize_language_code(align_language)

    align_model, metadata = _get_align_model(language_code, device)

    if parsed_is_synced and use_synced_lyrics:
        transcript = _segments_to_dicts(parsed_segments)
    else:
        transcript = _flatten_segments(parsed_segments, audio_length)

    aligned = whisperx.align(
        transcript,
        align_model,
        metadata,
        audio,
        device=device,
        return_char_alignments=False,
    )

    aligned_segments = list(aligned.get("segments") or [])
    if parsed_is_synced:
        words = [word for segment in aligned_segments for word in segment.get("words", [])]
        rebuilt = _rebuild_synced_segments(parsed_segments, words)
        if rebuilt:
            return rebuilt
    return aligned_segments


def dump_aligned_lyrics_json(aligned_segments: list[dict[str, Any]]) -> str:
    return json.dumps(aligned_segments, ensure_ascii=False, indent=2)
