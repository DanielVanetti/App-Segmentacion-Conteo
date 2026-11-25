"""Segmentador con Ultralytics YOLO (seg). El modelo se carga una sola vez."""

import logging
import threading
from pathlib import Path

import numpy as np
from shapely.geometry import Polygon
from shapely.validation import make_valid

from app.dominio.modelos import Deteccion

log = logging.getLogger(__name__)


def resolver_ids_clases(nombres_clases: dict[int, str], clases: tuple[str, ...]) -> list[int] | None:
    """Convierte nombres de clase (p. ej. ("arbol",)) en los ids del modelo.

    Devuelve None (= no filtrar, se aceptan todas las clases) si no se pidió ninguna
    o si ninguna coincide con las del modelo (p. ej. un modelo viejo con la clase 'tree').
    """
    if not clases:
        return None
    por_nombre = {nombre: i for i, nombre in nombres_clases.items()}
    ids = [por_nombre[c] for c in clases if c in por_nombre]
    faltan = [c for c in clases if c not in por_nombre]
    if faltan:
        log.warning("El modelo no tiene la(s) clase(s) %s (tiene: %s).",
                    faltan, list(nombres_clases.values()))
    if not ids:
        log.warning("Ninguna clase pedida existe en el modelo: no se filtra por clase.")
        return None
    return ids


class SegmentadorYOLO:
    def __init__(self, ruta_modelo: Path, imgsz: int, confianza_min: float, area_min_px: float,
                 clases: tuple[str, ...] = ()):
        from ultralytics import YOLO  # import aquí: es pesado y solo lo necesita este adaptador

        if not Path(ruta_modelo).exists():
            raise FileNotFoundError(f"No se encontró el modelo en {ruta_modelo}")
        self._modelo = YOLO(str(ruta_modelo))
        if self._modelo.task != "segment":
            raise ValueError(f"El modelo es de tipo '{self._modelo.task}', se esperaba 'segment'")
        self.nombres_clases: dict[int, str] = dict(self._modelo.names)
        self.ruta_modelo = Path(ruta_modelo)
        self._imgsz = imgsz
        self._conf = confianza_min
        self._area_min = area_min_px
        # Solo se detectan (y se cuentan) estas clases; las demás (p. ej. 'grupo') se ignoran.
        self._ids_clases = resolver_ids_clases(self.nombres_clases, clases)
        self.clases_activas: list[str] = (
            [self.nombres_clases[i] for i in self._ids_clases]
            if self._ids_clases is not None else list(self.nombres_clases.values()))
        self._candado = threading.Lock()  # Ultralytics no es seguro entre hilos

    def segmentar(self, imagen_bgr: np.ndarray) -> list[Deteccion]:
        with self._candado:
            r = self._modelo.predict(imagen_bgr, imgsz=self._imgsz, conf=self._conf,
                                     classes=self._ids_clases,
                                     retina_masks=True, verbose=False)[0]
        if r.masks is None:
            return []

        detecciones = []
        for puntos, conf, cls in zip(r.masks.xy, r.boxes.conf.tolist(), r.boxes.cls.tolist()):
            if self._ids_clases is not None and int(cls) not in self._ids_clases:
                continue  # por si acaso: nunca dejar pasar una clase no pedida
            poligono = self._a_poligono(puntos)
            if poligono is not None:
                detecciones.append(Deteccion(poligono, float(conf), self.nombres_clases[int(cls)]))
        return detecciones

    def _a_poligono(self, puntos: np.ndarray) -> Polygon | None:
        """Convierte el contorno de la máscara en un polígono válido (o None si no sirve)."""
        if len(puntos) < 3:
            return None
        p = Polygon(puntos)
        if not p.is_valid:
            p = make_valid(p)
            if p.geom_type != "Polygon":
                partes = [g for g in getattr(p, "geoms", []) if g.geom_type == "Polygon"]
                if not partes:
                    return None
                p = max(partes, key=lambda g: g.area)  # nos quedamos con la parte más grande
        if p.is_empty or p.area < self._area_min:
            return None
        return p
