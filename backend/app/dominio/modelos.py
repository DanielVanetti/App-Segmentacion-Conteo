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


# --- Ejecuciones de detección (RF-06 a RF-12; DD-01, DD-02) -----------------------

class EstadoEjecucion(str, Enum):
    EN_COLA = "en_cola"
    EJECUTANDO = "ejecutando"
    COMPLETADO = "completado"
    FALLIDO = "fallido"
    CANCELADO = "cancelado"

    @property
    def activa(self) -> bool:
        return self in (EstadoEjecucion.EN_COLA, EstadoEjecucion.EJECUTANDO)


@dataclass(frozen=True)
class ParametrosEjecucion:
    tamano_mosaico_px: int = 1024
    traslape_pct: float = 20.0
    # Umbral inicial: se guarda todo lo que supera el mínimo del modelo y este valor solo
    # decide el conteo; se puede mover después sin reprocesar (DD-05, RF-16).
    confianza_minima: float = 0.5
    area_minima_m2: float = 1.5


@dataclass(frozen=True)
class EntradaBitacora:
    momento: str
    nivel: str          # "info" | "advertencia" | "error"
    mensaje: str


@dataclass
class Ejecucion:
    id: str
    proyecto_id: str
    ortomosaico_id: str
    parametros: ParametrosEjecucion
    estado: EstadoEjecucion = EstadoEjecucion.EN_COLA
    progreso: float = 0.0              # 0 a 1
    etapa: str = "En cola"
    mosaico_actual: int = 0
    mosaicos_totales: int = 0
    creado_en: str = field(default_factory=ahora)
    iniciado_en: str | None = None
    finalizado_en: str | None = None
    copas_detectadas: int | None = None   # las que pasan el umbral y el área mínima
    copas_guardadas: int | None = None    # todas las del resultado (DD-05)
    area_total_m2: float | None = None
    cancelacion_solicitada: bool = False
    bitacora: list[EntradaBitacora] = field(default_factory=list)
