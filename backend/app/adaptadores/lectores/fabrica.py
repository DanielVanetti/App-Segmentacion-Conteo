"""
Elige el lector según la extensión del archivo.
Para soportar un formato nuevo basta con agregarlo a LECTORES (principio abierto/cerrado).
"""

from pathlib import Path

from app.adaptadores.lectores.lector_geotiff import LectorGeoTIFF
from app.adaptadores.lectores.lector_imagen_simple import LectorImagenSimple
from app.dominio.errores import ArchivoNoValido
from app.dominio.puertos import LectorImagen

LECTORES = {
    ".tif": LectorGeoTIFF,
    ".tiff": LectorGeoTIFF,
    ".png": LectorImagenSimple,   # previsto, aún no disponible
    ".jpg": LectorImagenSimple,
    ".jpeg": LectorImagenSimple,
}

EXTENSIONES = set(LECTORES)


def abrir_lector(ruta: Path) -> LectorImagen:
    clase = LECTORES.get(Path(ruta).suffix.lower())
    if clase is None:
        raise ArchivoNoValido(f"Formato no soportado: {Path(ruta).suffix}")
    return clase(ruta)
