"""Inyección de dependencias de FastAPI: las rutas piden el servicio, no lo crean."""

from fastapi import Request

from app.contenedor import Contenedor
from app.servicios.servicio_ejecuciones import ServicioEjecuciones
from app.servicios.servicio_proyectos import ServicioProyectos
from app.servicios.servicio_trabajos import ServicioTrabajos


def obtener_contenedor(request: Request) -> Contenedor:
    return request.app.state.contenedor


def obtener_servicio(request: Request) -> ServicioTrabajos:
    return request.app.state.contenedor.servicio


def obtener_proyectos(request: Request) -> ServicioProyectos:
    return request.app.state.contenedor.proyectos


def obtener_ejecuciones(request: Request) -> ServicioEjecuciones:
    return request.app.state.contenedor.ejecuciones
