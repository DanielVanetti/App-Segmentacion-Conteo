"""Objetos del dominio. No dependen de FastAPI, rasterio ni Ultralytics."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from shapely.geometry import Polygon


def ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class EstadoTrabajo(str, Enum):
    EN_COLA = "en cola"
    PROCESANDO = "procesando"
    TERMINADO = "terminado"
    ERROR = "error"


@dataclass(frozen=True)
class InfoImagen:
    ancho: int
    alto: int
    bandas: int
    crs: str | None = None                       # p. ej. "EPSG:5367"; None = sin georreferencia
    transform: tuple[float, ...] | None = None   # (a, b, c, d, e, f) píxel -> CRS
    tam_pixel: tuple[float, float] | None = None   # tamaño del píxel en unidades del CRS
    metros_por_unidad: float | None = None         # metros por unidad del CRS (None si no es proyectado)


@dataclass(frozen=True)
class Deteccion:
    """Lo que devuelve el segmentador: polígono en píxeles de la tesela."""
    poligono: Polygon
    confianza: float
    clase: str


@dataclass(frozen=True)
class Copa:
    """Detección final: polígono en coordenadas del CRS (o en píxeles si no hay CRS)."""
    poligono: Polygon
    confianza: float
    clase: str


@dataclass(frozen=True)
class Resumen:
    conteo: int
    area_total_m2: float | None
    crs_origen: str | None
    aviso: str | None = None


@dataclass
class Trabajo:
    id: str
    archivo: str
    info: InfoImagen
    estado: EstadoTrabajo = EstadoTrabajo.EN_COLA
    progreso: float = 0.0
    creado: str = field(default_factory=ahora)
    inicio: str | None = None
    fin: str | None = None
    error: str | None = None
    resumen: Resumen | None = None
