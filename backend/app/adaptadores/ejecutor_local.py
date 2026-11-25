"""
Cola local con hilos. Con trabajadores=1 los trabajos se procesan de a uno y los demás
esperan "en cola". Siguiente paso si hay carga: ejecutor_celery.py con la misma interfaz.
"""

from concurrent.futures import ThreadPoolExecutor
from typing import Callable


class EjecutorLocal:
    def __init__(self, trabajadores: int = 1):
        self._pool = ThreadPoolExecutor(max_workers=trabajadores, thread_name_prefix="trabajo")

    def enviar(self, funcion: Callable, *args) -> None:
        self._pool.submit(funcion, *args)

    def cerrar(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
