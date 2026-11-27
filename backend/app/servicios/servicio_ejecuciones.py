"""
Casos de uso de las ejecuciones desde la API (RF-06 a RF-12): lanzar, consultar, cancelar
y descargar el resultado. La API NO procesa: solo deja la ejecución en la cola. El trabajo
pesado lo hace el procesador (servicios/procesador.py), que puede ser otro proceso (DD-01).
"""

import uuid
from pathlib import Path

from app.dominio import errores
from app.dominio.modelos import Ejecucion, EntradaBitacora, EstadoEjecucion, ParametrosEjecucion, ahora
from app.dominio.puertos import ArchivosProyecto, RepositorioEjecuciones, RepositorioProyectos

TAMANO_MIN, TAMANO_MAX = 256, 4096
TRASLAPE_MAX_PCT = 50


def validar_parametros(p: ParametrosEjecucion) -> None:
    problemas = []
    if not TAMANO_MIN <= p.tamano_mosaico_px <= TAMANO_MAX or p.tamano_mosaico_px % 32:
        problemas.append(f"el tamaño de mosaico debe estar entre {TAMANO_MIN} y {TAMANO_MAX} "
                         "píxeles y ser múltiplo de 32")
    if not 0 <= p.traslape_pct <= TRASLAPE_MAX_PCT:
        problemas.append(f"el traslape debe estar entre 0 y {TRASLAPE_MAX_PCT} %")
    if not 0 <= p.confianza_minima <= 1:
        problemas.append("la confianza mínima debe estar entre 0 y 1")
    if p.area_minima_m2 < 0:
        problemas.append("el área mínima no puede ser negativa")
    if problemas:
        raise errores.DatosNoValidos("Parámetros no válidos: " + "; ".join(problemas) + ".")


class ServicioEjecuciones:
    def __init__(self, repositorio: RepositorioEjecuciones, proyectos: RepositorioProyectos,
                 archivos: ArchivosProyecto, tesela_modelo: int, confianza_modelo: float):
        self.repositorio = repositorio
        self.proyectos = proyectos
        self.archivos = archivos
        self.tesela_modelo = tesela_modelo
        self.confianza_modelo = confianza_modelo

    def _proyecto(self, id_proyecto: str) -> None:
        if self.proyectos.obtener(id_proyecto) is None:
            raise errores.ProyectoNoEncontrado("El proyecto solicitado no existe.")

    def lanzar(self, id_proyecto: str, parametros: ParametrosEjecucion) -> Ejecucion:
        self._proyecto(id_proyecto)
        orto = self.proyectos.obtener_ortomosaico(id_proyecto)
        if orto is None:
            raise errores.Conflicto("El proyecto no tiene una imagen cargada. Cargue el "
                                    "ortomosaico antes de ejecutar la detección.")
        validar_parametros(parametros)

        bitacora = [EntradaBitacora(ahora(), "info", "Detección en cola.")]
        if parametros.tamano_mosaico_px != self.tesela_modelo:
            bitacora.append(EntradaBitacora(
                ahora(), "advertencia",
                f"El modelo se entrenó con mosaicos de {self.tesela_modelo} px y se pidieron "
                f"{parametros.tamano_mosaico_px} px: los resultados pueden empeorar."))
        if parametros.confianza_minima < self.confianza_modelo:
            bitacora.append(EntradaBitacora(
                ahora(), "advertencia",
                f"El modelo descarta las detecciones con confianza menor a "
                f"{self.confianza_modelo:g}; no habrá copas por debajo de ese valor."))

        ejecucion = Ejecucion(id=str(uuid.uuid4()), proyecto_id=id_proyecto,
                              ortomosaico_id=orto.id, parametros=parametros, bitacora=bitacora)
        self.repositorio.crear(ejecucion)   # Conflicto si ya hay una activa
        return ejecucion

    def listar(self, id_proyecto: str) -> list[Ejecucion]:
        self._proyecto(id_proyecto)
        return self.repositorio.listar(id_proyecto)

    def obtener(self, id_proyecto: str, id_ejecucion: str) -> Ejecucion:
        e = self.repositorio.obtener(id_ejecucion)
        if e is None or e.proyecto_id != id_proyecto:
            raise errores.EjecucionNoEncontrada("El trabajo solicitado no existe.")
        return e

    def cancelar(self, id_proyecto: str, id_ejecucion: str) -> Ejecucion:
        self.obtener(id_proyecto, id_ejecucion)
        e = self.repositorio.solicitar_cancelacion(id_ejecucion)
        if e is None:
            raise errores.EjecucionNoEncontrada("El trabajo solicitado no existe.")
        return e

    def ruta_resultado(self, id_proyecto: str, id_ejecucion: str) -> Path:
        e = self.obtener(id_proyecto, id_ejecucion)
        if e.estado != EstadoEjecucion.COMPLETADO:
            raise errores.Conflicto("El trabajo no tiene resultado: su estado es "
                                    f"«{e.estado.value}».")
        ruta = self.archivos.ruta_resultado(id_proyecto, id_ejecucion)
        if not ruta.exists():
            raise errores.EjecucionNoEncontrada("El resultado ya no está en el servidor.")
        return ruta
