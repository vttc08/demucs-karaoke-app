"""Report missing and unreferenced frontend translation keys."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LOCALES_DIR = ROOT / "locales"
CATALOG_PATHS = list(LOCALES_DIR.glob("*.json"))
# CATALOG_PATHS = (ROOT / "locales/en.json", ROOT / "locales/zh-CN.json")
SOURCE_SUFFIXES = {".py", ".js", ".html", ".md"}
EXCLUDED_PARTS = {".git", ".venv", "node_modules", "static/docs", "docs-site"}
# Add a key here only when production code constructs it dynamically instead
# of containing the complete key as a string literal.
DYNAMIC_KEYS: set[str] = set()


def _source_text() -> str:
    chunks: list[str] = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in SOURCE_SUFFIXES:
            continue
        relative = path.relative_to(ROOT)
        relative_text = relative.as_posix()
        if path in CATALOG_PATHS or any(
            part in relative.parts for part in EXCLUDED_PARTS if "/" not in part
        ):
            continue
        if any(relative_text.startswith(prefix) for prefix in ("static/docs/", "docs-site/")):
            continue
        chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def audit() -> tuple[list[str], list[str]]:
    catalogs = [json.loads(path.read_text(encoding="utf-8")) for path in CATALOG_PATHS]
    english_keys = set(catalogs[0])
    parity_missing = sorted(english_keys.symmetric_difference(set(catalogs[1])))
    source = _source_text()
    unused = sorted(key for key in english_keys if key not in source and key not in DYNAMIC_KEYS)
    return parity_missing, unused


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail when the audit finds issues")
    args = parser.parse_args()
    parity_missing, unused = audit()
    if parity_missing:
        print("Catalog parity differences:")
        print("\n".join(parity_missing))
    if unused:
        print("Unreferenced keys:")
        print("\n".join(unused))
    if not parity_missing and not unused:
        print("Translation catalogs are in parity and all keys are referenced.")
    return 1 if args.check and (parity_missing or unused) else 0


if __name__ == "__main__":
    raise SystemExit(main())
