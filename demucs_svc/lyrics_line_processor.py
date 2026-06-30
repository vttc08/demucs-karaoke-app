from __future__ import annotations

import re

_CJK_CHAR_RE = re.compile(r"[\u4e00-\u9fff]")
_ODD_SPACES_RE = re.compile(r"[^\S\n]|\u00A0|\u1680|[\u2000-\u200A]|\u202F|\u205F|\u3000")


def process_lyric_lines(
    lines: list[str],
    *,
    max_line_length: int,
    max_line_length_cjk: int,
) -> list[str]:
    processed: list[str] = []
    for line in lines:
        cleaned = _clean_line(line)
        if not cleaned:
            continue
        processed.extend(_process_line(cleaned, max_line_length, max_line_length_cjk))
    return [line for line in processed if line]


def _clean_line(line: str) -> str:
    cleaned = _ODD_SPACES_RE.sub(" ", str(line or ""))
    cleaned = re.sub(r" +", " ", cleaned).strip()
    cleaned = re.sub(r"\s+([,\.!?:;])", r"\1", cleaned)
    cleaned = re.sub(r'(".*?)(,)(\s*")', r"\1\3,", cleaned)
    return cleaned


def _weighted_length(text: str, cjk_cost: float) -> float:
    total = 0.0
    for char in text:
        if char.isspace():
            total += 1.0
        elif _CJK_CHAR_RE.match(char):
            total += cjk_cost
        else:
            total += 1.0
    return total


def _line_profile(text: str, max_line_length: int, max_line_length_cjk: int) -> tuple[float, float]:
    ascii_chars = 0
    cjk_chars = 0
    for char in text:
        if char.isspace():
            continue
        if _CJK_CHAR_RE.match(char):
            cjk_chars += 1
        else:
            ascii_chars += 1
    if cjk_chars == 0:
        return float(max_line_length), 1.0
    if ascii_chars == 0:
        return float(max_line_length_cjk), 1.0
    # Mixed English+CJK lines should not collapse to the strict CJK limit.
    # Scale each CJK character to the English limit ratio so a mixed line is
    # allowed to stay closer to the English cap while still counting CJK more
    # heavily than ASCII.
    cjk_cost = max(float(max_line_length) / float(max_line_length_cjk), 1.0)
    return float(max_line_length), cjk_cost


def _line_too_long(line: str, max_line_length: int, max_line_length_cjk: int) -> bool:
    limit, cjk_cost = _line_profile(line, max_line_length, max_line_length_cjk)
    return _weighted_length(line, cjk_cost=cjk_cost) > limit


def _find_best_split_point(line: str, max_line_length: int, max_line_length_cjk: int) -> int:
    limit, cjk_cost = _line_profile(line, max_line_length, max_line_length_cjk)
    words = line.split()
    if words:
        mid_word_index = len(words) // 2
        if "," in line:
            mid_point = len(" ".join(words[:mid_word_index]))
            comma_indices = [i for i, char in enumerate(line) if char == ","]
            for index in comma_indices:
                if abs(mid_point - index) < 20 and _weighted_length(line[: index + 1].strip(), cjk_cost=cjk_cost) <= limit:
                    return index + 1

        if " and " in line:
            mid_point = len(line) // 2
            and_indices = [m.start() for m in re.finditer(r" and ", line)]
            for index in sorted(and_indices, key=lambda value: abs(value - mid_point)):
                if _weighted_length(line[: index + len(" and ")].strip(), cjk_cost=cjk_cost) <= limit:
                    return index + len(" and ")

        if len(words) > 2 and mid_word_index > 0:
            split_at_middle = len(" ".join(words[:mid_word_index]))
            if _weighted_length(line[:split_at_middle].strip(), cjk_cost=cjk_cost) <= limit:
                return split_at_middle

    weighted = 0.0
    last_space = -1
    for index, char in enumerate(line):
        if char.isspace():
            last_space = index
        weighted += 1.0 if char.isspace() else (cjk_cost if _CJK_CHAR_RE.match(char) else 1.0)
        if weighted > limit:
            return last_space if last_space != -1 else max(1, index)
    return len(line)


def _find_matching_paren(line: str, start_index: int) -> int:
    stack = 0
    for index in range(start_index, len(line)):
        if line[index] == "(":
            stack += 1
        elif line[index] == ")":
            stack -= 1
            if stack == 0:
                return index
    return -1


def _split_line(line: str, max_line_length: int, max_line_length_cjk: int) -> list[str]:
    if not _line_too_long(line, max_line_length, max_line_length_cjk):
        return [line]

    split_lines: list[str] = []
    remaining = line
    while _line_too_long(remaining, max_line_length, max_line_length_cjk):
        split_point = _find_best_split_point(remaining, max_line_length, max_line_length_cjk)
        if split_point <= 0:
            split_point = max(1, len(remaining) // 2)
        split_lines.append(remaining[:split_point].strip())
        remaining = remaining[split_point:].strip()
    if remaining:
        split_lines.append(remaining)
    return split_lines


def _process_line(line: str, max_line_length: int, max_line_length_cjk: int) -> list[str]:
    processed_lines: list[str] = []
    remaining = line

    while _line_too_long(remaining, max_line_length, max_line_length_cjk):
        if "(" in remaining and ")" in remaining:
            start_paren = remaining.find("(")
            end_paren = _find_matching_paren(remaining, start_paren)
            if end_paren >= 0:
                if start_paren > 0:
                    processed_lines.extend(
                        _split_line(remaining[:start_paren].strip(), max_line_length, max_line_length_cjk)
                    )
                paren_content = remaining[start_paren : end_paren + 1].strip()
                processed_lines.extend(_split_line(paren_content, max_line_length, max_line_length_cjk))
                remaining = remaining[end_paren + 1 :].strip()
                continue

        split_point = _find_best_split_point(remaining, max_line_length, max_line_length_cjk)
        if split_point <= 0:
            split_point = max(1, len(remaining) // 2)
        processed_lines.append(remaining[:split_point].strip())
        remaining = remaining[split_point:].strip()

    if remaining:
        processed_lines.extend(_split_line(remaining, max_line_length, max_line_length_cjk))
    return processed_lines
