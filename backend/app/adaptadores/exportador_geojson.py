"""
Exporta las copas a GeoJSON en EPSG:4326.
Se escribe al disco copa por copa (no se arma un texto gigante en memoria).
"""

import json
from pathlib import Path

from rasterio.crs import CRS
from rasterio.warp import transform_geom
from shapely.geometry import mapping

from app.dominio.modelos import Copa, InfoImagen, Resumen

DECIMALES = 7  # en grados: ~1 cm, suficiente para copas


class ExportadorGeoJSON:
    def exportar(self, copas: list[Copa], info: InfoImagen, ruta: Path) -> Resumen:
        crs = CRS.from_user_input(info.crs) if info.crs else None
        proyectado = bool(crs and crs.is_projected)
        factor = crs.linear_units_factor[1] if proyectado else None  # metros por unidad

        areas = [round(c.poligono.area * factor * factor, 2) if proyectado else None for c in copas]
        resumen = Resumen(
            conteo=len(copas),
            area_total_m2=round(sum(areas), 2) if proyectado else None,
            crs_origen=info.crs,
            aviso=self._aviso(crs, proyectado),
        )

        temporal = ruta.with_suffix(".tmp")
        with open(temporal, "w", encoding="utf-8") as f:
            f.write('{"type":"FeatureCollection","resumen":')
            json.dump(resumen.__dict__, f, ensure_ascii=False)
            f.write(',"features":[')
            for i, (copa, area) in enumerate(zip(copas, areas), start=1):
                if i > 1:
                    f.write(",")
                geometria = mapping(copa.poligono)
                if crs is not None:
                    geometria = transform_geom(crs, "EPSG:4326", geometria, precision=DECIMALES)
                json.dump({
                    "type": "Feature",
                    "geometry": geometria,
                    "properties": {"id": i, "clase": copa.clase,
                                   "confianza": round(copa.confianza, 4), "area_m2": area},
                }, f)
            f.write("]}")
        temporal.replace(ruta)  # se publica completo o no se publica
        return resumen

    @staticmethod
    def _aviso(crs, proyectado: bool) -> str | None:
        if crs is None:
            return "Imagen sin georreferencia: coordenadas en píxeles y sin áreas."
        if not proyectado:
            return ("El CRS del ortomosaico no es proyectado: no se calcularon áreas. "
                    "Reproyecte a CRTM05 (EPSG:5367).")
        return None
