"""
Punto de entrada de la API.

Ejecutar:  python -m uvicorn app.main:app --reload
Docs:      http://127.0.0.1:8000/docs
"""

import logging
from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import contenedor as contenedor_mod
from app.api import rutas_proyectos, rutas_salud, rutas_trabajos
from app.config import Config
from app.contenedor import Contenedor
from app.dominio import errores

log = logging.getLogger("app")

# Error del dominio -> código HTTP
CODIGOS_HTTP = {
    errores.ArchivoNoValido: 400,
    errores.TrabajoNoEncontrado: 404,
    errores.ProyectoNoEncontrado: 404,
    errores.OrtomosaicoNoEncontrado: 404,
    errores.DatosNoValidos: 422,
    errores.TrabajoNoTerminado: 409,
    errores.ArchivoDemasiadoGrande: 413,
    errores.FormatoNoDisponible: 415,
    errores.ImagenInvalida: 422,
    errores.TrabajoFallido: 500,
}


def crear_app(construir: Callable[[Config], Contenedor] = contenedor_mod.construir) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # El modelo se carga UNA sola vez, al iniciar.
        app.state.contenedor = construir(Config.desde_entorno())
        yield
        app.state.contenedor.cerrar()

    app = FastAPI(
        title="API de copas de árboles (YOLOv8-seg)",
        description="Recibe un ortomosaico GeoTIFF y devuelve cada copa como polígono GeoJSON.",
        version="2.0.0",
        lifespan=lifespan,
    )
    app.include_router(rutas_salud.router)
    app.include_router(rutas_trabajos.router)
    app.include_router(rutas_proyectos.router)

    # Todos los errores responden {"mensaje": ..., "detalle": ...} (contrato del frontend),
    # en español y sin trazas técnicas (RNF-11). El detalle técnico va a la bitácora.
    def error(codigo: int, mensaje: str, detalle: str | None = None) -> JSONResponse:
        return JSONResponse(status_code=codigo, content={"mensaje": mensaje, "detalle": detalle})

    @app.exception_handler(errores.ErrorDominio)
    async def manejar_error_dominio(_: Request, exc: errores.ErrorDominio):
        return error(CODIGOS_HTTP.get(type(exc), 400), str(exc))

    @app.exception_handler(RequestValidationError)
    async def manejar_validacion(_: Request, exc: RequestValidationError):
        campos = ", ".join(".".join(str(p) for p in e["loc"] if p != "body") or "cuerpo"
                           for e in exc.errors())
        return error(422, f"Faltan datos o tienen un formato incorrecto: {campos}.",
                     detalle=str(exc.errors()))

    @app.exception_handler(StarletteHTTPException)
    async def manejar_http(_: Request, exc: StarletteHTTPException):
        mensajes = {400: "La solicitud no se pudo leer: el contenido no es JSON válido "
                         "(revise que el texto esté en UTF-8).",
                    404: "La dirección solicitada no existe.",
                    405: "Esa operación no está permitida en esta dirección."}
        return error(exc.status_code, mensajes.get(exc.status_code, str(exc.detail)))

    @app.exception_handler(Exception)
    async def manejar_inesperado(request: Request, exc: Exception):
        log.exception("Error no controlado en %s %s", request.method, request.url.path)
        return error(500, "Ocurrió un error inesperado en el servidor. Intente de nuevo; si "
                          "persiste, revise la bitácora del servidor.")

    return app


app = crear_app()
