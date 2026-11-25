"""
Casos de uso de la aplicación: crear un trabajo, consultarlo, obtener su resultado
y procesar un archivo (también lo usa la consola, procesar.py).

Recibe todas sus dependencias por el constructor (inversión de dependencias):
no sabe qué clases concretas hay detrás.
"""

import uuid
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from app.dominio.errores import (
    ArchivoNoValido, TrabajoFallido, TrabajoNoEncontrado, TrabajoNoTerminado,
)
from app.dominio.modelos import EstadoTrabajo, Resumen, Trabajo, ahora
from app.dominio.puertos import (
    Almacenamiento, ArchivoSubido, Ejecutor, Exportador, LectorImagen,
    RepositorioTrabajos, Segmentador,
)
from app.servicios.pipeline import segmentar_imagen


@dataclass(frozen=True)
class ParametrosPipeline:
    tesela: int
    traslape: int
    simplificar_px: float
    gsd_objetivo: float = 0.0   # m/px del modelo; 0 = no reescalar


class ServicioTrabajos:
    def __init__(
        self,
        repositorio: RepositorioTrabajos,
        almacenamiento: Almacenamiento,
        ejecutor: Ejecutor,
        segmentador: Segmentador,
        exportador: Exportador,
        abrir_lector: Callable[[Path], LectorImagen],
        extensiones: set[str],
        parametros: ParametrosPipeline,
        max_bytes: int,
    ):
        self.repositorio = repositorio
        self.almacenamiento = almacenamiento
        self.ejecutor = ejecutor
        self.segmentador = segmentador
        self.exportador = exportador
        self.abrir_lector = abrir_lector
        self.extensiones = extensiones
        self.parametros = parametros
        self.max_bytes = max_bytes

    # --- Casos de uso para la API -------------------------------------------
    async def crear(self, nombre_archivo: str, archivo: ArchivoSubido) -> Trabajo:
        extension = Path(nombre_archivo or "").suffix.lower()
        if extension not in self.extensiones:
            raise ArchivoNoValido(
                f"Extensión no permitida. Use: {', '.join(sorted(self.extensiones))}")

        id_trabajo = uuid.uuid4().hex
        ruta = await self.almacenamiento.guardar_subida(
            id_trabajo, archivo, extension, self.max_bytes)
        try:
            with self.abrir_lector(ruta) as lector:
                info = lector.info()  # valida (CRS, bandas...) antes de encolar
        except Exception:
            self.almacenamiento.eliminar(id_trabajo)
            raise

        trabajo = Trabajo(id=id_trabajo, archivo=nombre_archivo, info=info)
        self.repositorio.guardar(trabajo)
        creado = replace(trabajo)  # copia: el hilo de trabajo modifica el original
        self.ejecutor.enviar(self._procesar_trabajo, id_trabajo, ruta)
        return creado

    def obtener(self, id_trabajo: str) -> Trabajo:
        trabajo = self.repositorio.obtener(id_trabajo)
        if trabajo is None:
            raise TrabajoNoEncontrado("Trabajo no encontrado")
        return trabajo

    def ruta_resultado(self, id_trabajo: str) -> Path:
        trabajo = self.obtener(id_trabajo)
        if trabajo.estado == EstadoTrabajo.ERROR:
            raise TrabajoFallido(trabajo.error or "Error desconocido")
        if trabajo.estado != EstadoTrabajo.TERMINADO:
            raise TrabajoNoTerminado(f"El trabajo aún no termina (estado: {trabajo.estado.value})")
        return self.almacenamiento.ruta_resultado(id_trabajo)

    # --- Procesamiento (API en segundo plano y consola) ---------------------
    def procesar_archivo(self, ruta: Path, salida: Path,
                         al_avanzar: Callable[[float], None] | None = None) -> Resumen:
        p = self.parametros
        with self.abrir_lector(ruta) as lector:
            info = lector.info()
            copas = segmentar_imagen(lector, self.segmentador, p.tesela, p.traslape,
                                     p.simplificar_px, al_avanzar, gsd_objetivo=p.gsd_objetivo)
        return self.exportador.exportar(copas, info, salida)

    def _procesar_trabajo(self, id_trabajo: str, ruta: Path) -> None:
        repo = self.repositorio
        repo.actualizar(id_trabajo, estado=EstadoTrabajo.PROCESANDO, inicio=ahora())
        try:
            resumen = self.procesar_archivo(
                ruta, self.almacenamiento.ruta_resultado(id_trabajo),
                al_avanzar=lambda prog: repo.actualizar(id_trabajo, progreso=prog))
            repo.actualizar(id_trabajo, estado=EstadoTrabajo.TERMINADO, progreso=1.0,
                            resumen=resumen, fin=ahora())
        except Exception as e:  # cualquier fallo queda registrado en el estado
            repo.actualizar(id_trabajo, estado=EstadoTrabajo.ERROR,
                            error=f"{type(e).__name__}: {e}", fin=ahora())
