"""Prompt template loader backed by data/prompt/*.txt files."""

from __future__ import annotations

from pathlib import Path
import re


_PLACEHOLDER_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")
_TEMPLATE_NAME_PATTERN = re.compile(r"[A-Za-z0-9_.-]+")


class PromptTemplateService:
    """Load prompt templates from disk and render placeholders safely."""

    def __init__(self, prompt_dir: str | Path | None = None) -> None:
        if prompt_dir is None:
            repo_root = Path(__file__).resolve().parents[2]
            prompt_dir = repo_root / "data" / "prompt"
        self.prompt_dir = Path(prompt_dir)
        self._cache: dict[str, tuple[int, str]] = {}

    def load(self, template_name: str) -> str:
        name = str(template_name or "").strip()
        if not name or not _TEMPLATE_NAME_PATTERN.fullmatch(name):
            return ""
        path = self.prompt_dir / f"{name}.txt"
        if not path.exists() or not path.is_file():
            return ""
        try:
            stat = path.stat()
        except OSError:
            return ""
        cached = self._cache.get(name)
        mtime_ns = int(getattr(stat, "st_mtime_ns", int(stat.st_mtime * 1_000_000_000)))
        if cached and cached[0] == mtime_ns:
            return cached[1]
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return ""
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        self._cache[name] = (mtime_ns, normalized)
        return normalized

    def render(self, template_name: str, *, fallback: str = "", **kwargs: object) -> str:
        template = self.load(template_name) or str(fallback or "")
        if not template:
            return ""
        return self.render_text(template, **kwargs)

    def render_text(self, text: str, **kwargs: object) -> str:
        raw = str(text or "")
        if not raw:
            return ""

        def _replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key not in kwargs:
                return match.group(0)
            return str(kwargs[key])

        return _PLACEHOLDER_PATTERN.sub(_replace, raw)
