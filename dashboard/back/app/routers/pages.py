"""Rutas que sirven páginas HTML del dashboard."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from back.app.context import render_page

router = APIRouter(tags=["pages"])


@router.get("/", response_class=HTMLResponse)
def index(request: Request):
    return render_page(request, "index.html")


@router.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    return render_page(request, "login.html")


@router.get("/perfil", response_class=HTMLResponse)
def perfil(request: Request):
    return render_page(request, "perfil.html")


@router.get("/camaras", response_class=HTMLResponse)
def camaras(request: Request):
    return render_page(request, "camaras.html")


@router.get("/mapa", response_class=HTMLResponse)
def mapa(request: Request):
    return render_page(request, "mapa.html")


@router.get("/eventos", response_class=HTMLResponse)
def eventos(request: Request):
    return render_page(request, "eventos.html")


@router.get("/registro-vehiculos", response_class=HTMLResponse)
def registro_vehiculos(request: Request):
    return render_page(request, "registro_vehiculos.html")


@router.get("/usuarios", response_class=HTMLResponse)
def usuarios(request: Request):
    return render_page(request, "usuarios.html")


@router.get("/notificaciones", response_class=HTMLResponse)
def notificaciones(request: Request):
    return render_page(request, "notificaciones.html")


@router.get("/registros", response_class=HTMLResponse)
def registros(request: Request):
    return render_page(request, "registros.html")


@router.get("/health")
def health():
    return {"status": "ok"}
