from fastapi import APIRouter, Depends

from app.api.dependencias import obtener_contenedor
from app.api.esquemas import SaludSalida
from app.contenedor import Contenedor

router = APIRouter(tags=["salud"])


@router.get("/salud", response_model=SaludSalida, summary="¿La API y el modelo están listos?")
def salud(contenedor: Contenedor = Depends(obtener_contenedor)):
    cfg, servicio = contenedor.config, contenedor.servicio
    return SaludSalida(
        ok=True,
        modelo=cfg.ruta_modelo.name,
        clases=servicio.segmentador.nombres_clases,
        tesela=cfg.tesela,
        traslape=cfg.traslape,
        imgsz=cfg.imgsz,
        formatos=sorted(servicio.extensiones),
        clases_contadas=getattr(servicio.segmentador, "clases_activas",
                                list(servicio.segmentador.nombres_clases.values())),
        gsd_objetivo=cfg.gsd_objetivo,
    )
