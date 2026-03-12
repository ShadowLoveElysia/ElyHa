"""Runtime i18n loader backed by repository-level JSON catalogs."""

from __future__ import annotations

from functools import lru_cache
import json
import os
from pathlib import Path
from typing import Final


SUPPORTED_LOCALES: Final[tuple[str, ...]] = ("zh", "en", "ja")
DEFAULT_LOCALE: Final[str] = "zh"


def normalize_locale(value: str | None) -> str:
    if value is None:
        return DEFAULT_LOCALE
    text = value.strip().lower()
    if not text:
        return DEFAULT_LOCALE
    text = text.replace("-", "_")
    if "." in text:
        text = text.split(".", 1)[0]
    if "_" in text:
        text = text.split("_", 1)[0]
    if text in SUPPORTED_LOCALES:
        return text
    return DEFAULT_LOCALE


def current_locale() -> str:
    return normalize_locale(os.getenv("ELYHA_LOCALE"))


def available_locales() -> tuple[str, ...]:
    return SUPPORTED_LOCALES


@lru_cache(maxsize=1)
def _load_catalogs() -> dict[str, dict[str, str]]:
    repo_root = Path(__file__).resolve().parent.parent
    i18n_dir = repo_root / "i18n"
    catalogs: dict[str, dict[str, str]] = {}
    for locale in SUPPORTED_LOCALES:
        path = i18n_dir / f"{locale}.json"
        if not path.exists():
            catalogs[locale] = {}
            continue
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            catalogs[locale] = {}
            continue
        catalogs[locale] = {str(key): str(value) for key, value in raw.items()}
    return catalogs


def clear_i18n_cache() -> None:
    _load_catalogs.cache_clear()


def catalog(locale: str | None = None) -> dict[str, str]:
    """Return a copy of one locale catalog with normalization."""
    chosen = normalize_locale(locale if locale is not None else os.getenv("ELYHA_LOCALE"))
    catalogs = _load_catalogs()
    return dict(catalogs.get(chosen, {}))


def tr(key: str, *, locale: str | None = None, **kwargs: object) -> str:
    chosen = normalize_locale(locale if locale is not None else os.getenv("ELYHA_LOCALE"))
    catalogs = _load_catalogs()
    text = (
        catalogs.get(chosen, {}).get(key)
        or catalogs.get(DEFAULT_LOCALE, {}).get(key)
        or catalogs.get("en", {}).get(key)
        or key
    )
    if not kwargs:
        return text
    try:
        return text.format(**kwargs)
    except (KeyError, ValueError):
        return text
