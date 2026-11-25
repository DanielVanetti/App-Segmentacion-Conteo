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

Backend (PowerShell, desde `backend/`):

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Frontend (desde `frontend/`):

```powershell
npm install
npm run dev
```

Con `VITE_USE_MOCKS=true` en `frontend/.env` la interfaz usa la API simulada (MSW);
con `false` y `VITE_API_URL` apuntando al backend, usa la API real.
