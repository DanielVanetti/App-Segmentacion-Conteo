"""
Pipeline de segmentación: teselas -> segmentar -> quitar duplicados -> georreferenciar.
Solo conoce interfaces (LectorImagen, Segmentador): no sabe de HTTP, disco ni YOLO.

Escala: el modelo se entrena con teselas de `tesela` px a una resolución fija
(p. ej. 5 cm/px). Si el ortomosaico tiene otra resolución, cada ventana se lee
con un tamaño mayor y se reduce a `tesela` px, de modo que el modelo vea las copas
con el mismo tamaño que al entrenar. Los polígonos se devuelven a la escala original.
"""

import logging
from typing import Callable

import numpy as np
from shapely.affinity import affine_transform, scale, translate

from app.dominio.modelos import Copa, InfoImagen
from app.dominio.puertos import LectorImagen, Segmentador
from app.servicios.teselado import rejilla

log = logging.getLogger(__name__)

TOLERANCIA_ESCALA = 1.02  # por debajo de este factor no se reescala


def _rellenar(imagen: np.ndarray, tam: int) -> np.ndarray:
    """Completa con negro hasta tam x tam (mantiene la misma escala que al entrenar)."""
    alto, ancho = imagen.shape[:2]
    if alto == tam and ancho == tam:
        return imagen
    lienzo = np.zeros((tam, tam, 3), dtype=np.uint8)
    lienzo[:alto, :ancho] = imagen
    return lienzo


def factor_escala(info: InfoImagen, gsd_objetivo: float) -> float:
    """Cuántos píxeles de la imagen original caben en 1 px del modelo.

    1.0 = no se reescala. Un valor mayor que 1 significa que la imagen es más fina que la
    resolución del modelo y se reduce. No se amplía nunca una imagen más gruesa.
    """
    if gsd_objetivo <= 0:
        return 1.0
    if info.tam_pixel is None or not info.metros_por_unidad:
        log.warning("No se conoce el tamaño del píxel en metros (CRS no proyectado o sin CRS): "
                    "se procesa a la resolución original. Reproyecte a un CRS proyectado.")
        return 1.0
    gsd_original = info.tam_pixel[0] * info.metros_por_unidad
    f = gsd_objetivo / gsd_original
    if f <= TOLERANCIA_ESCALA:
        if f < 1 / TOLERANCIA_ESCALA:
            log.warning("El ortomosaico (%.3f m/px) es más grueso que la resolución del modelo "
                        "(%.3f m/px): no se amplía, los resultados pueden ser peores.",
                        gsd_original, gsd_objetivo)
        return 1.0
    return f


def segmentar_imagen(
    lector: LectorImagen,
    segmentador: Segmentador,
    tesela: int,
    traslape: int,
    simplificar_px: float = 0.0,
    al_avanzar: Callable[[float], None] | None = None,
    gsd_objetivo: float = 0.0,
) -> list[Copa]:
    """`tesela`, `traslape` y `simplificar_px` están en píxeles DEL MODELO (a `gsd_objetivo`)."""
    info = lector.info()
    f = factor_escala(info, gsd_objetivo)
    # Ventana en píxeles de la imagen original (si f = 1 es igual a `tesela`).
    tam_origen = max(1, round(tesela * f))
    traslape_origen = min(round(traslape * f), tam_origen - 1)
    ventanas = rejilla(info.ancho, info.alto, tam_origen, traslape_origen)
    # (a, b, c, d, e, f) de rasterio -> [a, b, d, e, c, f] de shapely
    matriz = None
    if info.transform is not None:
        a, b, c, d, e, f_ = info.transform
        matriz = [a, b, d, e, c, f_]

    copas: list[Copa] = []
    for n, v in enumerate(ventanas, start=1):
        salida = None
        if f > 1:
            salida = (min(tesela, max(1, round(v.alto / f))),
                      min(tesela, max(1, round(v.ancho / f))))
        imagen = lector.leer_ventana(v.x0, v.y0, v.ancho, v.alto, salida) if salida \
            else lector.leer_ventana(v.x0, v.y0, v.ancho, v.alto)
        if imagen is not None:
            for det in segmentador.segmentar(_rellenar(imagen, tesela)):
                poligono = det.poligono
                if salida is not None:  # de píxeles del modelo a píxeles de la imagen original
                    poligono = scale(poligono, v.ancho / salida[1], v.alto / salida[0],
                                     origin=(0, 0))
                poligono = translate(poligono, v.x0, v.y0)  # px de la imagen completa
                centro = poligono.centroid
                if not v.contiene(centro.x, centro.y):
                    continue  # le pertenece a otra tesela
                if simplificar_px > 0:
                    poligono = poligono.simplify(simplificar_px * f, preserve_topology=True)
                if matriz is not None:
                    poligono = affine_transform(poligono, matriz)
                copas.append(Copa(poligono, det.confianza, det.clase))
        if al_avanzar:
            al_avanzar(round(n / len(ventanas), 3))
    return copas
