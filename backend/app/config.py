"""Configuración de la aplicación, leída de variables de entorno."""

import os
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Config:
    ruta_modelo: Path
    dir_trabajos: Path
    # OJO: tesela e imgsz deben coincidir con lo usado al entrenar (1024).
    tesela: int
    traslape: int
    imgsz: int
    confianza_min: float
    area_min_px: float      # descarta manchitas de pocos píxeles
    simplificar_px: float   # tolerancia para simplificar polígonos (0 = no simplificar)
    max_mb: int             # tamaño máximo de subida
    trabajadores: int       # trabajos procesados a la vez
    # Resolución (m/px) con que se entrenó el modelo. El ortomosaico se reduce a esta
    # resolución antes de segmentar. 0 = no reescalar (se usa la resolución original).
    gsd_objetivo: float = 0.0
    # Clases del modelo que se detectan y cuentan. Vacío = todas. 'grupo' se ignora.
    clases: tuple[str, ...] = ()

    @classmethod
    def desde_entorno(cls) -> "Config":
        cfg = cls(
            ruta_modelo=Path(os.getenv("RUTA_MODELO", RAIZ / "modelos" / "best.pt")),
            dir_trabajos=Path(os.getenv("DIR_TRABAJOS", RAIZ / "trabajos")),
            tesela=int(os.getenv("TESELA", 1024)),
            traslape=int(os.getenv("TRASLAPE", 192)),
            imgsz=int(os.getenv("IMGSZ", 1024)),
            confianza_min=float(os.getenv("CONFIANZA_MIN", 0.25)),
            area_min_px=float(os.getenv("AREA_MIN_PX", 20)),
            simplificar_px=float(os.getenv("SIMPLIFICAR_PX", 0.7)),
            max_mb=int(os.getenv("MAX_MB", 20_000)),
            trabajadores=int(os.getenv("TRABAJADORES", 1)),
            gsd_objetivo=float(os.getenv("GSD_OBJETIVO", 0.05)),
            clases=tuple(c.strip() for c in os.getenv("CLASES", "arbol").split(",") if c.strip()),
        )
        if not 0 <= cfg.traslape < cfg.tesela:
            raise ValueError("TRASLAPE debe ser mayor o igual a 0 y menor que TESELA")
        if cfg.gsd_objetivo < 0:
            raise ValueError("GSD_OBJETIVO no puede ser negativo (0 = no reescalar)")
        return cfg
