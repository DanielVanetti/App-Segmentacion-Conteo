# Contexto del proyecto: segmentación de copas de árboles con YOLO + API en FastAPI

## Qué queremos construir
Un sistema que reciba un **ortomosaico de dron (GeoTIFF)** y devuelva **cada copa de árbol segmentada** como polígono georreferenciado (GeoJSON), con conteo y área en m².

Flujo completo:
1. **Entrenamiento (Google Colab, GPU T4):** YOLOv8-seg (Ultralytics) sobre teselas anotadas → produce `best.pt`.
2. **Servicio (FastAPI):** carga `best.pt` una sola vez, recibe el GeoTIFF, lo corta en teselas con traslape, predice, une resultados sin duplicar copas, convierte píxeles a coordenadas y devuelve GeoJSON.

Este trabajo nace de un TFG de la Universidad Nacional (Costa Rica). También servirá como base para otro equipo que hará lo mismo para **detectar maleza en pasturas** (mismo flujo, otra clase).

## Equipo
Jose Alejandro Chaves, Daniel González y Josué Solórzano. Explicaciones en español, lenguaje simple.

## Estado actual

### Datos
- Material de práctica: DJI Zenmuse P1, parcela 10. **No son los datos finales de la ECA.**
- `dataset_v2.zip` (Drive, ID `1XhPZGAjrYtNCVMjcstexS3qLIYW49L0U`): carpetas `images/` y `labels/` con `train_v2` (7 teselas, 31 copas) y `val_v2` (7 teselas, 23 copas). Etiquetas en formato YOLO-seg (polígonos normalizados), una sola clase: `0: tree`.
- El ZIP se genera en la PC con `armar_dataset_v2.py` (corta y exporta; no está en este repo todavía).
- Anotación hecha en CVAT con polígonos. Criterio: solo copas completas, sin copas dudosas.
- Hay un ortomosaico `parcela_32.tif` en Drive (ID `1U9h9A98CfDYHqO2qqEXEbxpJMp54iWER`). **Falta confirmar si es GeoTIFF** (tiene CRS y transform). Se verifica con `rasterio.open(f).crs`.

### Entrenamiento (cuaderno `SCDA_ensayo2_YOLOv8seg.ipynb`)
- Configuración base: `yolov8n-seg.pt`, `epochs=60`, `imgsz=1024`, `batch=4`, `patience=20`.
- Repite cada experimento con 3 semillas, evalúa con pycocotools (mismo protocolo que detectree2) y guarda un CSV de registro en Drive.
- Regla del borde: copas que tocan el borde de la tesela (3 px) no cuentan ni como anotación ni como predicción.
- Pesos guardados en `MyDrive/SCDA_practica/ensayo2/yolo/pesos/base_s{semilla}.pt` (es el `best.pt` renombrado).
- **Resultado: mAP50 = 0,0, precisión 0 y exhaustividad 0.** Predice 1–2 copas donde hay 14. El early stopping cortó en la época 22–28. La causa principal es la falta de datos (31 copas), no el código.

### API (paquete `app/`, arquitectura por capas con puertos y adaptadores; ver README §9)
- Arranque: `python -m uvicorn app.main:app`. Consola: `python procesar.py <tif>`. Pruebas: `python -m pytest -q`.
- Clases concretas solo en `app/contenedor.py`; el núcleo (`app/servicios/`) depende de `app/dominio/puertos.py`.
- PNG/JPG registrados en `app/adaptadores/lectores/fabrica.py` pero responden 415 (pendiente).
- `POST /trabajos`: sube el .tif (a disco por partes), devuelve `id`, procesa con `BackgroundTasks`.
- `GET /trabajos/{id}`: estado (`en cola`, `procesando` + progreso, `terminado`, `error`).
- `GET /trabajos/{id}/resultado`: GeoJSON en EPSG:4326 con `id`, `confianza` y `area_m2` (si el CRS es proyectado).
- Lee el ortomosaico por ventanas con Rasterio (`TESELA=1024`, `TRASLAPE=192`). Bandas 1-3, conversión a 8 bits por percentiles 2–98, RGB→BGR antes de `predict`.
- Duplicados en el traslape: cada copa pertenece a la tesela que contiene su centroide, descontando la mitad del traslape en los lados internos.
- El estado de los trabajos vive en memoria (pendiente de pasar a base de datos).
- **Escala:** `GSD_OBJETIVO` (por defecto 0.05 m/px) = resolución con que se entrenó el modelo. El pipeline lee cada ventana más grande (`TESELA * factor`) y la reduce a `TESELA` px; los polígonos se devuelven a la escala original. Si el modelo se reentrena a otra resolución, cambiar este valor. Con `0` no reescala.
- **Clases:** `CLASES` (por defecto `arbol`) filtra en `predict(classes=...)`. El modelo de Santa Cruz (`fold1`, YOLOv8n-seg, 2 clases) tiene `0: arbol` y `1: grupo`; `grupo` se ignora y no cuenta. Con un modelo cuya clase no coincide (p. ej. `tree`) no se filtra y se avisa.
- Incluye `requirements.txt` y `Dockerfile` (torch CPU).

