"""
Ejecuciones en PostgreSQL. La tabla `ejecucion` es también la cola (DD-02): no hace falta
Celery ni Redis. La API y el procesador pueden ser procesos distintos (DD-01) porque
comparten esta tabla.
"""

from dataclasses import asdict
from datetime import datetime

from sqlalchemy import Engine, case, delete, func, literal, select, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError

from app.adaptadores.bd.repositorio_proyectos_postgis import _iso
from app.adaptadores.bd.tablas import ejecucion as t
from app.dominio.errores import Conflicto
from app.dominio.modelos import (Ejecucion, EntradaBitacora, EstadoEjecucion as E,
                                 ParametrosEjecucion, ahora)

ACTIVOS = (E.EN_COLA.value, E.EJECUTANDO.value)


def _entrada(nivel: str, mensaje: str):
    """Expresión SQL de un arreglo JSON con una línea de bitácora (para `bitacora || ...`)."""
    return literal([{"momento": ahora(), "nivel": nivel, "mensaje": mensaje}], JSONB)


class RepositorioEjecucionesPostgis:
    def __init__(self, motor: Engine):
        self._motor = motor

    @staticmethod
    def _a_ejecucion(f) -> Ejecucion:
        return Ejecucion(
            id=f.id, proyecto_id=f.proyecto_id, ortomosaico_id=f.ortomosaico_id,
            parametros=ParametrosEjecucion(**f.parametros), estado=E(f.estado),
            progreso=f.progreso, etapa=f.etapa, mosaico_actual=f.mosaico_actual,
            mosaicos_totales=f.mosaicos_totales, creado_en=_iso(f.creado_en),
            iniciado_en=_iso(f.iniciado_en), finalizado_en=_iso(f.finalizado_en),
            copas_detectadas=f.copas_detectadas, copas_guardadas=f.copas_guardadas,
            area_total_m2=f.area_total_m2, cancelacion_solicitada=f.cancelacion_solicitada,
            bitacora=[EntradaBitacora(**b) for b in f.bitacora])

    def crear(self, e: Ejecucion) -> None:
        valores = dict(
            id=e.id, proyecto_id=e.proyecto_id, ortomosaico_id=e.ortomosaico_id,
            estado=e.estado.value, parametros=asdict(e.parametros), etapa=e.etapa,
            creado_en=datetime.fromisoformat(e.creado_en),
            bitacora=[asdict(b) for b in e.bitacora])
        try:
            with self._motor.begin() as cx:
                cx.execute(t.insert().values(**valores))
        except IntegrityError as exc:
            if "ux_ejecucion_activa" in str(exc.orig):
                raise Conflicto("El proyecto ya tiene una detección en curso. Espere a que "
                                "termine o cancélela.") from None
            raise

    def obtener(self, id_ejecucion: str) -> Ejecucion | None:
        with self._motor.connect() as cx:
            f = cx.execute(select(t).where(t.c.id == id_ejecucion)).first()
        return self._a_ejecucion(f) if f else None

    def listar(self, id_proyecto: str) -> list[Ejecucion]:
        with self._motor.connect() as cx:
            filas = cx.execute(select(t).where(t.c.proyecto_id == id_proyecto)
                               .order_by(t.c.creado_en.desc(), t.c.id.desc()))
            return [self._a_ejecucion(f) for f in filas]

    def activa(self, id_proyecto: str) -> Ejecucion | None:
        with self._motor.connect() as cx:
            f = cx.execute(select(t).where(t.c.proyecto_id == id_proyecto,
                                           t.c.estado.in_(ACTIVOS))).first()
        return self._a_ejecucion(f) if f else None

    def ultimas(self) -> dict[str, Ejecucion]:
        consulta = (select(t).distinct(t.c.proyecto_id)
                    .order_by(t.c.proyecto_id, t.c.creado_en.desc(), t.c.id.desc()))
        with self._motor.connect() as cx:
            return {f.proyecto_id: self._a_ejecucion(f) for f in cx.execute(consulta)}

    def eliminar_proyecto(self, id_proyecto: str) -> None:
        with self._motor.begin() as cx:   # normalmente ya lo hizo el CASCADE
            cx.execute(delete(t).where(t.c.proyecto_id == id_proyecto))

    def solicitar_cancelacion(self, id_ejecucion: str) -> Ejecucion | None:
        with self._motor.begin() as cx:
            cx.execute(update(t).where(t.c.id == id_ejecucion, t.c.estado == E.EN_COLA.value)
                       .values(estado=E.CANCELADO.value, etapa="Cancelado",
                               finalizado_en=func.now(),
                               bitacora=t.c.bitacora.op("||")(
                                   _entrada("advertencia", "Cancelada antes de empezar."))))
            cx.execute(update(t).where(t.c.id == id_ejecucion,
                                       t.c.estado == E.EJECUTANDO.value,
                                       t.c.cancelacion_solicitada.is_(False))
                       .values(cancelacion_solicitada=True, etapa="Cancelando",
                               bitacora=t.c.bitacora.op("||")(
                                   _entrada("advertencia", "Cancelación solicitada."))))
        return self.obtener(id_ejecucion)

    # --- procesador ------------------------------------------------------------
    def tomar_siguiente(self) -> Ejecucion | None:
        # SKIP LOCKED: si hay varios procesadores, cada uno toma una fila distinta.
        siguiente = (select(t.c.id).where(t.c.estado == E.EN_COLA.value)
                     .order_by(t.c.creado_en, t.c.id).limit(1)
                     .with_for_update(skip_locked=True).scalar_subquery())
        with self._motor.begin() as cx:
            f = cx.execute(update(t).where(t.c.id == siguiente)
                           .values(estado=E.EJECUTANDO.value, iniciado_en=func.now(),
                                   latido=func.now(), etapa="Preparando")
                           .returning(*t.c)).first()
        return self._a_ejecucion(f) if f else None

    def avanzar(self, id_ejecucion, progreso, etapa, mosaico_actual=None,
                mosaicos_totales=None) -> bool:
        valores = dict(progreso=progreso, latido=func.now())
        if mosaico_actual is not None:
            valores["mosaico_actual"] = mosaico_actual
        if mosaicos_totales is not None:
            valores["mosaicos_totales"] = mosaicos_totales
        # Mientras se cancela, la etapa sigue diciendo "Cancelando".
        valores["etapa"] = case((t.c.cancelacion_solicitada, "Cancelando"), else_=etapa)
        with self._motor.begin() as cx:
            f = cx.execute(update(t).where(t.c.id == id_ejecucion).values(**valores)
                           .returning(t.c.cancelacion_solicitada)).first()
        return f is not None and not f.cancelacion_solicitada

    def anotar(self, id_ejecucion, nivel, mensaje) -> None:
        with self._motor.begin() as cx:
            cx.execute(update(t).where(t.c.id == id_ejecucion)
                       .values(bitacora=t.c.bitacora.op("||")(_entrada(nivel, mensaje))))

    def terminar(self, id_ejecucion, estado, etapa, copas_detectadas=None,
                 copas_guardadas=None, area_total_m2=None) -> None:
        valores = dict(estado=estado.value, etapa=etapa, finalizado_en=func.now(),
                       copas_detectadas=copas_detectadas, copas_guardadas=copas_guardadas,
                       area_total_m2=area_total_m2)
        if estado == E.COMPLETADO:
            valores["progreso"] = 1.0
        with self._motor.begin() as cx:
            cx.execute(update(t).where(t.c.id == id_ejecucion, t.c.estado.in_(ACTIVOS))
                       .values(**valores))

    def recuperar_interrumpidas(self, segundos_sin_latido: float) -> list[str]:
        limite = func.now() - func.make_interval(0, 0, 0, 0, 0, 0, segundos_sin_latido)
        aviso = ("El procesamiento se interrumpió (el servicio se detuvo). "
                 "Lance la detección de nuevo.")
        with self._motor.begin() as cx:
            filas = cx.execute(
                update(t).where(t.c.estado == E.EJECUTANDO.value,
                                func.coalesce(t.c.latido, t.c.iniciado_en) < limite)
                .values(estado=E.FALLIDO.value, etapa="Interrumpida", finalizado_en=func.now(),
                        bitacora=t.c.bitacora.op("||")(_entrada("error", aviso)))
                .returning(t.c.id))
            return [f.id for f in filas]
