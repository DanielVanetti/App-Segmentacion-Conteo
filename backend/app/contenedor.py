"""
Composition root: el ÚNICO lugar donde se eligen las clases concretas.
Para cambiar una pieza (otro modelo, PostgreSQL, Celery...) se cambia aquí.
"""

import logging
from dataclasses import dataclass, field
from typing import Callable

from app.adaptadores.almacenamiento_local import AlmacenamientoLocal
from app.adaptadores.archivos_proyecto_local import ArchivosProyectoLocal
from app.adaptadores.ejecutor_local import EjecutorLocal
from app.adaptadores.exportador_geojson import ExportadorGeoJSON
from app.adaptadores.lectores.fabrica import EXTENSIONES, abrir_lector
from app.adaptadores.lectores.inspector_raster import inspeccionar_geotiff
from app.adaptadores.repositorio_memoria import RepositorioMemoria
from app.adaptadores.repositorio_proyectos_memoria import RepositorioProyectosMemoria
from app.adaptadores.segmentador_yolo import SegmentadorYOLO
from app.config import Config
from app.dominio.puertos import RepositorioProyectos, Segmentador
from app.servicios.servicio_proyectos import ServicioProyectos
from app.servicios.servicio_trabajos import ParametrosPipeline, ServicioTrabajos
from app.servicios.validacion_ortomosaico import RangoResolucion

log = logging.getLogger(__name__)


@dataclass
class Contenedor:
    config: Config
    servicio: ServicioTrabajos
    proyectos: ServicioProyectos
    persistencia: str = "memoria"     # "postgis" o "memoria"
    _al_cerrar: list[Callable[[], None]] = field(default_factory=list)

    def cerrar(self) -> None:
        self.servicio.ejecutor.cerrar()
        for accion in self._al_cerrar:
            accion()


def _repositorio_proyectos(config: Config) -> tuple[RepositorioProyectos, str, list]:
    if not config.database_url:
        log.warning("Sin DATABASE_URL: los proyectos se guardan en memoria y se pierden al "
                    "reiniciar. Configure PostgreSQL/PostGIS (ver README).")
        return RepositorioProyectosMemoria(), "memoria", []
    # Import aquí: así las pruebas y el modo memoria no necesitan el driver de PostgreSQL.
    from sqlalchemy import create_engine
    from app.adaptadores.bd.repositorio_proyectos_postgis import RepositorioProyectosPostgis
    motor = create_engine(config.database_url, pool_pre_ping=True,
                          connect_args={"connect_timeout": 10})
    return RepositorioProyectosPostgis(motor), "postgis", [motor.dispose]


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
    repo, persistencia, al_cerrar = _repositorio_proyectos(config)
    proyectos = ServicioProyectos(
        repositorio=repo,
        archivos=ArchivosProyectoLocal(config.dir_datos),
        inspeccionar=inspeccionar_geotiff,
        rango=RangoResolucion(config.gsd_min, config.gsd_max),
        max_bytes=config.max_mb * 1024 * 1024,
    )
    return Contenedor(config=config, servicio=servicio, proyectos=proyectos,
                      persistencia=persistencia, _al_cerrar=al_cerrar)
