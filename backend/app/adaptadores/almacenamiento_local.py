"""Guarda archivos en disco local: trabajos/<id>/entrada.<ext> y resultado.geojson."""

import shutil
from pathlib import Path

from app.dominio.errores import ArchivoDemasiadoGrande
from app.dominio.puertos import ArchivoSubido

TAM_PARTE = 1024 * 1024  # 1 MB


async def copiar_por_partes(archivo: ArchivoSubido, ruta: Path, max_bytes: int) -> None:
    """Escribe la subida en disco por partes (no se carga entera en memoria)."""
    total = 0
    with open(ruta, "wb") as f:
        while parte := await archivo.read(TAM_PARTE):
            total += len(parte)
            if total > max_bytes:
                raise ArchivoDemasiadoGrande(
                    f"El archivo supera el máximo de {max_bytes // (1024 * 1024)} MB")
            f.write(parte)


class AlmacenamientoLocal:
    def __init__(self, directorio: Path):
        self._dir = Path(directorio)
        self._dir.mkdir(parents=True, exist_ok=True)

    def _carpeta(self, id_trabajo: str) -> Path:
        return self._dir / id_trabajo

    async def guardar_subida(self, id_trabajo: str, archivo: ArchivoSubido,
                             extension: str, max_bytes: int) -> Path:
        """Escribe la subida por partes (no se carga entera en memoria)."""
        carpeta = self._carpeta(id_trabajo)
        carpeta.mkdir(parents=True)
        ruta = carpeta / f"entrada{extension}"
        try:
            await copiar_por_partes(archivo, ruta, max_bytes)
        except Exception:
            self.eliminar(id_trabajo)
            raise
        return ruta

    def ruta_resultado(self, id_trabajo: str) -> Path:
        return self._carpeta(id_trabajo) / "resultado.geojson"

    def eliminar(self, id_trabajo: str) -> None:
        shutil.rmtree(self._carpeta(id_trabajo), ignore_errors=True)
