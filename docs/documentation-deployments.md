# Documentation Deployments

The application docs live in `docs-site/docs/` and are built with MkDocs.

## Build flow

1. Markdown sources in `docs-site/docs/` are built with `docs-site/mkdocs.yml`.
2. `scripts/build_docs.py` builds the MkDocs site.
3. The generated site is copied into `static/docs/` for FastAPI to serve at `/help`.

## Local build

Use the same build script the app uses:

```bash
uv run python scripts/build_docs.py
```

## GitHub Pages

GitHub Pages deploys from the `main` branch through `.github/workflows/docs-pages.yml`.

## Cloudflare Pages

Cloudflare Pages is connected to the GitHub repository and auto-deploys from `main`.
The current Git-backed project is `demucs-karaoke-app-github` at:

- `https://demucs-karaoke-app-github.pages.dev`

The Cloudflare build command installs the docs dependencies from `docs-site/requirements.txt`
and then runs `scripts/build_docs.py`.
