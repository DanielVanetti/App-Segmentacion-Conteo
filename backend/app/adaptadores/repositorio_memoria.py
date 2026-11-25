"""
Estado de los trabajos en memoria. Se pierde al reiniciar.
Siguiente paso: repositorio_postgres.py con la misma interfaz (guardar/obtener/actualizar).
"""

import copy
import threading

from app.dominio.modelos import Trabajo


class RepositorioMemoria:
    def __init__(self):
        self._trabajos: dict[str, Trabajo] = {}
        self._candado = threading.Lock()

    def guardar(self, trabajo: Trabajo) -> None:
        with self._candado:
            self._trabajos[trabajo.id] = copy.copy(trabajo)  # copia: el repositorio es dueño de su estado

    def obtener(self, id_trabajo: str) -> Trabajo | None:
        with self._candado:
            trabajo = self._trabajos.get(id_trabajo)
            return copy.copy(trabajo) if trabajo else None  # copia: nadie lo modifica por fuera

    def actualizar(self, id_trabajo: str, **campos) -> None:
        with self._candado:
            trabajo = self._trabajos[id_trabajo]
            for nombre, valor in campos.items():
                setattr(trabajo, nombre, valor)
