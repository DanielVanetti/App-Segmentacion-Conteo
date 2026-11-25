"""
Proyectos en memoria. Se pierden al reiniciar: solo para pruebas y para arrancar la API
sin base de datos (sin DATABASE_URL). En uso real va repositorio_proyectos_postgis.
"""

import copy
import threading
from dataclasses import replace

from app.dominio.modelos import Ortomosaico, Proyecto, ahora


class RepositorioProyectosMemoria:
    def __init__(self):
        self._proyectos: dict[str, Proyecto] = {}
        self._ortos: dict[str, Ortomosaico] = {}   # por id de proyecto
        self._candado = threading.Lock()

    def _con_orto(self, p: Proyecto) -> Proyecto:
        orto = self._ortos.get(p.id)
        return replace(p, ortomosaico_id=orto.id if orto else None)

    def crear(self, proyecto: Proyecto) -> None:
        with self._candado:
            self._proyectos[proyecto.id] = copy.copy(proyecto)

    def listar(self) -> list[Proyecto]:
        with self._candado:
            todos = sorted(self._proyectos.values(), key=lambda p: p.creado_en, reverse=True)
            return [self._con_orto(p) for p in todos]

    def obtener(self, id_proyecto: str) -> Proyecto | None:
        with self._candado:
            p = self._proyectos.get(id_proyecto)
            return self._con_orto(p) if p else None

    def eliminar(self, id_proyecto: str) -> bool:
        with self._candado:
            self._ortos.pop(id_proyecto, None)
            return self._proyectos.pop(id_proyecto, None) is not None

    def guardar_ortomosaico(self, ortomosaico: Ortomosaico) -> None:
        with self._candado:
            self._ortos[ortomosaico.proyecto_id] = copy.copy(ortomosaico)
            p = self._proyectos[ortomosaico.proyecto_id]
            self._proyectos[p.id] = replace(p, actualizado_en=ahora())

    def obtener_ortomosaico(self, id_proyecto: str) -> Ortomosaico | None:
        with self._candado:
            o = self._ortos.get(id_proyecto)
            return copy.copy(o) if o else None
