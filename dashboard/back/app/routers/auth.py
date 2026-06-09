"""Endpoints de autenticación: login, logout y sesión."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from back.app.context import call_api, get_token, is_auth_error
from back.app.state import SESSION_COOKIE

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/login")
async def api_login(request: Request) -> JSONResponse:
    payload = await request.json()
    from back.app.context import _text
    username = _text(payload.get("identity") or payload.get("username"))
    password = _text(payload.get("password"))
    try:
        result = call_api("/auth/login", method="POST", data={"username": username, "password": password})
    except RuntimeError as exc:
        return JSONResponse({"ok": False, "message": str(exc)}, status_code=401)
    response = JSONResponse({"ok": True, "redirect": "/"})
    response.set_cookie(SESSION_COOKIE, result["access_token"], httponly=True, samesite="lax")
    return response


@router.post("/logout")
def api_logout() -> JSONResponse:
    response = JSONResponse({"ok": True, "redirect": "/login"})
    response.delete_cookie(SESSION_COOKIE)
    return response


@router.get("/auth/session")
def auth_session(request: Request):
    token = get_token(request)
    if not token:
        return JSONResponse({"authenticated": False}, status_code=401)
    me = call_api("/auth/me", token=token)
    return {"authenticated": True, "user": {"username": me.get("username"), "roles": me.get("roles", [])}}
