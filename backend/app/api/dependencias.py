"""Inyección de dependencias de FastAPI: las rutas piden el servicio, no lo crean."""

from fastapi import Request

from app.contenedor import Contenedor
from app.servicios.servicio_trabajos import ServicioTrabajos


def obtener_contenedor(request: Request) -> Contenedor:
    return request.app.state.contenedor


def obtener_servicio(request: Request) -> ServicioTrabajos:
    return request.app.state.contenedor.servicio
