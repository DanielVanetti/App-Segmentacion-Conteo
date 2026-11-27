"""
Procesador de ejecuciones (DD-01, DD-02). Toma la siguiente ejecución en cola, corre el
pipeline (teselas -> YOLO -> unir -> GeoJSON) e informa el avance mosaico por mosaico.

Puede correr dentro de la API (un hilo, PROCESADOR_INTEGRADO=1) o como proceso aparte
(`python -m app.procesador`). Como solo se comunica por el repositorio, la API sigue
respondiendo aunque el procesador esté ocupado o se caiga.

Cancelar (RF-12): la API marca la fila; el procesador lo nota al terminar el mosaico en
curso y se detiene. Lo que ya se procesó se descarta.
"""

import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.dominio.errores import EjecucionCancelada, ErrorDominio
from app.dominio.modelos import Ejecucion, EstadoEjecucion as E
from app.dominio.puertos import (ArchivosProyecto, Exportador, LectorImagen,
                                 RepositorioEjecuciones, RepositorioProyectos, Segmentador)
from app.servicios.pipeline import segmentar_imagen

log = logging.getLogger(__name__)

# Reparto del avance: preparar 0-3 %, mosaicos 3-92 %, unir y guardar 92-100 %.
INICIO_MOSAICOS, FIN_MOSAICOS = 0.03, 0.92


class ServicioDetenido(Exception):
    """El procesador se está apagando: la ejecución queda como fallida, no cancelada."""


@dataclass(frozen=True)
class AjustesProcesador:
    simplificar_px: float
    gsd_objetivo: float
    confianza_modelo: float
    espera_s: float = 2.0          # cada cuánto mira la cola cuando está vacía
    interrupcion_s: float = 300.0  # sin latido por más de esto = el procesador se cayó


