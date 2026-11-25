"""Endpoints de trabajos. Solo traducen HTTP <-> servicio; no tienen lógica de negocio."""

from pathlib import Path

from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse

from app.api.dependencias import obtener_servicio
from app.api.esquemas import TrabajoCreado, TrabajoSalida
from app.servicios.servicio_trabajos import ServicioTrabajos

router = APIRouter(prefix="/trabajos", tags=["trabajos"])


@router.post("", status_code=202, response_model=TrabajoCreado,
             summary="Subir un ortomosaico y encolar su procesamiento")
async def crear_trabajo(
    archivo: UploadFile = File(..., description="GeoTIFF (.tif/.tiff). PNG/JPG: próximamente."),
    servicio: ServicioTrabajos = Depends(obtener_servicio),
):
    try:
        trabajo = await servicio.crear(archivo.filename or "", archivo)
    finally:
        await archivo.close()
    return TrabajoCreado(id=trabajo.id, estado=trabajo.estado)


@router.get("/{id_trabajo}", response_model=TrabajoSalida, summary="Estado y resumen del trabajo")
def estado_trabajo(id_trabajo: str, servicio: ServicioTrabajos = Depends(obtener_servicio)):
    return servicio.obtener(id_trabajo)


@router.get(
    "/{id_trabajo}/resultado",
    summary="Descargar el GeoJSON (EPSG:4326) con las copas",
    response_class=FileResponse,
    responses={200: {"content": {"application/geo+json": {}},
                     "description": "Archivo GeoJSON para descargar"}},
)
def resultado_trabajo(id_trabajo: str, servicio: ServicioTrabajos = Depends(obtener_servicio)):
    ruta = servicio.ruta_resultado(id_trabajo)
    nombre = Path(servicio.obtener(id_trabajo).archivo).stem + "_copas.geojson"
    # Se envía como archivo (se lee del disco por partes). Swagger muestra "Download"
    # en lugar de intentar colorear un JSON enorme.
    return FileResponse(ruta, media_type="application/geo+json", filename=nombre)
