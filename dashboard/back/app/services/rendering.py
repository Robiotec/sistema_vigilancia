from __future__ import annotations

import re
from pathlib import Path


class BaseTemplateRenderer:
    """Renderizador padre con soporte de includes simples."""

    include_pattern = re.compile(r"__INCLUDE:([A-Za-z0-9_./-]+)__")

    def __init__(self, templates_dir: Path) -> None:
        self.templates_dir = templates_dir

    def source(self, name: str, seen: set[Path] | None = None) -> str:
        root = self.templates_dir.resolve()
        path = (root / name).resolve()
        path.relative_to(root)
        seen = set() if seen is None else seen
        if path in seen:
            raise ValueError(f"Template include circular: {name}")
        seen.add(path)
        source = path.read_text(encoding="utf-8")

        def replace(match: re.Match[str]) -> str:
            return self.source(match.group(1), seen)

        return self.include_pattern.sub(replace, source)


class DashboardTemplateRenderer(BaseTemplateRenderer):
    """Renderizador hijo para templates del frontend del dashboard."""

    def render_source(self, template: str, context: dict[str, str]) -> str:
        source = self.source(template)
        for key, value in context.items():
            source = source.replace(key, value)
        return re.sub(r"__[A-Z0-9_]+__", "", source)
