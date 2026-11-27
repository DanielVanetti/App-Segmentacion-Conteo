"""
Puertos = interfaces que el núcleo necesita.
Los adaptadores (app/adaptadores/) las implementan. El núcleo solo conoce estas
interfaces, así se puede cambiar una pieza (otro modelo, PostgreSQL, Celery...)
sin tocar los servicios.
"""

from pathlib import Path
from typing import Callable, Protocol

import numpy as np

from app.dominio.modelos import (Copa, Deteccion, Ejecucion, EstadoEjecucion, InfoImagen,
                                 MetadatosRaster, Ortomosaico, Proyecto, Resumen, Trabajo)


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


class RepositorioProyectos(Protocol):
    """Proyectos y sus ortomosaicos (RF-01, RF-02). Un ortomosaico por proyecto:
    cargar uno nuevo reemplaza al anterior."""

    def crear(self, proyecto: Proyecto) -> None: ...

    def listar(self) -> list[Proyecto]: ...

    def obtener(self, id_proyecto: str) -> Proyecto | None: ...

    def eliminar(self, id_proyecto: str) -> bool:
        """True si existía. Borra también su ortomosaico (en cascada)."""
        ...

    def guardar_ortomosaico(self, ortomosaico: Ortomosaico) -> None: ...

    def obtener_ortomosaico(self, id_proyecto: str) -> Ortomosaico | None: ...


class InspectorRaster(Protocol):
    def __call__(self, ruta: Path) -> MetadatosRaster:
        """Lee los metadatos sin leer los píxeles. Lanza ImagenInvalida si no se puede abrir."""
        ...


class ArchivosProyecto(Protocol):
    """Archivos grandes de cada proyecto (ortomosaico). Fuera de la base de datos."""

    async def guardar_temporal(self, archivo: ArchivoSubido, extension: str,
                               max_bytes: int) -> Path: ...

    def confirmar(self, id_proyecto: str, temporal: Path) -> Path:
        """Mueve el temporal a la carpeta del proyecto, reemplazando el anterior."""
        ...

    def descartar(self, temporal: Path) -> None: ...

    def eliminar_proyecto(self, id_proyecto: str) -> None: ...

    def ruta_resultado(self, id_proyecto: str, id_ejecucion: str) -> Path:
        """Dónde se escribe el GeoJSON de una ejecución (crea la carpeta)."""
        ...


class RepositorioEjecuciones(Protocol):
    """Cola y estado de las ejecuciones (DD-02: la cola es esta misma tabla).

    La API solo crea, consulta y pide cancelar. El procesador (otro proceso, DD-01) toma
    la siguiente en cola, informa el avance y la cierra. Un proyecto tiene como máximo
    una ejecución activa (en cola o ejecutando)."""

    def crear(self, ejecucion: Ejecucion) -> None:
        """Lanza Conflicto si el proyecto ya tiene una ejecución activa."""
        ...

    def obtener(self, id_ejecucion: str) -> Ejecucion | None: ...

    def listar(self, id_proyecto: str) -> list[Ejecucion]:
        """De la más reciente a la más antigua."""
        ...

    def activa(self, id_proyecto: str) -> Ejecucion | None: ...

    def ultimas(self) -> dict[str, Ejecucion]:
        """La ejecución más reciente de cada proyecto (para el estado del proyecto)."""
        ...

    def eliminar_proyecto(self, id_proyecto: str) -> None:
        """Borra las ejecuciones del proyecto (en PostGIS ya lo hace el ON DELETE CASCADE)."""
        ...

    def solicitar_cancelacion(self, id_ejecucion: str) -> Ejecucion | None:
        """En cola: queda cancelada al instante. Ejecutando: se marca y el procesador
        se detiene en el siguiente mosaico. Terminada: no cambia."""
        ...

    # --- lo usa el procesador ---
    def tomar_siguiente(self) -> Ejecucion | None:
        """Pasa la más antigua en cola a 'ejecutando' y la devuelve. Dos procesadores
        nunca toman la misma."""
        ...

    def avanzar(self, id_ejecucion: str, progreso: float, etapa: str,
                mosaico_actual: int | None = None,
                mosaicos_totales: int | None = None) -> bool:
        """Guarda el avance y renueva el latido. Devuelve False si hay que detenerse
        (cancelación pedida o la ejecución ya no existe)."""
        ...

    def anotar(self, id_ejecucion: str, nivel: str, mensaje: str) -> None:
        """Agrega una línea a la bitácora."""
        ...

    def terminar(self, id_ejecucion: str, estado: EstadoEjecucion, etapa: str,
                 copas_detectadas: int | None = None, copas_guardadas: int | None = None,
                 area_total_m2: float | None = None) -> None: ...

    def recuperar_interrumpidas(self, segundos_sin_latido: float) -> list[str]:
        """Marca como fallidas las que quedaron 'ejecutando' sin latido (el procesador
        se cayó). Devuelve sus ids."""
        ...
