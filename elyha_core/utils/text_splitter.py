"""Text splitting helpers."""

from __future__ import annotations

from elyha_core.i18n import tr


def split_text_by_chars(text: str, *, chunk_size: int = 3000) -> list[str]:
    """Split text into stable char chunks preserving order."""
    if chunk_size <= 0:
        raise ValueError(tr("err.chunk_size_positive"))
    normalized = (text or "").strip()
    if not normalized:
        return []
    return [normalized[i : i + chunk_size] for i in range(0, len(normalized), chunk_size)]
