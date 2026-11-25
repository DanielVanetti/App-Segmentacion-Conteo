"""Errores del dominio. La capa API los traduce a códigos HTTP (ver app/main.py)."""


class ErrorDominio(Exception):
    """Base de todos los errores conocidos de la aplicación."""


class ArchivoNoValido(ErrorDominio):
    """Extensión no permitida o archivo ilegible (HTTP 400/422)."""


class ImagenInvalida(ErrorDominio):
    """El archivo se abre pero no sirve: sin CRS, menos de 3 bandas... (HTTP 422)."""


class FormatoNoDisponible(ErrorDominio):
    """Formato previsto pero aún no implementado, p. ej. PNG/JPG (HTTP 415)."""


class ArchivoDemasiadoGrande(ErrorDominio):
    """Supera MAX_MB (HTTP 413)."""


class TrabajoNoEncontrado(ErrorDominio):
    """No existe un trabajo con ese id (HTTP 404)."""


class TrabajoNoTerminado(ErrorDominio):
    """Se pidió el resultado de un trabajo que no ha terminado (HTTP 409)."""


class TrabajoFallido(ErrorDominio):
    """El trabajo terminó con error (HTTP 500)."""
