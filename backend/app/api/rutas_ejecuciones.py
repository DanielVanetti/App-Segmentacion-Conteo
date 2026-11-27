"""
Endpoints de las ejecuciones de detección (RF-06 a RF-12), bajo cada proyecto. En el
frontend se llaman "trabajos" (`/api/proyectos/{id}/trabajos`).

La API no procesa: deja la ejecución en la cola y responde 202. El avance se consulta
por sondeo con GET.
"""

from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.api.dependencias import obtener_ejecuciones
from app.api.esquemas_ejecuciones import ParametrosInferencia, TrabajoInferenciaSalida
from app.api.esquemas_proyectos import RespuestaError
from app.api.rutas_proyectos import PREFIJO
from app.servicios.servicio_ejecuciones import ServicioEjecuciones

router = APIRouter(prefix=f"{PREFIJO}/proyectos/{{id_proyecto}}/trabajos", tags=["ejecuciones"])
ERRORES = {c: {"model": RespuestaError} for c in (404, 409, 422)}


def _salida(e) -> TrabajoInferenciaSalida:
    url = f"{PREFIJO}/proyectos/{e.proyecto_id}/trabajos/{e.id}/resultado"
    return TrabajoInferenciaSalida.desde(e, url)


@router.post("", status_code=202, response_model=TrabajoInferenciaSalida, responses=ERRORES,
             summary="Lanzar la detección de copas",
             description="Deja la ejecución en cola y responde de inmediato. 409 si el "
                         "proyecto no tiene ortomosaico o ya tiene una detección en curso.")
def lanzar(id_proyecto: str, parametros: ParametrosInferencia | None = None,
           servicio: ServicioEjecuciones = Depends(obtener_ejecuciones)):
    parametros = parametros or ParametrosInferencia()
    return _salida(servicio.lanzar(id_proyecto, parametros.a_dominio()))


@router.get("", response_model=list[TrabajoInferenciaSalida], responses={404: ERRORES[404]},
            summary="Historial de ejecuciones del proyecto (la más reciente primero)")
def listar(id_proyecto: str, servicio: ServicioEjecuciones = Depends(obtener_ejecuciones)):
    return [_salida(e) for e in servicio.listar(id_proyecto)]


@router.get("/{id_trabajo}", response_model=TrabajoInferenciaSalida,
            responses={404: ERRORES[404]}, summary="Estado y avance de una ejecución")
def obtener(id_proyecto: str, id_trabajo: str,
            servicio: ServicioEjecuciones = Depends(obtener_ejecuciones)):
    return _salida(servicio.obtener(id_proyecto, id_trabajo))


@router.post("/{id_trabajo}/cancelacion", response_model=TrabajoInferenciaSalida,
             responses={404: ERRORES[404]}, summary="Cancelar una ejecución",
             description="Si está en cola se cancela al instante. Si se está ejecutando, se "
                         "detiene al terminar el mosaico en curso: `cancelacionSolicitada` "
                         "pasa a true y el estado cambia a `cancelado` poco después.")
def cancelar(id_proyecto: str, id_trabajo: str,
             servicio: ServicioEjecuciones = Depends(obtener_ejecuciones)):
    return _salida(servicio.cancelar(id_proyecto, id_trabajo))


@router.get("/{id_trabajo}/resultado", response_class=FileResponse,
            responses={404: ERRORES[404], 409: ERRORES[409],
                       200: {"content": {"application/geo+json": {}}}},
            summary="Descargar las copas detectadas (GeoJSON, EPSG:4326)")
def resultado(id_proyecto: str, id_trabajo: str,
              servicio: ServicioEjecuciones = Depends(obtener_ejecuciones)):
    ruta: Path = servicio.ruta_resultado(id_proyecto, id_trabajo)
    return FileResponse(ruta, media_type="application/geo+json",
                        filename=f"copas_{id_trabajo[:8]}.geojson")
