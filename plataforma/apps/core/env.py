"""Small environment helpers with no external dependency."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse


def load_env_file(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def env(name: str, default: str | None = None) -> str:
    value = os.getenv(name)
    if value is None or value == "":
        if default is None:
            return ""
        return str(default)
    return value


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on", "si"}


def env_list(name: str, default: list[str] | None = None) -> list[str]:
    value = os.getenv(name)
    if not value:
        return list(default or [])
    return [item.strip() for item in value.split(",") if item.strip()]


def database_from_url(url: str) -> dict[str, object]:
    parsed = urlparse(url)

    if parsed.scheme in {"sqlite", "sqlite3"}:
        path = unquote(parsed.path)
        if parsed.netloc and not path:
            path = parsed.netloc
        if path in {"", "/"}:
            path = ":memory:"
        if path != ":memory:":
            path = str(Path(path))
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": path}

    if parsed.scheme in {"postgres", "postgresql", "postgresql+psycopg"}:
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(parsed.path.lstrip("/")),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "127.0.0.1",
            "PORT": str(parsed.port or 5432),
        }

    raise ValueError(f"Unsupported DATABASE_URL scheme: {parsed.scheme}")
