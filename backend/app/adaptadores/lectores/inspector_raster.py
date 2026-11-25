"""Lee los metadatos de un GeoTIFF con rasterio, sin leer los píxeles (RF-02)."""

from pathlib import Path

import rasterio
from rasterio.errors import RasterioIOError
from rasterio.warp import transform_bounds

from app.dominio.errores import ImagenInvalida
from app.dominio.modelos import Extension, MetadatosRaster

CRS_VISOR = "EPSG:5367"


def inspeccionar_geotiff(ruta: Path) -> MetadatosRaster:
    try:
        ds = rasterio.open(ruta)
    except RasterioIOError as e:
        raise ImagenInvalida(
            "No se pudo leer el archivo como GeoTIFF. Puede estar dañado o incompleto: "
            "expórtelo de nuevo y vuelva a cargarlo.") from e
    with ds:
        crs = ds.crs
        nativa = Extension(*ds.bounds) if crs else None
        crtm05 = None
        if crs:
            try:
                crtm05 = Extension(*transform_bounds(crs, CRS_VISOR, *ds.bounds, densify_pts=21))
            except Exception:
                crtm05 = None   # CRS que no se puede reproyectar: el visor no podrá ubicarlo
        proyectado = bool(crs and crs.is_projected)
        gsd = None
        if proyectado:
            metros = crs.linear_units_factor[1]
            gsd = abs(ds.res[0]) * metros
        return MetadatosRaster(
            ancho=ds.width, alto=ds.height, bandas=ds.count, tipo_dato=ds.dtypes[0],
            crs=crs.to_string() if crs else None,
            epsg=crs.to_epsg() if crs else None,
            proyectado=proyectado, gsd_m=gsd,
            extension_nativa=nativa, extension_crtm05=crtm05,
        )
