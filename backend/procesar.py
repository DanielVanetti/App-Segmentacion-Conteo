r"""
Procesa un ortomosaico desde la consola, sin levantar la API.
Usa el mismo servicio y pipeline que la API.

Uso:
    .\.venv\Scripts\python.exe procesar.py C:\ruta\ortomosaico.tif
    .\.venv\Scripts\python.exe procesar.py C:\ruta\ortomosaico.tif -o copas.geojson
"""

import argparse
import sys
import time
from pathlib import Path

from app.config import Config
from app.contenedor import construir
from app.dominio.errores import ErrorDominio


def run() -> int:
    p = argparse.ArgumentParser(description="Segmenta copas de árboles en un GeoTIFF.")
    p.add_argument("imagen", type=Path, help="ruta del ortomosaico GeoTIFF")
    p.add_argument("-o", "--salida", type=Path,
                   help="GeoJSON de salida (por defecto: <nombre>_copas.geojson)")
    a = p.parse_args()

    if not a.imagen.exists():
        print(f"No existe el archivo: {a.imagen}")
        return 1
    salida = a.salida or a.imagen.with_name(a.imagen.stem + "_copas.geojson")

    config = Config.desde_entorno()
    print(f"Cargando modelo {config.ruta_modelo.name} ...")
    try:
        contenedor = construir(config)
    except FileNotFoundError as e:
        print(e)
        return 1

    activas = getattr(contenedor.servicio.segmentador, "clases_activas", None)
    print(f"Clases que se cuentan: {', '.join(activas) if activas else 'todas'}")
    if config.gsd_objetivo > 0:
        print(f"Resolución del modelo: {config.gsd_objetivo} m/px (el ortomosaico se reduce a esta resolución)")

    inicio = time.time()
    try:
        resumen = contenedor.servicio.procesar_archivo(
            a.imagen, salida,
            al_avanzar=lambda prog: print(f"\rProcesando teselas: {prog:6.1%}", end="", flush=True))
    except ErrorDominio as e:
        print(f"\nERROR: {e}")
        return 1
    finally:
        contenedor.cerrar()

    print(f"  ({time.time() - inicio:.0f} s)")
    print(f"Copas encontradas: {resumen.conteo}")
    if resumen.area_total_m2 is not None:
        print(f"Área total: {resumen.area_total_m2} m²")
    if resumen.aviso:
        print(resumen.aviso)
    print(f"CRS de origen: {resumen.crs_origen}")
    print(f"Resultado guardado en: {salida.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(run())
