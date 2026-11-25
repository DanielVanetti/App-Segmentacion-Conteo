"""Modelos de respuesta de la API (documentan Swagger y validan la salida)."""

from pydantic import BaseModel, ConfigDict

from app.dominio.modelos import EstadoTrabajo


class _Base(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class InfoImagenSalida(_Base):
    ancho: int
    alto: int
    bandas: int
    crs: str | None
    tam_pixel: tuple[float, float] | None


class ResumenSalida(_Base):
    conteo: int
    area_total_m2: float | None
    crs_origen: str | None
    aviso: str | None


class TrabajoCreado(BaseModel):
    id: str
    estado: EstadoTrabajo


class TrabajoSalida(_Base):
    id: str
    archivo: str
    estado: EstadoTrabajo
    progreso: float
    creado: str
    inicio: str | None
    fin: str | None
    error: str | None
    info: InfoImagenSalida
    resumen: ResumenSalida | None


class SaludSalida(BaseModel):
    ok: bool
    modelo: str
    clases: dict[int, str]
    tesela: int
    traslape: int
    imgsz: int
    formatos: list[str]
    clases_contadas: list[str] = []   # clases que se detectan y cuentan (las demás se ignoran)
    gsd_objetivo: float = 0.0         # m/px a la que se reescala el ortomosaico (0 = no reescala)
    persistencia: str = "memoria"     # "postgis" o "memoria" (proyectos)
