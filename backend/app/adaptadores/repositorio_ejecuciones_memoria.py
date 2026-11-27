"""
Ejecuciones en memoria. Solo sirve con el procesador integrado (mismo proceso que la API):
otro proceso no puede ver esta memoria. Para pruebas y para arrancar sin base de datos.
"""

import copy
import threading
import time
from dataclasses import replace

from app.dominio.errores import Conflicto
from app.dominio.modelos import Ejecucion, EntradaBitacora, EstadoEjecucion as E, ahora


class RepositorioEjecucionesMemoria:
    def __init__(self):
        self._datos: dict[str, Ejecucion] = {}
        self._latidos: dict[str, float] = {}
        self._candado = threading.Lock()

    @staticmethod
    def _copia(e: Ejecucion) -> Ejecucion:
        return replace(e, bitacora=list(e.bitacora))

    def crear(self, ejecucion: Ejecucion) -> None:
        with self._candado:
            if any(x.proyecto_id == ejecucion.proyecto_id and x.estado.activa
                   for x in self._datos.values()):
                raise Conflicto("El proyecto ya tiene una detección en curso. Espere a que "
                                "termine o cancélela.")
            self._datos[ejecucion.id] = self._copia(ejecucion)

    def obtener(self, id_ejecucion: str) -> Ejecucion | None:
        with self._candado:
            e = self._datos.get(id_ejecucion)
            return self._copia(e) if e else None

    def _de(self, id_proyecto: str) -> list[Ejecucion]:
        return sorted((e for e in self._datos.values() if e.proyecto_id == id_proyecto),
                      key=lambda e: e.creado_en, reverse=True)

    def listar(self, id_proyecto: str) -> list[Ejecucion]:
        with self._candado:
            return [self._copia(e) for e in self._de(id_proyecto)]

    def activa(self, id_proyecto: str) -> Ejecucion | None:
        with self._candado:
            e = next((x for x in self._de(id_proyecto) if x.estado.activa), None)
            return self._copia(e) if e else None

    def ultimas(self) -> dict[str, Ejecucion]:
        with self._candado:
            res: dict[str, Ejecucion] = {}
            for e in sorted(self._datos.values(), key=lambda e: e.creado_en):
                res[e.proyecto_id] = self._copia(e)
            return res

    def eliminar_proyecto(self, id_proyecto: str) -> None:
        """Equivale al ON DELETE CASCADE de PostgreSQL."""
        with self._candado:
            for i in [i for i, e in self._datos.items() if e.proyecto_id == id_proyecto]:
                del self._datos[i]

    def solicitar_cancelacion(self, id_ejecucion: str) -> Ejecucion | None:
        with self._candado:
            e = self._datos.get(id_ejecucion)
            if e is None:
                return None
            if e.estado == E.EN_COLA:
                e.estado, e.etapa, e.finalizado_en = E.CANCELADO, "Cancelado", ahora()
                e.bitacora.append(EntradaBitacora(ahora(), "advertencia",
                                                  "Cancelada antes de empezar."))
            elif e.estado == E.EJECUTANDO and not e.cancelacion_solicitada:
                e.cancelacion_solicitada, e.etapa = True, "Cancelando"
                e.bitacora.append(EntradaBitacora(ahora(), "advertencia",
                                                  "Cancelación solicitada."))
            return self._copia(e)

    # --- procesador ---
    def tomar_siguiente(self) -> Ejecucion | None:
        with self._candado:
            cola = sorted((e for e in self._datos.values() if e.estado == E.EN_COLA),
                          key=lambda e: e.creado_en)
            if not cola:
                return None
            e = cola[0]
            e.estado, e.iniciado_en, e.etapa = E.EJECUTANDO, ahora(), "Preparando"
            self._latidos[e.id] = time.monotonic()
            return self._copia(e)

    def avanzar(self, id_ejecucion, progreso, etapa, mosaico_actual=None,
                mosaicos_totales=None) -> bool:
        with self._candado:
            e = self._datos.get(id_ejecucion)
            if e is None:
                return False
            e.progreso = progreso
            if not e.cancelacion_solicitada:
                e.etapa = etapa
            if mosaico_actual is not None:
                e.mosaico_actual = mosaico_actual
            if mosaicos_totales is not None:
                e.mosaicos_totales = mosaicos_totales
            self._latidos[id_ejecucion] = time.monotonic()
            return not e.cancelacion_solicitada

    def anotar(self, id_ejecucion, nivel, mensaje) -> None:
        with self._candado:
            e = self._datos.get(id_ejecucion)
            if e is not None:
                e.bitacora.append(EntradaBitacora(ahora(), nivel, mensaje))

    def terminar(self, id_ejecucion, estado, etapa, copas_detectadas=None,
                 copas_guardadas=None, area_total_m2=None) -> None:
        with self._candado:
            e = self._datos.get(id_ejecucion)
            if e is None or not e.estado.activa:
                return
            e.estado, e.etapa, e.finalizado_en = estado, etapa, ahora()
            e.copas_detectadas, e.copas_guardadas = copas_detectadas, copas_guardadas
            e.area_total_m2 = area_total_m2
            if estado == E.COMPLETADO:
                e.progreso = 1.0
            self._latidos.pop(id_ejecucion, None)

    def recuperar_interrumpidas(self, segundos_sin_latido: float) -> list[str]:
        limite = time.monotonic() - segundos_sin_latido
        with self._candado:
            ids = [i for i, e in self._datos.items()
                   if e.estado == E.EJECUTANDO and self._latidos.get(i, 0) <= limite]
            for i in ids:
                e = self._datos[i]
                e.estado, e.etapa, e.finalizado_en = E.FALLIDO, "Interrumpida", ahora()
                e.bitacora.append(EntradaBitacora(
                    ahora(), "error", "El procesamiento se interrumpió (el servicio se detuvo). "
                                      "Lance la detección de nuevo."))
            return ids
