"""
Endpoints de proyectos y ortomosaicos (RF-01 a RF-04). Prefijo /api, que es la base que
usa el frontend (VITE_API_URL=/api).
"""

from fastapi import APIRouter, Depends, File, Response, UploadFile
from fastapi.responses import FileResponse

from app.api.dependencias import obtener_proyectos
from app.api.esquemas_proyectos import (NuevoProyecto, OrtomosaicoSalida, ProyectoSalida,
                                        RespuestaError)
from app.servicios.servicio_proyectos import ServicioProyectos

PREFIJO = "/api"
router = APIRouter(prefix=f"{PREFIJO}/proyectos", tags=["proyectos"])

ERRORES = {c: {"model": RespuestaError} for c in (404, 413, 415, 422)}


def _url_archivo(id_proyecto: str) -> str:
    return f"{PREFIJO}/proyectos/{id_proyecto}/ortomosaico/archivo"


# --- proyectos (RF-01) ----------------------------------------------------------
@router.get("", response_model=list[ProyectoSalida], summary="Listar proyectos")
def listar(servicio: ServicioProyectos = Depends(obtener_proyectos)):
    return [ProyectoSalida.desde(p) for p in servicio.listar()]


@router.post("", status_code=201, response_model=ProyectoSalida,
             responses={422: ERRORES[422]}, summary="Crear un proyecto")
def crear(datos: NuevoProyecto, servicio: ServicioProyectos = Depends(obtener_proyectos)):
    p = servicio.crear(datos.nombre, datos.descripcion, datos.sitio, datos.fecha_vuelo)
    return ProyectoSalida.desde(p)


@router.get("/{id_proyecto}", response_model=ProyectoSalida, responses={404: ERRORES[404]},
            summary="Obtener un proyecto")
def obtener(id_proyecto: str, servicio: ServicioProyectos = Depends(obtener_proyectos)):
    return ProyectoSalida.desde(servicio.obtener(id_proyecto))


@router.delete("/{id_proyecto}", status_code=204, responses={404: ERRORES[404]},
               summary="Eliminar un proyecto y sus archivos")
def eliminar(id_proyecto: str, servicio: ServicioProyectos = Depends(obtener_proyectos)):
    servicio.eliminar(id_proyecto)
    return Response(status_code=204)


# --- ortomosaico (RF-02 a RF-04) ------------------------------------------------
@router.post("/{id_proyecto}/ortomosaico", status_code=201, response_model=OrtomosaicoSalida,
             responses=ERRORES,
             summary="Cargar el ortomosaico (GeoTIFF) del proyecto",
             description="Se valida formato, sistema de referencia, bandas y resolución. "
                         "Si es inválido se rechaza (422) y no se guarda; si solo tiene "
                         "advertencias se guarda y se devuelven en `validacion`. "
                         "Cargar otro reemplaza al anterior.")
async def cargar_ortomosaico(
    id_proyecto: str,
    archivo: UploadFile = File(..., description="GeoTIFF (.tif/.tiff)"),
    servicio: ServicioProyectos = Depends(obtener_proyectos),
):
    try:
        orto = await servicio.cargar_ortomosaico(id_proyecto, archivo.filename or "", archivo)
    finally:
        await archivo.close()
    return OrtomosaicoSalida.desde(orto, _url_archivo(id_proyecto))


@router.get("/{id_proyecto}/ortomosaico", response_model=OrtomosaicoSalida,
            responses={404: ERRORES[404]}, summary="Metadatos y validación del ortomosaico")
def obtener_ortomosaico(id_proyecto: str,
                        servicio: ServicioProyectos = Depends(obtener_proyectos)):
    return OrtomosaicoSalida.desde(servicio.obtener_ortomosaico(id_proyecto),
                                   _url_archivo(id_proyecto))


@router.get("/{id_proyecto}/ortomosaico/archivo", response_class=FileResponse,
            responses={404: ERRORES[404], 200: {"content": {"image/tiff": {}}}},
            summary="Descargar el ortomosaico (admite peticiones por rangos)",
            description="Admite el encabezado Range, así el visor puede leer solo la parte "
                        "visible cuando el archivo sea un COG.")
def archivo_ortomosaico(id_proyecto: str,
                        servicio: ServicioProyectos = Depends(obtener_proyectos)):
    ruta = servicio.ruta_ortomosaico(id_proyecto)
    return FileResponse(ruta, media_type="image/tiff")