### Proyectos y persistencia (RF-01 a RF-04)
- Prefijo `/api` (lo usa el frontend). Contrato del front en `frontend/src/shared/api/types.ts`: JSON en **camelCase**; errores `{"mensaje", "detalle"}` en español.
- PostgreSQL 17 + PostGIS en Docker (`docker compose up -d db`, puerto **5434**; el 5433 lo usa otro proyecto del equipo). URL en `backend/.env` (`DATABASE_URL`, con `127.0.0.1`, no `localhost`).
- Esquema con **Alembic** (`migraciones/versions/`). Tablas nuevas = migración nueva; no editar la 0001.
- Puerto `RepositorioProyectos` con dos adaptadores: `bd/repositorio_proyectos_postgis.py` y `repositorio_proyectos_memoria.py` (pruebas, o si falta `DATABASE_URL`; `/salud` dice cuál se usa).
- Un ortomosaico por proyecto; cargar otro lo reemplaza. La subida va a `datos/temporales/`, se valida y solo entonces pasa a `datos/proyectos/<id>/`: un archivo inválido no borra el anterior.
- Validación (`servicios/validacion_ortomosaico.py`): sin CRS o con menos de 3 bandas se rechaza (422). Resolución fuera de `GSD_MIN`–`GSD_MAX` o CRS distinto de EPSG:5367 se acepta con advertencia.
- La huella se guarda en el CRS de origen con su SRID (DD-04) y la envolvente en EPSG:5367 aparte para el visor.
- Pruebas de PostGIS: `tests/test_repositorio_postgis.py`, solo con `DATABASE_URL_PRUEBAS` (base `copas_pruebas`, que se vacía).

## Próximos pasos (en orden)
1. Obtener `best.pt` y probar la API de punta a punta con `parcela_32.tif`.
2. Confirmar que `parcela_32.tif` es GeoTIFF; si está en EPSG:4326, reproyectar a CRTM05 (EPSG:5367) para medir áreas.
3. Mejorar el modelo: anotar **300–500 copas o más** de varias zonas; teselas de 640–1024 px con traslape del 15–20%; aumentos para imagen aérea (`flipud=0.5`, `degrees=90`); `epochs=150`, `patience=50`; probar `yolov8s-seg.pt`.
4. Separar entrenamiento y validación **por zonas geográficas**, no al azar, para no inflar las métricas.
5. Ligar los trabajos a proyectos (`/api/proyectos/{id}/trabajos`) y pasar su estado a PostgreSQL. Según DD-01 y DD-02 del informe, el procesamiento corre en un servicio aparte que lee una tabla de ejecuciones (no Celery/Redis), y así es posible cancelar.

## Reglas para trabajar en este proyecto
- `TESELA` e `IMGSZ` en la API deben coincidir con los usados al entrenar.
- No cargar el ortomosaico completo en memoria: siempre por ventanas.
- No reportar una mejora del modelo si no supera la variación entre semillas de la línea base.
- `test_v2` se usa una sola vez, al final.
- El modelo se carga una vez al iniciar la API, nunca por solicitud.
- Ultralytics tiene licencia AGPL-3.0: tenerlo en cuenta si el servicio se publica.
- Stack preferido: Python, FastAPI, Rasterio, Shapely, Ultralytics, PostgreSQL/PostGIS, Docker.