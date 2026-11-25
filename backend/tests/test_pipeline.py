import json

import pytest

from app.adaptadores.exportador_geojson import ExportadorGeoJSON
from app.adaptadores.lectores.fabrica import abrir_lector
from app.dominio.errores import ArchivoNoValido, FormatoNoDisponible, ImagenInvalida
from app.servicios.pipeline import segmentar_imagen
from tests.conftest import LADO, TAM_PIXEL, SegmentadorFalso, crear_geotiff


def test_no_duplica_copas_en_el_traslape(geotiff):
    with abrir_lector(geotiff) as lector:
        copas = segmentar_imagen(lector, SegmentadorFalso(), 1024, 192)
    assert len(copas) == 2  # la copa A aparece en 2 teselas pero se cuenta una vez


def test_geojson_con_areas(geotiff, tmp_path):
    with abrir_lector(geotiff) as lector:
        info = lector.info()
        copas = segmentar_imagen(lector, SegmentadorFalso(), 1024, 192, simplificar_px=0.7)
    salida = tmp_path / "r.geojson"
    resumen = ExportadorGeoJSON().exportar(copas, info, salida)

    area_esperada = (LADO * TAM_PIXEL) ** 2
    assert resumen.conteo == 2
    assert resumen.area_total_m2 == pytest.approx(2 * area_esperada)
    g = json.loads(salida.read_text(encoding="utf-8"))
    assert len(g["features"]) == 2
    lon, lat = g["features"][0]["geometry"]["coordinates"][0][0]
    assert -86 < lon < -82 and 8 < lat < 12  # cae en Costa Rica


def test_sin_crs_se_rechaza(tmp_path):
    ruta = crear_geotiff(tmp_path / "sin_crs.tif", crs=None)
    with pytest.raises(ImagenInvalida):
        with abrir_lector(ruta) as lector:
            lector.info()


def test_png_previsto_pero_no_disponible(tmp_path):
    with pytest.raises(FormatoNoDisponible):
        abrir_lector(tmp_path / "foto.png")


def test_extension_desconocida(tmp_path):
    with pytest.raises(ArchivoNoValido):
        abrir_lector(tmp_path / "notas.txt")
