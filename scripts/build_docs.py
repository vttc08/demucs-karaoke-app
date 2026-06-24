"""Build the MkDocs site and sync it into the FastAPI static docs mount."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCS_SITE_DIR = ROOT / "docs-site"
BUILT_SITE_DIR = DOCS_SITE_DIR / "site"
STATIC_DOCS_DIR = ROOT / "static" / "docs"


def run_mkdocs_build() -> None:
    subprocess.run(
        [sys.executable, "-m", "mkdocs", "build", "--clean", "-f", "mkdocs.yml"],
        cwd=DOCS_SITE_DIR,
        check=True,
    )


def rewrite_404_assets(html_path: Path) -> None:
    html = html_path.read_text(encoding="utf-8")
    rewritten = html.replace('"/assets/', '"assets/')
    rewritten = rewritten.replace('"base": "/"', '"base": "."')
    html_path.write_text(rewritten, encoding="utf-8")


def sync_site() -> None:
    if STATIC_DOCS_DIR.exists():
        shutil.rmtree(STATIC_DOCS_DIR)
    shutil.copytree(BUILT_SITE_DIR, STATIC_DOCS_DIR)


def main() -> None:
    run_mkdocs_build()
    rewrite_404_assets(BUILT_SITE_DIR / "404.html")
    sync_site()
    rewrite_404_assets(STATIC_DOCS_DIR / "404.html")


if __name__ == "__main__":
    main()
