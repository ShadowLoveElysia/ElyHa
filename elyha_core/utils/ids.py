"""ID validation and generation helpers."""

from __future__ import annotations

import re
import uuid

from elyha_core.i18n import tr

_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{2,63}$")


def generate_id(prefix: str) -> str:
    """Generate a stable prefixed identifier."""
    if not prefix or not prefix.isidentifier():
        raise ValueError(tr("err.id_prefix_invalid"))
    suffix = uuid.uuid4().hex[:12]
    return f"{prefix}_{suffix}"


def ensure_valid_id(value: str, *, field_name: str = "id") -> str:
    """Validate and normalize an identifier string."""
    normalized = value.strip()
    if not normalized:
        raise ValueError(tr("err.id_field_empty", field=field_name))
    if not _ID_PATTERN.match(normalized):
        raise ValueError(
            tr(
                "err.id_pattern_mismatch",
                field=field_name,
                pattern=_ID_PATTERN.pattern,
                value=repr(value),
            )
        )
    return normalized
