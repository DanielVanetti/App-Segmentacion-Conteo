"""
Archivos de los proyectos en disco local (RNF-13, RNF-15):

    <dir_datos>/proyectos/<id_proyecto>/ortomosaico.tif
    <dir_datos>/proyectos/<id_proyecto>/ejecuciones/<id_ejecucion>.geojson
    <dir_datos>/temporales/<uuid>.tif      (mientras se valida la subida)

La subida se escribe primero en `temporales/` y solo se mueve al proyecto si es válida,
así un archivo malo no borra el ortomosaico anterior.
"""

import os
import shutil
import uuid
from pathlib import Path

from app.adaptadores.almacenamiento_local import copiar_por_partes
from app.dominio.puertos import ArchivoSubido


class ArchivosProyectoLocal:
    def __init__(self, dir_datos: Path):
        self._proyectos = Path(dir_datos) / "proyectos"
        self._temporales = Path(dir_datos) / "temporales"
        self._proyectos.mkdir(parents=True, exist_ok=True)
        self._temporales.mkdir(parents=True, exist_ok=True)

    async def guardar_temporal(self, archivo: ArchivoSubido, extension: str,
                               max_bytes: int) -> Path:
        ruta = self._temporales / f"{uuid.uuid4()}{extension}"
        try:
            await copiar_por_partes(archivo, ruta, max_bytes)
        except Exception:
            self.descartar(ruta)
            raise
        return ruta

    def confirmar(self, id_proyecto: str, temporal: Path) -> Path:
        carpeta = self._proyectos / id_proyecto
        carpeta.mkdir(parents=True, exist_ok=True)
        destino = carpeta / f"ortomosaico{temporal.suffix.lower()}"
        for anterior in carpeta.glob("ortomosaico.*"):
            anterior.unlink()
        os.replace(temporal, destino)
        return destino

    def descartar(self, temporal: Path) -> None:
        Path(temporal).unlink(missing_ok=True)

    def eliminar_proyecto(self, id_proyecto: str) -> None:
        shutil.rmtree(self._proyectos / id_proyecto, ignore_errors=True)

    def ruta_resultado(self, id_proyecto: str, id_ejecucion: str) -> Path:
        carpeta = self._proyectos / id_proyecto / "ejecuciones"
        carpeta.mkdir(parents=True, exist_ok=True)
        return carpeta / f"{id_ejecucion}.geojson"
