from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final


PACKAGE_DIR: Final[Path] = Path(__file__).resolve().parent
PROJECT_DIR: Final[Path] = PACKAGE_DIR.parent
TEMPLATES_DIR: Final[Path] = PACKAGE_DIR / "templates"
STATIC_DIR: Final[Path] = PACKAGE_DIR / "static"
INDEX_TEMPLATE_PATH: Final[Path] = TEMPLATES_DIR / "index.html"
DEFAULT_VIDEO_PATH: Final[Path] = PROJECT_DIR / "Recorrido Virtual - Plaza Comercial.mp4"


@dataclass(frozen=True, slots=True)
class AppConfig:
    host: str
    port: int
    video_path: Path

    @property
    def video_name(self) -> str:
        return self.video_path.name
