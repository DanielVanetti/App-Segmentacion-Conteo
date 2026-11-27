r"""
Servicio de procesamiento aparte de la API (DD-01).

    .\.venv\Scripts\python.exe -m app.procesador

Lee la cola de ejecuciones en PostgreSQL (DATABASE_URL), carga el modelo una sola vez y
procesa de a una. Con Ctrl+C se detiene; la ejecución en curso queda como fallida
("Interrumpida") y se puede lanzar de nuevo. Para usarlo, arranque la API con
PROCESADOR_INTEGRADO=0, así no hay dos procesadores compitiendo por el modelo.
"""

import logging
import sys
import threading

from dotenv import load_dotenv


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_dotenv()
    from app.adaptadores.archivos_proyecto_local import ArchivosProyectoLocal
    from app.config import Config
    from app.contenedor import construir_procesador, construir_repositorios, construir_segmentador

    config = Config.desde_entorno()
    if not config.database_url:
        print("Falta DATABASE_URL: el procesador aparte lee la cola desde PostgreSQL "
              "(ver backend/.env.example).", file=sys.stderr)
        return 1
    repos = construir_repositorios(config)
    procesador = construir_procesador(config, repos, construir_segmentador(config),
                                      ArchivosProyectoLocal(config.dir_datos))
    hilo = threading.Thread(target=procesador.ciclo, name="procesador")
    hilo.start()
    try:
        while hilo.is_alive():
            hilo.join(0.5)
    except KeyboardInterrupt:
        print("Deteniendo el procesador...")
        procesador.detener.set()
        hilo.join()
    finally:
        for accion in repos.al_cerrar:
            accion()
    return 0


if __name__ == "__main__":
    sys.exit(main())
