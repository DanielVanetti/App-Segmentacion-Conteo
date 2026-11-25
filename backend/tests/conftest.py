"""Utilidades compartidas por las pruebas."""

import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from shapely.geometry import box

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.dominio.modelos import Deteccion  # noqa: E402

TAM_PIXEL = 0.1  # m
# Dos "copas" blancas de 40x40 px. La A cae en el traslape de dos teselas.
COPAS = [(900, 100), (2000, 1000)]  # (x, y) esquina superior izquierda
LADO = 40


class SegmentadorFalso:
    """Sustituye a YOLO: devuelve el recuadro de los píxeles blancos de la tesela."""
    nombres_clases = {0: "tree"}

    def segmentar(self, imagen_bgr: np.ndarray) -> list[Deteccion]:
        filas, cols = np.where(imagen_bgr[:, :, 0] == 255)
        if len(filas) == 0:
            return []
        poligono = box(cols.min(), filas.min(), cols.max() + 1, filas.max() + 1)
        return [Deteccion(poligono, 0.9, "tree")]


def crear_geotiff(ruta: Path, crs: str | None = "EPSG:5367", ancho=2500, alto=1800) -> Path:
    datos = np.zeros((3, alto, ancho), dtype=np.uint8)
    for x, y in COPAS:
        datos[:, y:y + LADO, x:x + LADO] = 255
    perfil = dict(driver="GTiff", width=ancho, height=alto, count=3, dtype="uint8",
                  transform=from_origin(470000, 1100000, TAM_PIXEL, TAM_PIXEL))
    if crs:
        perfil["crs"] = crs
    with rasterio.open(ruta, "w", **perfil) as d:
        d.write(datos)
    return ruta


@pytest.fixture
def geotiff(tmp_path) -> Path:
    return crear_geotiff(tmp_path / "orto.tif")
