"""
Esquemas de proyectos y ortomosaicos. Siguen el contrato del frontend
(frontend/src/shared/api/types.ts): JSON en camelCase.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from app.dominio.modelos import Ejecucion, EstadoEjecucion, Extension, Ortomosaico, Proyecto


class _Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


EstadoProyecto = Literal["sin_ortomosaico", "ortomosaico_cargado", "procesando", "completado",
                         "error_georreferencia"]
ResultadoValidacion = Literal["valido", "advertencia", "invalido"]


# --- entrada ------------------------------------------------------------------
class NuevoProyecto(_Camel):
    nombre: str = Field(..., description="Obligatorio.", examples=["Parcela 10 — ECA"])
    descripcion: str = ""
    sitio: str = Field("", examples=["Santa Cruz, Guanacaste"])
    fecha_vuelo: str | None = Field(None, description="AAAA-MM-DD", examples=["2026-03-14"])


# --- salida -------------------------------------------------------------------
class ProyectoSalida(_Camel):
    id: str
    nombre: str
    descripcion: str
    sitio: str
    fecha_vuelo: str | None
    creado_en: str
    actualizado_en: str
    estado: EstadoProyecto
    ortomosaico_id: str | None
    total_copas: int | None = None      # de la última detección completada
    url_miniatura: str | None = None

    @classmethod
    def desde(cls, p: Proyecto, ultima: Ejecucion | None = None) -> "ProyectoSalida":
        """El estado sale del ortomosaico y de la última ejecución. Una detección hecha
        sobre un ortomosaico anterior ya no cuenta como resultado del proyecto."""
        estado, total = ("ortomosaico_cargado" if p.ortomosaico_id else "sin_ortomosaico"), None
        if ultima and ultima.estado.activa:
            estado = "procesando"
        elif (ultima and ultima.estado == EstadoEjecucion.COMPLETADO
              and ultima.ortomosaico_id == p.ortomosaico_id):
            estado, total = "completado", ultima.copas_detectadas
        return cls(id=p.id, nombre=p.nombre, descripcion=p.descripcion, sitio=p.sitio,
                   fecha_vuelo=p.fecha_vuelo, creado_en=p.creado_en,
                   actualizado_en=p.actualizado_en, estado=estado,
                   ortomosaico_id=p.ortomosaico_id, total_copas=total)


class ExtensionSalida(_Camel):
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @classmethod
    def desde(cls, e: Extension | None) -> "ExtensionSalida | None":
        return cls(min_x=e.min_x, min_y=e.min_y, max_x=e.max_x, max_y=e.max_y) if e else None


class ValidacionSalida(_Camel):
    formato: ResultadoValidacion
    crs: ResultadoValidacion
    resolucion: ResultadoValidacion
    mensajes: list[str]


class OrtomosaicoSalida(_Camel):
    id: str
    proyecto_id: str
    nombre_archivo: str
    tamano_bytes: int
    formato: Literal["GeoTIFF", "COG"]
    crs: str | None
    resolucion_cm_por_pixel: float | None
    extension: ExtensionSalida | None = Field(None, description="Envolvente en EPSG:5367.")
    extension_nativa: ExtensionSalida | None = Field(None, description="En el CRS del archivo.")
    ancho_px: int
    alto_px: int
    bandas: int
    tipo_dato: str
    url_cog: str
    validacion: ValidacionSalida
    vuelo: None = None                 # metadatos EXIF del vuelo: pendiente
    subido_en: str

    @classmethod
    def desde(cls, o: Ortomosaico, url_cog: str) -> "OrtomosaicoSalida":
        m, v = o.metadatos, o.validacion
        return cls(
            id=o.id, proyecto_id=o.proyecto_id, nombre_archivo=o.nombre_archivo,
            tamano_bytes=o.tamano_bytes, formato=o.formato, crs=m.crs,
            resolucion_cm_por_pixel=round(m.gsd_m * 100, 3) if m.gsd_m else None,
            extension=ExtensionSalida.desde(m.extension_crtm05),
            extension_nativa=ExtensionSalida.desde(m.extension_nativa),
            ancho_px=m.ancho, alto_px=m.alto, bandas=m.bandas, tipo_dato=m.tipo_dato,
            url_cog=url_cog,
            validacion=ValidacionSalida(formato=v.formato.value, crs=v.crs.value,
                                        resolucion=v.resolucion.value, mensajes=list(v.mensajes)),
            subido_en=o.subido_en,
        )


class RespuestaError(BaseModel):
    """Cuerpo de todos los errores (RNF-11): mensaje para la persona usuaria y,
    opcionalmente, un detalle técnico que no se muestra."""
    mensaje: str
    detalle: str | None = None
