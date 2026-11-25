"""
Validación de un ortomosaico recién cargado (RF-03, RF-04). Lógica pura: recibe los
metadatos ya leídos y decide.

- INVALIDO  -> el archivo se rechaza (sin sistema de referencia, menos de 3 bandas).
- ADVERTENCIA -> se acepta, pero se avisa (resolución fuera del rango del modelo,
                 sistema de referencia geográfico o distinto de CRTM05).

Los mensajes van en español y dicen qué hacer (RNF-11).
"""

from dataclasses import dataclass

from app.dominio.modelos import MetadatosRaster, ResultadoValidacion, Validacion

V, A, I = ResultadoValidacion.VALIDO, ResultadoValidacion.ADVERTENCIA, ResultadoValidacion.INVALIDO
EPSG_CRTM05 = 5367


@dataclass(frozen=True)
class RangoResolucion:
    """Rango de tamaño de píxel (m/px) con que se puede usar el modelo."""
    minimo_m: float
    maximo_m: float


def validar(meta: MetadatosRaster, rango: RangoResolucion) -> Validacion:
    mensajes: list[str] = []

    # --- sistema de referencia
    if meta.crs is None:
        crs = I
        mensajes.append("El archivo no tiene sistema de referencia (no está georreferenciado). "
                        "Expórtelo de nuevo como GeoTIFF georreferenciado desde el software "
                        "de fotogrametría.")
    elif not meta.proyectado:
        crs = A
        mensajes.append(f"El sistema de referencia ({meta.crs}) está en grados: no se pueden "
                        "medir áreas en metros. Se recomienda reproyectarlo a CRTM05 (EPSG:5367).")
    elif meta.epsg != EPSG_CRTM05:
        crs = A
        mensajes.append(f"El sistema de referencia es {meta.crs}, no CRTM05 (EPSG:5367). Las "
                        "áreas se calculan en el sistema del archivo y el visor lo reproyecta.")
    else:
        crs = V

    # --- bandas (forman parte del formato: hace falta RGB)
    if meta.bandas < 3:
        formato = I
        mensajes.append(f"El ortomosaico tiene {meta.bandas} banda(s); se necesitan al menos 3 "
                        "(rojo, verde y azul). Use el ortomosaico a color.")
    else:
        formato = V

    # --- resolución (RF-04)
    if meta.gsd_m is None:
        resolucion = A
        if meta.crs is not None:
            mensajes.append("No se pudo verificar la resolución en metros porque el sistema de "
                            "referencia no es proyectado.")
    elif meta.gsd_m < rango.minimo_m or meta.gsd_m > rango.maximo_m:
        resolucion = A
        mensajes.append(
            f"La resolución es de {meta.gsd_m * 100:.1f} cm/píxel y el modelo se usa entre "
            f"{rango.minimo_m * 100:.1f} y {rango.maximo_m * 100:.1f} cm/píxel. Puede procesarlo, "
            "pero los resultados pueden ser menos confiables.")
    else:
        resolucion = V

    return Validacion(formato=formato, crs=crs, resolucion=resolucion, mensajes=tuple(mensajes))


def es_invalida(v: Validacion) -> bool:
    return I in (v.formato, v.crs, v.resolucion)
