"""
Composition root: el ÚNICO lugar donde se eligen las clases concretas.
Para cambiar una pieza (otro modelo, PostgreSQL, Celery...) se cambia aquí.
"""

from dataclasses import dataclass

from app.adaptadores.almacenamiento_local import AlmacenamientoLocal
from app.adaptadores.ejecutor_local import EjecutorLocal
from app.adaptadores.exportador_geojson import ExportadorGeoJSON
from app.adaptadores.lectores.fabrica import EXTENSIONES, abrir_lector
from app.adaptadores.repositorio_memoria import RepositorioMemoria
from app.adaptadores.segmentador_yolo import SegmentadorYOLO
from app.config import Config
from app.dominio.puertos import Segmentador
from app.servicios.servicio_trabajos import ParametrosPipeline, ServicioTrabajos


@dataclass
class Contenedor:
    config: Config
    servicio: ServicioTrabajos

    def cerrar(self) -> None:
        self.servicio.ejecutor.cerrar()


def construir(config: Config, segmentador: Segmentador | None = None) -> Contenedor:
    """`segmentador` se puede pasar desde las pruebas para no cargar YOLO."""
    if segmentador is None:
        segmentador = SegmentadorYOLO(config.ruta_modelo, config.imgsz,
                                      config.confianza_min, config.area_min_px,
                                      clases=config.clases)
    servicio = ServicioTrabajos(
        repositorio=RepositorioMemoria(),
        almacenamiento=AlmacenamientoLocal(config.dir_trabajos),
        ejecutor=EjecutorLocal(config.trabajadores),
        segmentador=segmentador,
        exportador=ExportadorGeoJSON(),
        abrir_lector=abrir_lector,
        extensiones=EXTENSIONES,
        parametros=ParametrosPipeline(config.tesela, config.traslape, config.simplificar_px,
                                      config.gsd_objetivo),
        max_bytes=config.max_mb * 1024 * 1024,
    )
    return Contenedor(config=config, servicio=servicio)
