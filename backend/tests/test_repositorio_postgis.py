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
        cx.execute(text("DROP TABLE IF EXISTS ortomosaico, proyecto, alembic_version CASCADE"))
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
