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


# --- Proyectos y ortomosaicos (RF-01 a RF-04) ----------------------------------

class ResultadoValidacion(str, Enum):
    VALIDO = "valido"
    ADVERTENCIA = "advertencia"
    INVALIDO = "invalido"


@dataclass(frozen=True)
class Validacion:
    """Resultado de revisar formato, sistema de referencia y resolución (RF-03, RF-04).
    Si algo es INVALIDO el archivo se rechaza; las ADVERTENCIAS se guardan y se muestran."""
    formato: ResultadoValidacion
    crs: ResultadoValidacion
    resolucion: ResultadoValidacion
    mensajes: tuple[str, ...] = ()


@dataclass(frozen=True)
class Extension:
    """Envolvente [min_x, min_y, max_x, max_y]."""
    min_x: float
    min_y: float
    max_x: float
    max_y: float


@dataclass(frozen=True)
class MetadatosRaster:
    """Lo que se lee del archivo al cargarlo, sin leer los píxeles."""
    ancho: int
    alto: int
    bandas: int
    tipo_dato: str
    crs: str | None              # p. ej. "EPSG:5367"
    epsg: int | None
    proyectado: bool
    gsd_m: float | None          # tamaño de píxel en metros (None si el CRS no es proyectado)
    extension_nativa: Extension | None    # en el CRS del archivo
    extension_crtm05: Extension | None    # en EPSG:5367, para el visor


@dataclass
class Ortomosaico:
    id: str
    proyecto_id: str
    nombre_archivo: str
    ruta: str
    tamano_bytes: int
    metadatos: MetadatosRaster
    validacion: Validacion
    formato: str = "GeoTIFF"
    subido_en: str = field(default_factory=ahora)


@dataclass
class Proyecto:
    id: str
    nombre: str
    descripcion: str = ""
    sitio: str = ""
    fecha_vuelo: str | None = None   # ISO 8601 (solo fecha)
    creado_en: str = field(default_factory=ahora)
    actualizado_en: str = field(default_factory=ahora)
    # Se completa al leer; no se guarda en la tabla de proyectos.
    ortomosaico_id: str | None = None