class Procesador:
    def __init__(self, ejecuciones: RepositorioEjecuciones, proyectos: RepositorioProyectos,
                 archivos: ArchivosProyecto, segmentador: Segmentador, exportador: Exportador,
                 abrir_lector: Callable[[Path], LectorImagen], ajustes: AjustesProcesador):
        self.ejecuciones = ejecuciones
        self.proyectos = proyectos
        self.archivos = archivos
        self.segmentador = segmentador
        self.exportador = exportador
        self.abrir_lector = abrir_lector
        self.ajustes = ajustes
        self.detener = threading.Event()

    # --- bucle -----------------------------------------------------------------
    def ciclo(self) -> None:
        """Procesa la cola hasta que se active `detener`."""
        log.info("Procesador de ejecuciones iniciado.")
        while not self.detener.is_set():
            try:
                if not self.procesar_siguiente():
                    self.detener.wait(self.ajustes.espera_s)
            except Exception:   # p. ej. la base no responde: se reintenta
                log.exception("Error en el ciclo del procesador; se reintenta.")
                self.detener.wait(self.ajustes.espera_s * 5)
        log.info("Procesador de ejecuciones detenido.")

    def procesar_siguiente(self) -> bool:
        """Procesa una ejecución si hay alguna en cola. True si procesó algo."""
        for i in self.ejecuciones.recuperar_interrumpidas(self.ajustes.interrupcion_s):
            log.warning("Ejecución %s marcada como interrumpida.", i)
        e = self.ejecuciones.tomar_siguiente()
        if e is None:
            return False
        self.procesar(e)
        return True

    # --- una ejecución -------------------------------------------------------------
    def procesar(self, e: Ejecucion) -> None:
        repo, p = self.ejecuciones, e.parametros
        log.info("Procesando ejecución %s (proyecto %s).", e.id, e.proyecto_id)
        salida: Path | None = None
        try:
            orto = self.proyectos.obtener_ortomosaico(e.proyecto_id)
            if orto is None or orto.id != e.ortomosaico_id:
                raise ErrorDominio("El ortomosaico del proyecto cambió o ya no existe. "
                                   "Lance la detección de nuevo.")
            self._seguir(e.id, 0.01, "Preparando el ortomosaico")
            tesela = p.tamano_mosaico_px
            traslape = min(round(tesela * p.traslape_pct / 100), tesela - 1)

            def al_mosaico(n: int, total: int) -> None:
                avance = INICIO_MOSAICOS + (FIN_MOSAICOS - INICIO_MOSAICOS) * (n / total if total else 1)
                self._seguir(e.id, round(avance, 4), "Detectando copas", n, total)

            with self.abrir_lector(Path(orto.ruta)) as lector:
                info = lector.info()
                repo.anotar(e.id, "info", f"Ortomosaico «{orto.nombre_archivo}»: {info.ancho} × "
                                          f"{info.alto} px. Mosaicos de {tesela} px con "
                                          f"{traslape} px de traslape.")
                copas = segmentar_imagen(lector, self.segmentador, tesela, traslape,
                                         self.ajustes.simplificar_px,
                                         gsd_objetivo=self.ajustes.gsd_objetivo,
                                         al_mosaico=al_mosaico)

            self._seguir(e.id, FIN_MOSAICOS, "Uniendo y guardando resultados")
            mpu = info.metros_por_unidad
            areas = [c.poligono.area * mpu * mpu if mpu else None for c in copas]
            if mpu is None and p.area_minima_m2 > 0:
                repo.anotar(e.id, "advertencia", "El sistema de referencia no está en metros: "
                                                 "no se aplicó el área mínima.")
            elif p.area_minima_m2 > 0:
                antes = len(copas)
                pares = [(c, a) for c, a in zip(copas, areas) if a >= p.area_minima_m2]
                copas, areas = [c for c, _ in pares], [a for _, a in pares]
                if antes - len(copas):
                    repo.anotar(e.id, "info", f"Se descartaron {antes - len(copas)} detecciones "
                                              f"menores a {p.area_minima_m2:g} m².")

            salida = self.archivos.ruta_resultado(e.proyecto_id, e.id)
            resumen = self.exportador.exportar(copas, info, salida)
            if resumen.aviso:
                repo.anotar(e.id, "advertencia", resumen.aviso)
            contadas = [a for c, a in zip(copas, areas) if c.confianza >= p.confianza_minima]
            area_total = round(sum(contadas), 2) if mpu else None
            if not self.ejecuciones.avanzar(e.id, 0.99, "Terminando"):
                raise EjecucionCancelada()
            repo.anotar(e.id, "info", f"{len(contadas)} copas con confianza ≥ "
                                      f"{p.confianza_minima:g} ({len(copas)} guardadas en total).")
            repo.terminar(e.id, E.COMPLETADO, "Terminado", copas_detectadas=len(contadas),
                          copas_guardadas=len(copas), area_total_m2=area_total)
            log.info("Ejecución %s terminada: %d copas.", e.id, len(contadas))
        except EjecucionCancelada:
            self._borrar(salida)
            repo.anotar(e.id, "advertencia", "Detección cancelada; se descartó lo procesado.")
            repo.terminar(e.id, E.CANCELADO, "Cancelado")
            log.info("Ejecución %s cancelada.", e.id)
        except ServicioDetenido:
            self._borrar(salida)
            repo.anotar(e.id, "error", "El servicio de procesamiento se detuvo. "
                                       "Lance la detección de nuevo.")
            repo.terminar(e.id, E.FALLIDO, "Interrumpida")
        except Exception as exc:
            self._borrar(salida)
            log.exception("Ejecución %s falló.", e.id)
            mensaje = str(exc) if isinstance(exc, ErrorDominio) else (
                "Ocurrió un error al procesar el ortomosaico. Revise la bitácora del servidor.")
            repo.anotar(e.id, "error", mensaje)
            repo.terminar(e.id, E.FALLIDO, "Falló")

    def _seguir(self, id_ejecucion: str, progreso: float, etapa: str,
                n: int | None = None, total: int | None = None) -> None:
        """Informa el avance y se detiene si se pidió cancelar o apagar."""
        if self.detener.is_set():
            raise ServicioDetenido()
        if not self.ejecuciones.avanzar(id_ejecucion, progreso, etapa, n, total):
            raise EjecucionCancelada()

    @staticmethod
    def _borrar(ruta: Path | None) -> None:
        if ruta is not None:
            ruta.unlink(missing_ok=True)

