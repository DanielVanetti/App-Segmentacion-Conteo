"""
Puertos = interfaces que el núcleo necesita.
Los adaptadores (app/adaptadores/) las implementan. El núcleo solo conoce estas
interfaces, así se puede cambiar una pieza (otro modelo, PostgreSQL, Celery...)
sin tocar los servicios.
"""

from pathlib import Path
from typing import Callable, Protocol

import numpy as np

from app.dominio.modelos import Copa, Deteccion, InfoImagen, Resumen, Trabajo


class LectorImagen(Protocol):
    """Lee una imagen por ventanas. Se usa con `with`."""

    def info(self) -> InfoImagen:
        """Metadatos. Lanza ImagenInvalida si la imagen no sirve."""
        ...

    def leer_ventana(self, x0: int, y0: int, ancho: int, alto: int,
                     salida: tuple[int, int] | None = None) -> np.ndarray | None:
        """Devuelve la ventana como BGR uint8, o None si está vacía (nodata).

        Sin `salida`: tamaño (alto, ancho, 3), a la resolución original.
        Con `salida=(alto_px, ancho_px)`: la ventana se reduce (promedio) a ese tamaño,
        para trabajar a la resolución con que se entrenó el modelo.
        """
        ...

    def cerrar(self) -> None: ...

    def __enter__(self) -> "LectorImagen": ...

    def __exit__(self, *args) -> None: ...


class Segmentador(Protocol):
    nombres_clases: dict[int, str]

    def segmentar(self, imagen_bgr: np.ndarray) -> list[Deteccion]:
        """Polígonos en píxeles de la imagen recibida."""
        ...


class Exportador(Protocol):
    def exportar(self, copas: list[Copa], info: InfoImagen, ruta: Path) -> Resumen: ...


class RepositorioTrabajos(Protocol):
    def guardar(self, trabajo: Trabajo) -> None: ...

    def obtener(self, id_trabajo: str) -> Trabajo | None: ...

    def actualizar(self, id_trabajo: str, **campos) -> None: ...


class ArchivoSubido(Protocol):
    """Cualquier objeto con lectura asíncrona por partes (p. ej. UploadFile de FastAPI)."""

    async def read(self, size: int = -1) -> bytes: ...


class Almacenamiento(Protocol):
    async def guardar_subida(self, id_trabajo: str, archivo: ArchivoSubido,
                             extension: str, max_bytes: int) -> Path: ...

    def ruta_resultado(self, id_trabajo: str) -> Path: ...

    def eliminar(self, id_trabajo: str) -> None: ...


class Ejecutor(Protocol):
    """Corre tareas en segundo plano (hoy hilos; mañana Celery/RQ)."""

    def enviar(self, funcion: Callable, *args) -> None: ...

    def cerrar(self) -> None: ...
