"""Chinese lyrics simplification and pinyin rendering helpers."""
from __future__ import annotations

import logging
import re
from functools import lru_cache

logger = logging.getLogger(__name__)

_CHINESE_RUN_RE = re.compile(r"([\u3400-\u4dbf\u4e00-\u9fff\ufa0e-\ufa2d]+)")
_CHINESE_CHAR_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\ufa0e-\ufa2d]")

try:
    from opencc import OpenCC
except ImportError:  # pragma: no cover - dependency is installed in normal runs
    OpenCC = None

try:
    from pypinyin import lazy_pinyin
except ImportError:  # pragma: no cover - dependency is installed in normal runs
    lazy_pinyin = None

class ChineseLyricsService:
    """Simplify Chinese text and optionally build pinyin display rows."""

    def __init__(self) -> None:
        self._opencc = self._build_opencc()

    @staticmethod
    @lru_cache(maxsize=1)
    def _build_opencc():
        if OpenCC is None:
            logger.warning("opencc is unavailable; Chinese simplification will be a no-op")
            return None
        return OpenCC("t2s")

    @staticmethod
    def _has_chinese(text: str) -> bool:
        return bool(_CHINESE_CHAR_RE.search(text))

    def simplify_text(self, text: str) -> str:
        """Convert traditional Chinese text to simplified Chinese when possible."""
        if not text:
            return ""
        if self._opencc is None:
            return text
        return self._opencc.convert(text)

    @staticmethod
    def _is_wordish(text: str) -> bool:
        return bool(text) and text[0].isalnum() and text[-1].isalnum()

    def _to_pinyin(self, text: str) -> str:
        """Convert a mixed string to display-friendly pinyin while preserving non-Chinese text."""
        if not text:
            return ""
        if lazy_pinyin is None:
            logger.warning("pypinyin is unavailable; pinyin rendering will be omitted")
            return text

        pieces: list[str] = []
        for part in filter(None, _CHINESE_RUN_RE.split(text)):
            if _CHINESE_RUN_RE.fullmatch(part):
                converted = " ".join(lazy_pinyin(part))
            else:
                converted = part

            if pieces and self._is_wordish(pieces[-1]) and self._is_wordish(converted):
                pieces.append(" ")
            pieces.append(converted)
        return "".join(pieces)

    def transform_lines(self, texts: list[str], include_pinyin: bool = False) -> list[dict[str, object]]:
        """Transform each line independently for display."""
        items: list[dict[str, object]] = []
        for raw_text in texts:
            original = raw_text or ""
            simplified = self.simplify_text(original)
            has_chinese = self._has_chinese(simplified)
            pinyin = self._to_pinyin(simplified) if include_pinyin and has_chinese else None
            items.append(
                {
                    "original": original,
                    "simplified": simplified,
                    "pinyin": pinyin,
                    "has_chinese": has_chinese,
                }
            )
        return items
