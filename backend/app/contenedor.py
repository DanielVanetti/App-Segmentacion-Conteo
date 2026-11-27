"""
Composition root: el ÚNICO lugar donde se eligen las clases concretas.
Para cambiar una pieza (otro modelo, PostgreSQL, Celery...) se cambia aquí.
"""

import logging
import threading
from dataclasses import dataclass, field
from typing import Callable

from app.adaptadores.almacenamiento_local import AlmacenamientoLocal
from app.adaptadores.archivos_proyecto_local import ArchivosProyectoLocal
from app.adaptadores.ejecutor_local import EjecutorLocal
from app.adaptadores.exportador_geojson import ExportadorGeoJSON
from app.adaptadores.lectores.fabrica import EXTENSIONES, abrir_lector
from app.adaptadores.lectores.inspector_raster import inspeccionar_geotiff
from app.adaptadores.repositorio_ejecuciones_memoria import RepositorioEjecucionesMemoria
from app.adaptadores.repositorio_memoria import RepositorioMemoria
from app.adaptadores.repositorio_proyectos_memoria import RepositorioProyectosMemoria
from app.adaptadores.segmentador_yolo import SegmentadorYOLO
from app.config import Config
from app.dominio.puertos import RepositorioEjecuciones, RepositorioProyectos, Segmentador
from app.servicios.procesador import AjustesProcesador, Procesador
from app.servicios.servicio_ejecuciones import ServicioEjecuciones
from app.servicios.servicio_proyectos import ServicioProyectos
from app.servicios.servicio_trabajos import ParametrosPipeline, ServicioTrabajos
from app.servicios.validacion_ortomosaico import RangoResolucion

log = logging.getLogger(__name__)


@dataclass
class Contenedor:
    config: Config
    servicio: ServicioTrabajos
    proyectos: ServicioProyectos
    ejecuciones: ServicioEjecuciones
    persistencia: str = "memoria"     # "postgis" o "memoria"
    procesador: Procesador | None = None   # solo si corre integrado en la API
    _al_cerrar: list[Callable[[], None]] = field(default_factory=list)

    def cerrar(self) -> None:
        self.servicio.ejecutor.cerrar()
        for accion in self._al_cerrar:
            accion()


@dataclass
class Repositorios:
    proyectos: RepositorioProyectos
    ejecuciones: RepositorioEjecuciones
    persistencia: str
    al_cerrar: list[Callable[[], None]]


def construir_repositorios(config: Config) -> Repositorios:
    if not config.database_url:
        log.warning("Sin DATABASE_URL: proyectos y ejecuciones se guardan en memoria y se "
                    "pierden al reiniciar. Configure PostgreSQL/PostGIS (ver README).")
        return Repositorios(RepositorioProyectosMemoria(), RepositorioEjecucionesMemoria(),
                            "memoria", [])
    # Import aquí: así las pruebas y el modo memoria no necesitan el driver de PostgreSQL.
    from sqlalchemy import create_engine
    from app.adaptadores.bd.repositorio_ejecuciones_postgis import RepositorioEjecucionesPostgis
    from app.adaptadores.bd.repositorio_proyectos_postgis import RepositorioProyectosPostgis
    motor = create_engine(config.database_url, pool_pre_ping=True,
                          connect_args={"connect_timeout": 10})
    return Repositorios(RepositorioProyectosPostgis(motor), RepositorioEjecucionesPostgis(motor),
                        "postgis", [motor.dispose])


def construir_segmentador(config: Config) -> Segmentador:
    return SegmentadorYOLO(config.ruta_modelo, config.imgsz, config.confianza_min,
                           config.area_min_px, clases=config.clases)


def construir_procesador(config: Config, repos: Repositorios, segmentador: Segmentador,
                         archivos: ArchivosProyectoLocal) -> Procesador:
    return Procesador(
        ejecuciones=repos.ejecuciones, proyectos=repos.proyectos, archivos=archivos,
        segmentador=segmentador, exportador=ExportadorGeoJSON(), abrir_lector=abrir_lector,
        ajustes=AjustesProcesador(simplificar_px=config.simplificar_px,
                                  gsd_objetivo=config.gsd_objetivo,
                                  confianza_modelo=config.confianza_min,
                                  espera_s=config.espera_cola_s,
                                  interrupcion_s=config.interrupcion_s))


def _arrancar_en_hilo(procesador: Procesador) -> Callable[[], None]:
    hilo = threading.Thread(target=procesador.ciclo, name="procesador", daemon=True)
    hilo.start()

    def detener() -> None:
        procesador.detener.set()
        hilo.join(timeout=10)
    return detener


def construir(config: Config, segmentador: Segmentador | None = None) -> Contenedor:
    """`segmentador` se puede pasar desde las pruebas para no cargar YOLO."""
    if segmentador is None:
        segmentador = construir_segmentador(config)
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
    repos = construir_repositorios(config)
    archivos = ArchivosProyectoLocal(config.dir_datos)
    proyectos = ServicioProyectos(
        repositorio=repos.proyectos,
        archivos=archivos,
        inspeccionar=inspeccionar_geotiff,
        rango=RangoResolucion(config.gsd_min, config.gsd_max),
        max_bytes=config.max_mb * 1024 * 1024,
        ejecuciones=repos.ejecuciones,
    )
    ejecuciones = ServicioEjecuciones(repos.ejecuciones, repos.proyectos, archivos,
                                      tesela_modelo=config.tesela,
                                      confianza_modelo=config.confianza_min)

    al_cerrar: list[Callable[[], None]] = []
    procesador = None
    integrado = config.procesador_integrado
    if not integrado and repos.persistencia == "memoria":
        log.warning("PROCESADOR_INTEGRADO=0 necesita DATABASE_URL (la cola vive en la base); "
                    "sin base de datos el procesador corre dentro de la API.")
        integrado = True
    if integrado:
        procesador = construir_procesador(config, repos, segmentador, archivos)
        al_cerrar.append(_arrancar_en_hilo(procesador))
    else:
        log.info("Procesador externo: ejecute `python -m app.procesador` para atender la cola.")
    al_cerrar += repos.al_cerrar   # el motor se cierra después de detener el procesador

    return Contenedor(config=config, servicio=servicio, proyectos=proyectos,
                      ejecuciones=ejecuciones, persistencia=repos.persistencia,
                      procesador=procesador, _al_cerrar=al_cerrar)
