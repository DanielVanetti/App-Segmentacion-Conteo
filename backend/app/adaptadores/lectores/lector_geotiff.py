"""Lector de GeoTIFF con rasterio. Lee siempre por ventanas, nunca la imagen completa."""

from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.errors import RasterioIOError
from rasterio.windows import Window

from app.dominio.errores import ImagenInvalida
from app.dominio.modelos import InfoImagen

LADO_MUESTRA = 2048  # tamaño de la versión reducida para calcular percentiles


class LectorGeoTIFF:
    def __init__(self, ruta: Path):
        try:
            self._ds = rasterio.open(ruta)
        except RasterioIOError as e:
            raise ImagenInvalida("El archivo no es un GeoTIFF válido") from e
        self._limites: list[tuple[float, float]] | None = None
        self._limites_calculados = False

    # --- interfaz LectorImagen ---------------------------------------------
    def info(self) -> InfoImagen:
        ds = self._ds
        if ds.crs is None:
            raise ImagenInvalida("El GeoTIFF no tiene CRS (no está georreferenciado)")
        if ds.count < 3:
            raise ImagenInvalida(f"Se esperaban al menos 3 bandas (RGB), tiene {ds.count}")
        return InfoImagen(
            ancho=ds.width, alto=ds.height, bandas=ds.count,
            crs=ds.crs.to_string(),
            transform=tuple(ds.transform)[:6],
            tam_pixel=(abs(ds.res[0]), abs(ds.res[1])),
            metros_por_unidad=ds.crs.linear_units_factor[1] if ds.crs.is_projected else None,
        )

    def leer_ventana(self, x0: int, y0: int, ancho: int, alto: int,
                     salida: tuple[int, int] | None = None) -> np.ndarray | None:
        ventana = Window(x0, y0, ancho, alto)
        if salida is None:
            mascara = self._ds.dataset_mask(window=ventana)
            if not mascara.any():
                return None  # tesela vacía (nodata)
            bloque = self._ds.read([1, 2, 3], window=ventana)
        else:
            # Se lee directamente reducida (promedio): evita cargar la ventana a resolución completa.
            mascara = self._ds.dataset_mask(window=ventana, out_shape=salida)
            if not mascara.any():
                return None
            bloque = self._ds.read([1, 2, 3], window=ventana, out_shape=(3, *salida),
                                   resampling=Resampling.average)
        rgb = self._a_8bits(bloque)
        rgb[:, mascara == 0] = 0
        # (3, alto, ancho) RGB -> (alto, ancho, 3) BGR, que es lo que espera Ultralytics
        return np.ascontiguousarray(np.transpose(rgb, (1, 2, 0))[:, :, ::-1])

    def cerrar(self) -> None:
        self._ds.close()

    def __enter__(self) -> "LectorGeoTIFF":
        return self

    def __exit__(self, *args) -> None:
        self.cerrar()

    # --- conversión a 8 bits -------------------------------------------------
    def _a_8bits(self, bloque: np.ndarray) -> np.ndarray:
        limites = self._percentiles()
        if limites is None:
            return bloque.astype(np.uint8, copy=False)
        salida = np.empty(bloque.shape, dtype=np.uint8)
        for b, (lo, hi) in enumerate(limites):
            salida[b] = np.clip((bloque[b].astype(np.float32) - lo) / (hi - lo) * 255, 0, 255)
        return salida

    def _percentiles(self) -> list[tuple[float, float]] | None:
        """Percentiles 2-98 por banda, calculados UNA vez sobre una versión reducida
        de toda la imagen (así el color no cambia de una tesela a otra).
        Si ya es de 8 bits no se toca."""
        if self._limites_calculados:
            return self._limites
        self._limites_calculados = True
        ds = self._ds
        if ds.dtypes[0] == "uint8":
            return None
        escala = max(1.0, max(ds.width, ds.height) / LADO_MUESTRA)
        forma = (max(1, int(ds.height / escala)), max(1, int(ds.width / escala)))
        datos = ds.read([1, 2, 3], out_shape=(3, *forma), resampling=Resampling.average)
        mascara = ds.dataset_mask(out_shape=forma) > 0
        limites = []
        for b in range(3):
            valores = datos[b][mascara] if mascara.any() else datos[b].ravel()
            lo, hi = np.percentile(valores, [2, 98])
            limites.append((float(lo), float(hi if hi > lo else lo + 1)))
        self._limites = limites
        return limites
