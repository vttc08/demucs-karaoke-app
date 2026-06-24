"""Runtime custom lyrics provider loading."""
from __future__ import annotations

import hashlib
import importlib.util
import inspect
import logging
import sys
from functools import lru_cache
from pathlib import Path
from typing import Iterable

from config import settings
from services import lyrics_types as lt

logger = logging.getLogger(__name__)

_PROVIDER_CLASS_NAMES = ("LyricsProvider", "CustomLyricsProvider", "Provider")


def load_custom_lyrics_providers(custom_paths: str | Iterable[str] | None = None) -> list[lt.LyricsProvider]:
    """Load user-defined lyrics providers from files or directories.

    Path values may be a comma-separated string or an iterable of paths.
    Directories are scanned for top-level ``*.py`` files in sorted order.
    """
    normalized_paths = tuple(_normalize_custom_paths(custom_paths))
    if not normalized_paths:
        return []
    return list(_load_custom_lyrics_providers_cached(normalized_paths))


def _normalize_custom_paths(custom_paths: str | Iterable[str] | None) -> list[Path]:
    if custom_paths is None:
        raw_paths: Iterable[str] = [settings.lyrics_provider_custom_paths]
    elif isinstance(custom_paths, str):
        raw_paths = custom_paths.split(",")
    else:
        raw_paths = custom_paths

    paths: list[Path] = []
    for raw_path in raw_paths:
        value = str(raw_path).strip()
        if not value:
            continue
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        else:
            path = path.resolve()
        paths.append(path)
    return paths


@lru_cache(maxsize=32)
def _load_custom_lyrics_providers_cached(paths: tuple[Path, ...]) -> tuple[lt.LyricsProvider, ...]:
    providers: list[lt.LyricsProvider] = []
    for path in paths:
        providers.extend(_load_providers_from_path(path))
    return tuple(providers)


def _load_providers_from_path(path: Path) -> list[lt.LyricsProvider]:
    if not path.exists():
        logger.warning("Custom lyrics provider path does not exist path=%s", path)
        return []

    if path.is_dir():
        provider_files = sorted(
            child
            for child in path.iterdir()
            if child.is_file() and child.suffix == ".py" and child.name != "__init__.py" and not child.name.startswith("_")
        )
    elif path.is_file() and path.suffix == ".py":
        provider_files = [path]
    else:
        logger.warning("Custom lyrics provider path is not a Python file or directory path=%s", path)
        return []

    providers: list[lt.LyricsProvider] = []
    for provider_file in provider_files:
        providers.extend(_load_providers_from_file(provider_file))
    return providers


def _load_providers_from_file(provider_file: Path) -> list[lt.LyricsProvider]:
    module_name = _module_name_for_path(provider_file)
    spec = importlib.util.spec_from_file_location(module_name, provider_file)
    if spec is None or spec.loader is None:
        logger.warning("Could not build import spec for custom lyrics provider file=%s", provider_file)
        return []

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
        logger.info("Custom lyrics provider module imported file=%s", provider_file)
    except Exception:
        logger.exception("Custom lyrics provider module import failed file=%s", provider_file)
        return []

    provider_classes = _find_provider_classes(module)
    if not provider_classes:
        logger.warning("No custom lyrics provider class found in file=%s", provider_file)
        return []

    providers: list[lt.LyricsProvider] = []
    for provider_class in provider_classes:
        try:
            provider = provider_class()
        except Exception:
            logger.exception(
                "Custom lyrics provider instantiation failed file=%s class=%s",
                provider_file,
                provider_class.__name__,
            )
            continue

        name = getattr(provider, "name", "")
        fetch = getattr(provider, "fetch", None)
        if not isinstance(name, str) or not name.strip():
            logger.warning(
                "Custom lyrics provider missing non-empty name file=%s class=%s",
                provider_file,
                provider_class.__name__,
            )
            continue
        if not callable(fetch):
            logger.warning(
                "Custom lyrics provider missing callable fetch file=%s class=%s",
                provider_file,
                provider_class.__name__,
            )
            continue
        providers.append(provider)

    return providers


def _find_provider_classes(module: object) -> list[type]:
    classes: list[type] = []
    for class_name in _PROVIDER_CLASS_NAMES:
        candidate = getattr(module, class_name, None)
        if inspect.isclass(candidate) and candidate.__module__ == getattr(module, "__name__", ""):
            classes.append(candidate)
    if classes:
        return classes

    for candidate in vars(module).values():
        if inspect.isclass(candidate) and candidate.__module__ == getattr(module, "__name__", ""):
            if callable(getattr(candidate, "fetch", None)) and isinstance(getattr(candidate, "name", None), str):
                classes.append(candidate)
    return classes[:1]


def _module_name_for_path(path: Path) -> str:
    digest = hashlib.sha1(str(path).encode("utf-8")).hexdigest()[:16]
    return f"_karaoke_custom_lyrics_{digest}"
