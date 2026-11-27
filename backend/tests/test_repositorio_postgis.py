"""
Repositorio de proyectos contra PostgreSQL/PostGIS real.

Se salta si no hay base de pruebas. Para correrlo:
    $env:DATABASE_URL_PRUEBAS = "postgresql+psycopg://copas:copas_local@127.0.0.1:5434/copas_pruebas"
    .\\.venv\\Scripts\\python.exe -m pytest tests/test_repositorio_postgis.py -q

OJO: la prueba BORRA las tablas de esa base. Use una base exclusiva para pruebas.
"""

import os
from dataclasses import replace

import pytest

URL = os.getenv("DATABASE_URL_PRUEBAS")
pytestmark = pytest.mark.skipif(not URL, reason="sin DATABASE_URL_PRUEBAS")


@pytest.fixture
def repo():
    from alembic import command
    from alembic.config import Config as ConfigAlembic
    from sqlalchemy import create_engine, text

    from app.adaptadores.bd.repositorio_proyectos_postgis import RepositorioProyectosPostgis

    motor = create_engine(URL, connect_args={"connect_timeout": 10})
    with motor.begin() as cx:
        cx.execute(text("DROP TABLE IF EXISTS ejecucion, ortomosaico, proyecto, alembic_version CASCADE"))
    cfg = ConfigAlembic(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location",
                        os.path.join(os.path.dirname(__file__), "..", "migraciones"))
    cfg.attributes["url"] = URL
    command.upgrade(cfg, "head")   # prueba también la migración
    yield RepositorioProyectosPostgis(motor)
    motor.dispose()


def _orto(id_proyecto, id_orto="o1", epsg=5367):
    from app.dominio.modelos import (Extension, MetadatosRaster, Ortomosaico,
                                     ResultadoValidacion as R, Validacion)
    meta = MetadatosRaster(ancho=200, alto=100, bandas=3, tipo_dato="uint8",
                           crs=f"EPSG:{epsg}", epsg=epsg, proyectado=True, gsd_m=0.05,
                           extension_nativa=Extension(360000, 1149995, 360010, 1150000),
                           extension_crtm05=Extension(360000, 1149995, 360010, 1150000))
    val = Validacion(R.VALIDO, R.ADVERTENCIA, R.VALIDO, ("aviso",))
    return Ortomosaico(id=id_orto, proyecto_id=id_proyecto, nombre_archivo="orto.tif",
                       ruta="/datos/orto.tif", tamano_bytes=1234, metadatos=meta, validacion=val)


def test_ciclo_completo(repo):
    from app.dominio.modelos import Proyecto
    p = Proyecto(id="p1", nombre="Parcela", sitio="Santa Cruz", fecha_vuelo="2026-03-14")
    repo.crear(p)
    leido = repo.obtener("p1")
    assert leido.nombre == "Parcela" and leido.fecha_vuelo == "2026-03-14"
    assert leido.ortomosaico_id is None
    assert [x.id for x in repo.listar()] == ["p1"]

    repo.guardar_ortomosaico(_orto("p1"))
    o = repo.obtener_ortomosaico("p1")
    assert o.metadatos.extension_nativa.max_x == pytest.approx(360010)
    assert o.validacion.crs.value == "advertencia" and o.validacion.mensajes == ("aviso",)
    assert repo.obtener("p1").ortomosaico_id == "o1"

    # reemplazo: sigue habiendo uno solo
    repo.guardar_ortomosaico(replace(_orto("p1", "o2"), tamano_bytes=99))
    assert repo.obtener_ortomosaico("p1").id == "o2"

    assert repo.eliminar("p1") is True
    assert repo.obtener("p1") is None and repo.obtener_ortomosaico("p1") is None
    assert repo.eliminar("p1") is False


def test_huella_guarda_el_srid_de_origen(repo):
    from sqlalchemy import text
    from app.dominio.modelos import Proyecto
    repo.crear(Proyecto(id="p2", nombre="UTM"))
    repo.guardar_ortomosaico(_orto("p2", epsg=32616))
    with repo._motor.connect() as cx:
        srid = cx.execute(text("SELECT ST_SRID(huella) FROM ortomosaico")).scalar()
    assert srid == 32616


