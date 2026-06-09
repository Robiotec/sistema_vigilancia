from __future__ import annotations

import json
import re
import secrets
import time
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


class BaseHelper:
    """Clase padre para utilidades comunes del backend."""

    @staticmethod
    def json_default(value: Any) -> str:
        return str(value)

    def to_json(self, value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, default=self.json_default)

    def num_id(self, value: Any) -> int:
        text = str(value or "")
        digits = re.sub(r"\D+", "", text)
        if digits:
            return int(digits[:9])
        return int(text.replace("-", "")[:8], 16) if re.fullmatch(r"[0-9a-fA-F-]{8,}", text) else 0

    def text(self, value: Any, fallback: str = "") -> str:
        return str(value or fallback).strip()

    def active(self, value: Any) -> bool:
        return value is not False and str(value).lower() not in {"false", "0", "no", "inactivo"}

    def bool_value(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "si", "sí", "on"}

    def optional_int(self, value: Any) -> int | None:
        text = self.text(value)
        if not text:
            return None
        try:
            return int(text)
        except ValueError:
            return None


class DashboardHelper(BaseHelper):
    """Utilidades hijas propias del dashboard Robiotec."""

    def __init__(self, session_cookie: str) -> None:
        self.session_cookie = session_cookie

    def token(self, request: Request) -> str | None:
        return request.cookies.get(self.session_cookie)

    def is_auth_error(self, error: Exception | str) -> bool:
        text = str(error).strip().lower()
        return any(part in text for part in ("token invalido", "usuario invalido", "unauthorized", "401"))

    def auth_json_response(self) -> JSONResponse:
        response = JSONResponse({"error": "authentication_required", "message": "Sesion expirada"}, status_code=401)
        response.delete_cookie(self.session_cookie)
        return response

    def generated_device_id(self, prefix: str) -> str:
        return f"{prefix}-{int(time.time())}-{secrets.token_hex(3)}".upper()

    def resolve_source_id(self, items: list[dict[str, Any]], raw_id: Any) -> str | None:
        text = self.text(raw_id)
        if not text:
            return None
        for item in items:
            source_id = self.text(item.get("id"))
            if source_id == text or str(self.num_id(source_id)) == text:
                return source_id
        return None
