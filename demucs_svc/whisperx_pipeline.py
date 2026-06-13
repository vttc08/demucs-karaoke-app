from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

logger = logging.getLogger(__name__)

try:
    import whisperx  # type: ignore
except Exception:  # pragma: no cover - optional dependency in test environments
    whisperx = None

_TRANSCRIPTION_MODEL_CACHE: dict[tuple[str, str, str], Any] = {}
_ALIGN_MODEL_CACHE: dict[tuple[str, str], tuple[Any, dict[str, Any]]] = {}

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[A-Za-z0-9]+|[^\s]")
_TIMESTAMP_RE = re.compile(r"\[(?P<minutes>\d{1,2}):(?P<seconds>\d{2}(?:\.\d{1,3})?)\]")
_LRC_METADATA_RE = re.compile(r"^\[(?:ar|al|ti|by|offset|re|ve|length):", re.IGNORECASE)
_SUPPORTED_LYRICS_FORMATS = {"lrc", "txt"}


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


def _clean_token(token: str) -> str:
    return re.sub(r"[^\w']+", "", token).lower()


def _preprocess_line(line: str) -> str | None:
    stripped = line.strip()
    if not stripped or _LRC_METADATA_RE.match(stripped):
        return None
    if "/" in stripped:
        stripped = stripped.split("/", 1)[0].strip()
    return stripped or None


def _parse_lrc(text: str) -> tuple[list[ParsedLyricSegment], bool]:
    segments: list[ParsedLyricSegment] = []
    is_synced = False
    lines = text.splitlines()
    for raw_line in lines:
        stripped = raw_line.strip()
        if not stripped or _LRC_METADATA_RE.match(stripped):
            continue
        matches = list(_TIMESTAMP_RE.finditer(stripped))
        lyric_text = _preprocess_line(_TIMESTAMP_RE.sub("", stripped).strip())
        if not matches:
            if lyric_text:
                segments.append(ParsedLyricSegment(text=lyric_text, start=0.0, end=0.0))
            continue
        is_synced = True
        if lyric_text is None:
            continue
        for match in matches:
            minutes = float(match.group("minutes"))
            seconds = float(match.group("seconds"))
            start = (minutes * 60.0) + seconds
            segments.append(ParsedLyricSegment(text=lyric_text, start=start, end=start))
    segments.sort(key=lambda segment: segment.start)
    for index, segment in enumerate(segments):
        if index + 1 < len(segments):
            segment.end = max(segment.start, segments[index + 1].start)
        else:
            segment.end = segment.start + 5.0
    return segments, is_synced


def _parse_text(text: str) -> list[ParsedLyricSegment]:
    lines = [_preprocess_line(line) for line in text.splitlines()]
    return [ParsedLyricSegment(text=line, start=0.0, end=0.0) for line in lines if line]


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
        token_count = len([token for token in _lyric_tokens(segment.text) if token.strip()])
        start_index = current_index
        current_index += token_count
        aligned_segments.append(_make_segment(start_index, current_index, words))
    return aligned_segments


def _realign_hard(segments: list[ParsedLyricSegment], words: list[dict[str, Any]]) -> list[dict[str, Any]]:
    aligned_segments: list[dict[str, Any]] = []
    word_index = 0
    total_words = len(words)
    for segment in segments:
        tokens = [token for token in (_clean_token(token) for token in _lyric_tokens(segment.text)) if token]
        line_start = word_index
        for token in tokens:
            while word_index < total_words and _clean_token(str(words[word_index].get("word", ""))) != token:
                word_index += 1
            if word_index >= total_words:
                break
            word_index += 1
        aligned_segments.append(_make_segment(line_start, word_index, words))
    return aligned_segments


def _rebuild_synced_segments(
    original_segments: list[ParsedLyricSegment],
    aligned_words: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    filtered_segments = [segment for segment in original_segments if segment.text.strip()]
    if not filtered_segments or not aligned_words:
        return []

    expected_word_count = sum(len(_lyric_tokens(segment.text)) for segment in filtered_segments)
    if expected_word_count == len(aligned_words):
        return _realign_easy(filtered_segments, aligned_words)
    return _realign_hard(filtered_segments, aligned_words)


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

    parsed_segments: list[ParsedLyricSegment]
    parsed_is_synced = False
    normalized_format = (lyrics_format or "").lower() or None
    if normalized_format == "txt" or (normalized_format is None and not _TIMESTAMP_RE.search(lyrics_text)):
        parsed_segments = _parse_text(lyrics_text)
    else:
        parsed_segments, parsed_is_synced = _parse_lrc(lyrics_text)
        if not parsed_is_synced:
            parsed_segments = _parse_text(lyrics_text)

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
    if parsed_is_synced and use_synced_lyrics:
        words = [word for segment in aligned_segments for word in segment.get("words", [])]
        rebuilt = _rebuild_synced_segments(parsed_segments, words)
        if rebuilt:
            return rebuilt
    return aligned_segments


def dump_aligned_lyrics_json(aligned_segments: list[dict[str, Any]]) -> str:
    return json.dumps(aligned_segments, ensure_ascii=False, indent=2)
