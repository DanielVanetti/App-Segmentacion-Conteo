"""
Punto de entrada de la API.

Ejecutar:  python -m uvicorn app.main:app --reload
Docs:      http://127.0.0.1:8000/docs
"""

from contextlib import asynccontextmanager
from typing import Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app import contenedor as contenedor_mod
from app.api import rutas_salud, rutas_trabajos
from app.config import Config
from app.contenedor import Contenedor
from app.dominio import errores

# Error del dominio -> código HTTP
CODIGOS_HTTP = {
    errores.ArchivoNoValido: 400,
    errores.TrabajoNoEncontrado: 404,
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

    @app.exception_handler(errores.ErrorDominio)
    async def manejar_error_dominio(_: Request, exc: errores.ErrorDominio):
        codigo = CODIGOS_HTTP.get(type(exc), 400)
        return JSONResponse(status_code=codigo, content={"detail": str(exc)})

    return app


app = crear_app()
