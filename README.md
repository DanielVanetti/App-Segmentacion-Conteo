# App-Segmentacion-Conteo

Segmentación por instancia y conteo de copas de árboles en ortomosaicos de VANT
(bosque tropical seco, Región Chorotega). TFG G51 — Licenciatura en Informática, UNA.

## Estructura

```
App_Segmentacion_Conteo/
├── backend/                  API FastAPI + YOLOv8-seg (Python)
│   ├── app/                  servicio: subir GeoTIFF → teselar → predecir → GeoJSON
│   ├── herramientas/
│   │   └── hacer_teselas/    script offline: ortomosaico + anotaciones → dataset YOLO-seg
│   ├── modelos/best.pt       pesos del modelo
│   └── tests/
└── frontend/                 interfaz web (Vite + React + OpenLayers)
```

Cada carpeta tiene su propio `README.md` con instrucciones de instalación y uso.

## Arranque rápido

Base de datos (PostgreSQL 17 + PostGIS en Docker, puerto **5434**; desde la raíz):

```powershell
docker compose up -d db
```

Backend (PowerShell, desde `backend/`):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --env-file .env
```

- Documentación interactiva de la API: http://127.0.0.1:8000/docs
- `GET /salud` muestra `"persistencia": "postgis"`. Si dice `"memoria"`, falta `DATABASE_URL`
  y los proyectos se pierden al reiniciar.
- Pruebas: `.\.venv\Scripts\python.exe -m pytest -q`. Las de PostGIS solo corren si existe
  `DATABASE_URL_PRUEBAS` (ver `.env.example`).
- En la URL de la base use `127.0.0.1`, no `localhost` (en Windows puede colgarse por IPv6).

### Endpoints disponibles (`/api`)

| Método | Ruta | Requerimiento |
|---|---|---|
| GET / POST | `/api/proyectos` | RF-01 |
| GET / DELETE | `/api/proyectos/{id}` | RF-01 |
| POST | `/api/proyectos/{id}/ortomosaico` (multipart, campo `archivo`) | RF-02 a RF-04 |
| GET | `/api/proyectos/{id}/ortomosaico` | RF-02 |
| GET | `/api/proyectos/{id}/ortomosaico/archivo` (admite `Range`) | DD-03 |
| GET / POST | `/api/proyectos/{id}/trabajos` (lanzar detección: responde 202 y queda en cola) | RF-06 a RF-11 |
| GET | `/api/proyectos/{id}/trabajos/{idTrabajo}` (avance, mosaico actual, bitácora) | RF-10 |
| POST | `/api/proyectos/{id}/trabajos/{idTrabajo}/cancelacion` | RF-12 |
| GET | `/api/proyectos/{id}/trabajos/{idTrabajo}/resultado` (GeoJSON) | RF-13 |

Los errores responden `{"mensaje": "...", "detalle": ...}` en español (RNF-11).

**Procesamiento.** Por defecto la API corre el procesador en un hilo. Para tenerlo aparte
(DD-01: si se cae o se reinicia, la API sigue respondiendo), en dos terminales:

```powershell
$env:PROCESADOR_INTEGRADO = "0"; .\.venv\Scripts\python.exe -m uvicorn app.main:app --env-file .env
```

```powershell
.\.venv\Scripts\python.exe -m app.procesador
```

La cola es la tabla `ejecucion` de PostgreSQL (DD-02). `/trabajos` (sin proyecto) se mantiene
solo para la consola y pruebas rápidas.

Frontend (desde `frontend/`):

```powershell
npm install
npm run dev
```

Con `VITE_USE_MOCKS=true` en `frontend/.env` la interfaz usa la API simulada (MSW).
Con `VITE_USE_MOCKS=false`, Vite reenvía `/api` al backend en `http://127.0.0.1:8000`
(se cambia con `VITE_PROXY_API`). En el backend real ya existen proyectos, ortomosaico y
trabajos de detección; copas, correcciones y exportaciones todavía necesitan MSW.
