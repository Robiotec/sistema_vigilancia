from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence

from .config import AppConfig, DEFAULT_VIDEO_PATH
from .server import run_server


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Levanta el editor de poligonos."
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host por defecto: 127.0.0.1")
    parser.add_argument("--port", type=int, default=8765, help="Puerto HTTP. Por defecto: 8765")
    parser.add_argument(
        "--video",
        default=str(DEFAULT_VIDEO_PATH),
        help="Ruta del archivo de video MP4.",
    )
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(argv)


def resolve_video_path(raw_path: str) -> Path:
    video_path = Path(raw_path).expanduser().resolve()

    if not video_path.exists():
        raise SystemExit(f"No se encontro el video en: {video_path}")

    if not video_path.is_file():
        raise SystemExit(f"La ruta indicada no es un archivo: {video_path}")

    return video_path


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    config = AppConfig(
        host=args.host,
        port=args.port,
        video_path=resolve_video_path(args.video),
    )
    run_server(config)
