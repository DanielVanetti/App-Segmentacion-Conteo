"""
Esquemas de las ejecuciones (trabajos de inferencia). Siguen el contrato del frontend
(`TrabajoInferencia` y `ParametrosInferencia` en frontend/src/shared/api/types.ts).
"""

from typing import Literal

from pydantic import Field

from app.api.esquemas_proyectos import _Camel
from app.dominio.modelos import Ejecucion, ParametrosEjecucion

EstadoTrabajo = Literal["en_cola", "ejecutando", "completado", "fallido", "cancelado"]
NivelBitacora = Literal["info", "advertencia", "error"]


class ParametrosInferencia(_Camel):
    tamano_mosaico_px: int = Field(1024, description="Lado del mosaico en píxeles del modelo. "
                                   "Debe coincidir con el usado al entrenar.")
    traslape_pct: float = Field(20, description="Traslape entre mosaicos, en porcentaje.")
    confianza_minima: float = Field(0.5, description="Umbral para el conteo. Se guardan "
                                    "también las de menor confianza (DD-05).")
    area_minima_m2: float = Field(1.5, description="Se descartan las copas más pequeñas.")

    def a_dominio(self) -> ParametrosEjecucion:
        return ParametrosEjecucion(self.tamano_mosaico_px, self.traslape_pct,
                                   self.confianza_minima, self.area_minima_m2)


class EntradaBitacoraSalida(_Camel):
    momento: str
    nivel: NivelBitacora
    mensaje: str


class TrabajoInferenciaSalida(_Camel):
    id: str
    proyecto_id: str
    ortomosaico_id: str
    estado: EstadoTrabajo
    progreso: int = Field(description="Porcentaje de avance, 0 a 100.")
    etapa: str
    mosaico_actual: int
    mosaicos_totales: int
    parametros: ParametrosInferencia
    creado_en: str
    iniciado_en: str | None
    finalizado_en: str | None
    copas_detectadas: int | None = Field(description="Copas con confianza ≥ confianzaMinima.")
    copas_guardadas: int | None = Field(description="Todas las del resultado.")
    area_total_m2: float | None
    cancelacion_solicitada: bool
    url_resultado: str | None = Field(description="GeoJSON en EPSG:4326, si terminó.")
    bitacora: list[EntradaBitacoraSalida]

    @classmethod
    def desde(cls, e: Ejecucion, url_resultado: str) -> "TrabajoInferenciaSalida":
        p = e.parametros
        return cls(
            id=e.id, proyecto_id=e.proyecto_id, ortomosaico_id=e.ortomosaico_id,
            estado=e.estado.value, progreso=round(e.progreso * 100), etapa=e.etapa,
            mosaico_actual=e.mosaico_actual, mosaicos_totales=e.mosaicos_totales,
            parametros=ParametrosInferencia(tamano_mosaico_px=p.tamano_mosaico_px,
                                            traslape_pct=p.traslape_pct,
                                            confianza_minima=p.confianza_minima,
                                            area_minima_m2=p.area_minima_m2),
            creado_en=e.creado_en, iniciado_en=e.iniciado_en, finalizado_en=e.finalizado_en,
            copas_detectadas=e.copas_detectadas, copas_guardadas=e.copas_guardadas,
            area_total_m2=e.area_total_m2, cancelacion_solicitada=e.cancelacion_solicitada,
            url_resultado=url_resultado if e.estado.value == "completado" else None,
            bitacora=[EntradaBitacoraSalida(momento=b.momento, nivel=b.nivel, mensaje=b.mensaje)
                      for b in e.bitacora],
        )
