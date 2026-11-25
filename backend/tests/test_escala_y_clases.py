"""Pruebas de la reducción a la resolución del modelo y del filtro de clases."""

import pytest

from app.adaptadores.lectores.fabrica import abrir_lector
from app.adaptadores.segmentador_yolo import resolver_ids_clases
from app.config import Config
from app.dominio.modelos import InfoImagen
from app.servicios.pipeline import factor_escala, segmentar_imagen
from tests.conftest import LADO, TAM_PIXEL, SegmentadorFalso


def _info(tam_pixel_m, metros_por_unidad=1.0):
    return InfoImagen(100, 100, 3, crs="EPSG:5367", tam_pixel=(tam_pixel_m, tam_pixel_m),
                      metros_por_unidad=metros_por_unidad)


# --- factor de escala ---------------------------------------------------------
def test_factor_escala_reduce_si_la_imagen_es_mas_fina():
    assert factor_escala(_info(0.0122), 0.05) == pytest.approx(0.05 / 0.0122)


def test_factor_escala_no_amplia_ni_toca_si_ya_coincide():
    assert factor_escala(_info(0.05), 0.05) == 1.0
    assert factor_escala(_info(0.10), 0.05) == 1.0   # más gruesa: no se amplía
    assert factor_escala(_info(0.0122), 0) == 1.0    # desactivado


def test_factor_escala_sin_metros_no_reescala():
    assert factor_escala(_info(0.0122, metros_por_unidad=None), 0.05) == 1.0


# --- el pipeline da el mismo resultado a otra resolución -----------------------
def test_reescalar_mantiene_conteo_y_area(geotiff):
    # El GeoTIFF de prueba tiene 0.1 m/px: con objetivo 0.2 m/px se reduce a la mitad.
    with abrir_lector(geotiff) as lector:
        copas = segmentar_imagen(lector, SegmentadorFalso(), 512, 96, gsd_objetivo=2 * TAM_PIXEL)
    assert len(copas) == 2                      # sin duplicar en el traslape
    area_esperada = (LADO * TAM_PIXEL) ** 2     # 16 m2 por copa
    for c in copas:                             # coordenadas ya en el CRS (metros)
        assert c.poligono.area == pytest.approx(area_esperada, rel=0.05)


def test_sin_reescalar_sigue_igual(geotiff):
    with abrir_lector(geotiff) as lector:
        copas = segmentar_imagen(lector, SegmentadorFalso(), 1024, 192)
    assert len(copas) == 2


# --- filtro de clases ------------------------------------------------------------
def test_ids_de_clases_ignora_grupo():
    nombres = {0: "arbol", 1: "grupo"}
    assert resolver_ids_clases(nombres, ("arbol",)) == [0]
    assert resolver_ids_clases(nombres, ("arbol", "grupo")) == [0, 1]
    assert resolver_ids_clases(nombres, ()) is None            # sin filtro


def test_modelo_viejo_sin_la_clase_pedida_no_filtra():
    assert resolver_ids_clases({0: "tree"}, ("arbol",)) is None


# --- configuración --------------------------------------------------------------------
def test_config_por_defecto(monkeypatch):
    for v in ("GSD_OBJETIVO", "CLASES"):
        monkeypatch.delenv(v, raising=False)
    cfg = Config.desde_entorno()
    assert cfg.gsd_objetivo == 0.05 and cfg.clases == ("arbol",)


def test_config_desde_entorno(monkeypatch):
    monkeypatch.setenv("GSD_OBJETIVO", "0.03")
    monkeypatch.setenv("CLASES", "arbol, grupo")
    cfg = Config.desde_entorno()
    assert cfg.gsd_objetivo == 0.03 and cfg.clases == ("arbol", "grupo")
