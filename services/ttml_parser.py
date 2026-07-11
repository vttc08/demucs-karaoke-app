"""TTML parsing helpers for converting subtitle XML into WhisperX JSON."""
from __future__ import annotations

import re
from typing import Any
from xml.etree import ElementTree as ET

_TIME_RE = re.compile(
    r"^(?:(?:(?P<hours>\d+):)?(?P<minutes>\d{1,2}):)?(?P<seconds>\d{1,2}(?:\.\d+)?)$"
)
_UNIT_TIME_RE = re.compile(
    r"^(?:(?P<hours>\d+(?:\.\d+)?)h)?(?:(?P<minutes>\d+(?:\.\d+)?)m)?(?:(?P<seconds>\d+(?:\.\d+)?)s)?$"
)


class TTMLParseError(ValueError):
    """Raised when TTML input cannot be parsed into lyric cues."""


def is_valid_xml(text: str) -> bool:
    """Return True when the provided text is well-formed XML."""
    value = str(text or "").strip()
    if not value:
        return False
    try:
        ET.fromstring(value)
    except ET.ParseError:
        return False
    return True


def has_word_level_timing(ttml_text: str) -> bool:
    """Return whether TTML contains enough explicit span timing for an upgrade.

    Paragraph-only TTML is still accepted by the normal parser because it is a
    useful line-timed import format. Automatic upgrades are stricter: every
    lyric paragraph must contain explicitly timed spans, and the document must
    contain more spans than paragraphs so a single span cannot merely mirror a
    whole lyric line.
    """
    try:
        root = _parse_root(ttml_text)
    except TTMLParseError:
        return False

    if _local_name(root.tag) not in {"tt", "ttml"}:
        return False

    paragraph_count = 0
    timed_span_count = 0
    for paragraph in _iter_elements(root, "p"):
        paragraph_text = _normalize_text("".join(paragraph.itertext()))
        if not paragraph_text:
            continue

        paragraph_count += 1
        spans = [
            span
            for span in paragraph.iter()
            if span is not paragraph
            and _local_name(span.tag) == "span"
            and _normalize_text("".join(span.itertext()))
        ]
        if not spans:
            return False

        for span in spans:
            start = _parse_time(span.attrib.get("begin"))
            end = _parse_time(span.attrib.get("end"))
            if start is None or end is None or end <= start:
                return False
            timed_span_count += 1

    return paragraph_count > 0 and timed_span_count > paragraph_count


def parse_ttml_to_whisperx_segments(ttml_text: str) -> list[dict[str, Any]]:
    """Parse TTML into WhisperX-style segments."""
    root = _parse_root(ttml_text)
    if _local_name(root.tag) not in {"tt", "ttml"}:
        raise TTMLParseError("TTML root element must be <tt>")

    segments: list[dict[str, Any]] = []
    for paragraph in _iter_elements(root, "p"):
        segment = _parse_paragraph(paragraph)
        if segment is not None:
            segments.append(segment)

    segments.sort(key=lambda row: float(row["start"]))
    return segments


def _parse_root(ttml_text: str) -> ET.Element:
    value = str(ttml_text or "").strip()
    if not value:
        raise TTMLParseError("TTML input is empty")
    try:
        return ET.fromstring(value)
    except ET.ParseError as exc:
        raise TTMLParseError(f"Invalid TTML XML: {exc}") from exc


def _parse_paragraph(paragraph: ET.Element) -> dict[str, Any] | None:
    paragraph_begin = _parse_time(paragraph.attrib.get("begin"))
    paragraph_end = _parse_time(paragraph.attrib.get("end"))
    spans = [child for child in paragraph.iter() if child is not paragraph and _local_name(child.tag) == "span"]

    words: list[dict[str, Any]] = []
    current_start = paragraph_begin
    for index, span in enumerate(spans):
        text = _normalize_text("".join(span.itertext()))
        if not text:
            continue

        start = _parse_time(span.attrib.get("begin"))
        end = _parse_time(span.attrib.get("end"))
        if start is None:
            start = current_start if current_start is not None else paragraph_begin
        if start is None:
            continue

        if end is None:
            next_start = _next_span_start(spans, index)
            if next_start is not None and next_start >= start:
                end = next_start
            elif paragraph_end is not None:
                end = paragraph_end
            else:
                end = start

        if end < start:
            end = start

        word = {
            "word": text,
            "start": round(float(start), 3),
            "end": round(float(end), 3),
        }
        words.append(word)
        current_start = end

    if words:
        segment_start = paragraph_begin if paragraph_begin is not None else float(words[0]["start"])
        segment_end = paragraph_end if paragraph_end is not None else float(words[-1]["end"])
        if segment_end < segment_start:
            segment_end = segment_start
        return {
            "start": round(float(segment_start), 3),
            "end": round(float(segment_end), 3),
            "text": " ".join(word["word"] for word in words),
            "words": words,
        }

    paragraph_text = _normalize_text("".join(paragraph.itertext()))
    if not paragraph_text:
        return None

    segment_start = 0.0 if paragraph_begin is None else float(paragraph_begin)
    segment_end = float(paragraph_end) if paragraph_end is not None else segment_start
    if segment_end < segment_start:
        segment_end = segment_start
    return {
        "start": round(segment_start, 3),
        "end": round(segment_end, 3),
        "text": paragraph_text,
        "words": [
            {
                "word": paragraph_text,
                "start": round(segment_start, 3),
                "end": round(segment_end, 3),
            }
        ],
    }


def _iter_elements(root: ET.Element, local_name: str) -> list[ET.Element]:
    return [element for element in root.iter() if _local_name(element.tag) == local_name]


def _next_span_start(spans: list[ET.Element], index: int) -> float | None:
    for span in spans[index + 1 :]:
        start = _parse_time(span.attrib.get("begin"))
        if start is not None:
            return start
    return None


def _parse_time(value: str | None) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None

    colon_match = _TIME_RE.fullmatch(text)
    if colon_match is not None:
        seconds = float(colon_match.group("seconds"))
        minutes = int(colon_match.group("minutes") or 0)
        hours = int(colon_match.group("hours") or 0)
        return hours * 3600 + minutes * 60 + seconds

    unit_match = _UNIT_TIME_RE.fullmatch(text)
    if unit_match is not None and any(unit_match.group(name) for name in ("hours", "minutes", "seconds")):
        hours = float(unit_match.group("hours") or 0)
        minutes = float(unit_match.group("minutes") or 0)
        seconds = float(unit_match.group("seconds") or 0)
        return hours * 3600 + minutes * 60 + seconds

    if text.endswith("s"):
        try:
            return float(text[:-1])
        except ValueError:
            return None

    try:
        return float(text)
    except ValueError:
        return None


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _local_name(tag: object) -> str:
    text = str(tag or "")
    if "}" in text:
        return text.rsplit("}", 1)[-1]
    return text
