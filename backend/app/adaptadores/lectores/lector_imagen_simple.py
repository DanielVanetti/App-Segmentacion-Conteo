"""
Lector para PNG/JPG (imágenes sin georreferencia).

AÚN NO IMPLEMENTADO: queda como punto de expansión. Para activarlo:
  1. Abrir la imagen (Pillow u OpenCV) en __init__.
  2. info(): devolver InfoImagen(ancho, alto, bandas=3, crs=None, transform=None).
     Con crs=None el pipeline deja los polígonos en píxeles y el exportador no calcula áreas.
  3. leer_ventana(): recortar y devolver BGR uint8.
  4. Quitar el `raise` de __init__.
Ojo: un PNG/JPG grande sí se carga completo en memoria (no hay lectura por ventanas).
"""

from pathlib import Path

import numpy as np

from app.dominio.errores import FormatoNoDisponible
from app.dominio.modelos import InfoImagen


class LectorImagenSimple:
    def __init__(self, ruta: Path):
        raise FormatoNoDisponible(
            "La segmentación en PNG/JPG aún no está disponible. Use un GeoTIFF (.tif).")

    def info(self) -> InfoImagen:
        raise NotImplementedError

    def leer_ventana(self, x0: int, y0: int, ancho: int, alto: int,
                     salida: tuple[int, int] | None = None) -> np.ndarray | None:
        raise NotImplementedError

    def cerrar(self) -> None:
        pass

    def __enter__(self) -> "LectorImagenSimple":
        return self

    def __exit__(self, *args) -> None:
        self.cerrar()