# --- ejecuciones: la cola en PostgreSQL (DD-02) ----------------------------------------
@pytest.fixture
def repo_ej(repo):
    from app.adaptadores.bd.repositorio_ejecuciones_postgis import RepositorioEjecucionesPostgis
    from app.dominio.modelos import Proyecto
    for pid in ("pa", "pb"):
        repo.crear(Proyecto(id=pid, nombre=pid))
        repo.guardar_ortomosaico(_orto(pid, id_orto=f"o-{pid}"))
    return RepositorioEjecucionesPostgis(repo._motor)


def _ej(id_ej, pid="pa"):
    from app.dominio.modelos import Ejecucion, EntradaBitacora, ParametrosEjecucion
    return Ejecucion(id=id_ej, proyecto_id=pid, ortomosaico_id=f"o-{pid}",
                     parametros=ParametrosEjecucion(traslape_pct=15),
                     bitacora=[EntradaBitacora("2026-01-01T00:00:00+00:00", "info", "en cola")])


def test_cola_completa(repo_ej):
    from app.dominio.errores import Conflicto
    from app.dominio.modelos import EstadoEjecucion as E

    repo_ej.crear(_ej("e1"))
    with pytest.raises(Conflicto):           # índice único parcial: una activa por proyecto
        repo_ej.crear(_ej("e2"))
    assert repo_ej.activa("pa").id == "e1" and repo_ej.activa("pb") is None

    e = repo_ej.tomar_siguiente()
    assert e.id == "e1" and e.estado == E.EJECUTANDO and e.iniciado_en
    assert e.parametros.traslape_pct == 15
    assert repo_ej.tomar_siguiente() is None

    assert repo_ej.avanzar("e1", 0.5, "Detectando copas", 3, 10) is True
    repo_ej.anotar("e1", "info", "hola")
    repo_ej.terminar("e1", E.COMPLETADO, "Terminado", copas_detectadas=7, copas_guardadas=9,
                     area_total_m2=12.5)
    e = repo_ej.obtener("e1")
    assert (e.estado, e.progreso, e.mosaico_actual, e.mosaicos_totales) == (E.COMPLETADO, 1.0, 3, 10)
    assert e.copas_detectadas == 7 and [b.mensaje for b in e.bitacora] == ["en cola", "hola"]
    # terminar otra vez no cambia una ejecución cerrada
    repo_ej.terminar("e1", E.FALLIDO, "Falló")
    assert repo_ej.obtener("e1").estado == E.COMPLETADO

    repo_ej.crear(_ej("e3"))                 # ya no hay activa: se puede lanzar otra
    assert [x.id for x in repo_ej.listar("pa")][0] == "e3"
    assert repo_ej.ultimas()["pa"].id == "e3"


def test_cancelacion(repo_ej):
    from app.dominio.modelos import EstadoEjecucion as E

    repo_ej.crear(_ej("a", "pa"))
    repo_ej.tomar_siguiente()
    repo_ej.crear(_ej("b", "pb"))

    b = repo_ej.solicitar_cancelacion("b")    # en cola: inmediato
    assert b.estado == E.CANCELADO and b.finalizado_en
    a = repo_ej.solicitar_cancelacion("a")    # ejecutando: se marca
    assert a.estado == E.EJECUTANDO and a.cancelacion_solicitada and a.etapa == "Cancelando"
    assert repo_ej.avanzar("a", 0.6, "Detectando copas") is False
    assert repo_ej.obtener("a").etapa == "Cancelando"
    assert repo_ej.avanzar("no-existe", 0.1, "x") is False
    assert repo_ej.tomar_siguiente() is None  # la cancelada en cola no se toma


def test_interrumpidas_y_cascada(repo, repo_ej):
    from app.dominio.modelos import EstadoEjecucion as E

    repo_ej.crear(_ej("x"))
    repo_ej.tomar_siguiente()
    assert repo_ej.recuperar_interrumpidas(3600) == []
    assert repo_ej.recuperar_interrumpidas(0) == ["x"]
    assert repo_ej.obtener("x").estado == E.FALLIDO

    repo.eliminar("pa")                        # ON DELETE CASCADE
    assert repo_ej.obtener("x") is None
