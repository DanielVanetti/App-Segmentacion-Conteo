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


class DatosNoValidos(ErrorDominio):
    """Datos enviados por el usuario que no cumplen las reglas (HTTP 422)."""


class ProyectoNoEncontrado(ErrorDominio):
    """No existe un proyecto con ese id (HTTP 404)."""


class OrtomosaicoNoEncontrado(ErrorDominio):
    """El proyecto todavía no tiene un ortomosaico cargado (HTTP 404)."""


class Conflicto(ErrorDominio):
    """La operación choca con el estado actual: sin ortomosaico, ejecución en curso... (409)."""


class EjecucionNoEncontrada(ErrorDominio):
    """No existe esa ejecución en el proyecto (HTTP 404)."""


class EjecucionCancelada(Exception):
    """Interna del procesador: se pidió cancelar y se detiene entre mosaicos. No llega a HTTP."""
