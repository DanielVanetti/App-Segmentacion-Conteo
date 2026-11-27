"""
Casos de uso de proyectos y ortomosaicos (RF-01 a RF-04).
Solo depende de los puertos: no sabe si los datos viven en PostGIS o en memoria.
"""

import uuid
from datetime import date
from pathlib import Path

from app.dominio import errores
from app.dominio.modelos import Ejecucion, Ortomosaico, Proyecto
from app.dominio.puertos import (ArchivoSubido, ArchivosProyecto, InspectorRaster,
                                 RepositorioEjecuciones, RepositorioProyectos)
from app.servicios.validacion_ortomosaico import RangoResolucion, es_invalida, validar

EXTENSIONES_ORTOMOSAICO = {".tif", ".tiff"}
EXTENSIONES_PREVISTAS = {".png", ".jpg", ".jpeg"}   # aún no soportadas (415)
LARGO_MAX_TEXTO = 200


class ServicioProyectos:
    def __init__(self, repositorio: RepositorioProyectos, archivos: ArchivosProyecto,
                 inspeccionar: InspectorRaster, rango: RangoResolucion, max_bytes: int,
                 ejecuciones: RepositorioEjecuciones | None = None):
        self.repositorio = repositorio
        self.ejecuciones = ejecuciones
        self.archivos = archivos
        self.inspeccionar = inspeccionar
        self.rango = rango
        self.max_bytes = max_bytes

    # --- proyectos -------------------------------------------------------------
    def crear(self, nombre: str, descripcion: str = "", sitio: str = "",
              fecha_vuelo: str | None = None) -> Proyecto:
        nombre = (nombre or "").strip()
        if not nombre:
            raise errores.DatosNoValidos("El nombre del proyecto es obligatorio.")
        if len(nombre) > LARGO_MAX_TEXTO or len(sitio or "") > LARGO_MAX_TEXTO:
            raise errores.DatosNoValidos(
                f"El nombre y el sitio admiten como máximo {LARGO_MAX_TEXTO} caracteres.")
        if fecha_vuelo:
            try:
                fecha_vuelo = date.fromisoformat(fecha_vuelo).isoformat()
            except ValueError:
                raise errores.DatosNoValidos(
                    "La fecha de vuelo debe tener el formato AAAA-MM-DD.") from None
        proyecto = Proyecto(id=str(uuid.uuid4()), nombre=nombre,
                            descripcion=(descripcion or "").strip(), sitio=(sitio or "").strip(),
                            fecha_vuelo=fecha_vuelo or None)
        self.repositorio.crear(proyecto)
        return proyecto

    def listar(self) -> list[Proyecto]:
        return self.repositorio.listar()

    def obtener(self, id_proyecto: str) -> Proyecto:
        proyecto = self.repositorio.obtener(id_proyecto)
        if proyecto is None:
            raise errores.ProyectoNoEncontrado("El proyecto solicitado no existe.")
        return proyecto

    def ultimas_ejecuciones(self) -> dict[str, Ejecucion]:
        """La ejecución más reciente de cada proyecto, para mostrar su estado."""
        return self.ejecuciones.ultimas() if self.ejecuciones else {}

    def _sin_ejecucion_activa(self, id_proyecto: str, accion: str) -> None:
        if self.ejecuciones and self.ejecuciones.activa(id_proyecto):
            raise errores.Conflicto(f"No se puede {accion} mientras hay una detección en "
                                    "curso. Espere a que termine o cancélela.")

    def eliminar(self, id_proyecto: str) -> None:
        self.obtener(id_proyecto)
        self._sin_ejecucion_activa(id_proyecto, "eliminar el proyecto")
        if not self.repositorio.eliminar(id_proyecto):
            raise errores.ProyectoNoEncontrado("El proyecto solicitado no existe.")
        if self.ejecuciones:
            self.ejecuciones.eliminar_proyecto(id_proyecto)
        self.archivos.eliminar_proyecto(id_proyecto)

    # --- ortomosaico -----------------------------------------------------------
    async def cargar_ortomosaico(self, id_proyecto: str, nombre_archivo: str,
                                 archivo: ArchivoSubido) -> Ortomosaico:
        """Guarda el archivo, lo valida y, si sirve, lo asocia al proyecto (reemplaza al
        anterior). Si es inválido se borra y se lanza ImagenInvalida con el motivo."""
        self.obtener(id_proyecto)   # 404 antes de recibir gigas
        self._sin_ejecucion_activa(id_proyecto, "cambiar el ortomosaico")
        extension = Path(nombre_archivo or "").suffix.lower()
        if extension in EXTENSIONES_PREVISTAS:
            raise errores.FormatoNoDisponible(
                "Por ahora solo se aceptan ortomosaicos GeoTIFF (.tif). Exporte el "
                "ortomosaico en ese formato.")
        if extension not in EXTENSIONES_ORTOMOSAICO:
            raise errores.ArchivoNoValido(
                f"El archivo «{nombre_archivo}» no es un GeoTIFF. Cargue un archivo .tif o .tiff.")

        temporal = await self.archivos.guardar_temporal(archivo, extension, self.max_bytes)
        try:
            metadatos = self.inspeccionar(temporal)
            validacion = validar(metadatos, self.rango)
            if es_invalida(validacion):
                raise errores.ImagenInvalida(" ".join(validacion.mensajes))
            tamano = temporal.stat().st_size
        except Exception:
            self.archivos.descartar(temporal)
            raise

        ruta = self.archivos.confirmar(id_proyecto, temporal)
        ortomosaico = Ortomosaico(id=str(uuid.uuid4()), proyecto_id=id_proyecto,
                                  nombre_archivo=Path(nombre_archivo).name, ruta=str(ruta),
                                  tamano_bytes=tamano, metadatos=metadatos,
                                  validacion=validacion)
        self.repositorio.guardar_ortomosaico(ortomosaico)
        return ortomosaico

    def obtener_ortomosaico(self, id_proyecto: str) -> Ortomosaico:
        self.obtener(id_proyecto)
        orto = self.repositorio.obtener_ortomosaico(id_proyecto)
        if orto is None:
            raise errores.OrtomosaicoNoEncontrado("El proyecto no tiene un ortomosaico cargado.")
        return orto

    def ruta_ortomosaico(self, id_proyecto: str) -> Path:
        ruta = Path(self.obtener_ortomosaico(id_proyecto).ruta)
        if not ruta.exists():
            raise errores.OrtomosaicoNoEncontrado(
                "El archivo del ortomosaico ya no está en el servidor. Cárguelo de nuevo.")
        return ruta

