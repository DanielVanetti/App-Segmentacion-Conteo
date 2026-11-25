# Segmentación de copas de árboles (YOLOv8-seg)

Recibe un ortomosaico de dron (GeoTIFF) y devuelve cada copa de árbol como polígono
georreferenciado en un archivo GeoJSON, con conteo y área en m².

Todos los comandos son para **PowerShell** y se corren desde la carpeta del proyecto.

---

## 1. Instalación (solo la primera vez)

```powershell
cd C:\Users\Ale\Desktop\api_copas_yolo
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

El modelo entrenado tiene que estar en `modelos\best.pt`.

> Usamos directamente `.\.venv\Scripts\python.exe` para no tener que activar el entorno
> (en Windows, `Activate.ps1` a veces está bloqueado por la política de ejecución).

---

## 2. Procesar un ortomosaico

```powershell
cd C:\Users\Ale\Desktop\api_copas_yolo
.\.venv\Scripts\python.exe procesar.py C:\ruta\ortomosaico.tif
```

Salida esperada:

```
Cargando modelo best.pt ...
Procesando teselas: 100.0%  (6 s)
Copas encontradas: 11
Área total: 23.67 m²
CRS de origen: EPSG:5367
Resultado guardado en: C:\ruta\ortomosaico_copas.geojson
```

El resultado se guarda junto al `.tif` como `<nombre>_copas.geojson`.

Para elegir otro nombre o carpeta de salida:

```powershell
.\.venv\Scripts\python.exe procesar.py C:\ruta\ortomosaico.tif -o C:\resultados\copas.geojson
```

Para ver la ayuda:

```powershell
.\.venv\Scripts\python.exe procesar.py -h
```

Para detener un proceso a la mitad: **Ctrl + C**.

---

## 3. Antes de procesar: revisar que el `.tif` sea GeoTIFF

```powershell
.\.venv\Scripts\python.exe -c "import rasterio; d=rasterio.open(r'C:\ruta\ortomosaico.tif'); print('CRS:', d.crs); print('Tamaño:', d.width, 'x', d.height, '| bandas:', d.count, '| tipo:', d.dtypes[0]); print('Pixel:', d.res)"
```

- Si `CRS` sale `None`: el archivo **no está georreferenciado** y no se puede procesar.
- Si `CRS` sale `EPSG:4326` (grados): se cuentan las copas pero **no se calculan áreas**.
  Hay que reproyectarlo a CRTM05 (paso 4).
- Hace falta que tenga al menos 3 bandas (RGB).

---

## 4. Reproyectar a CRTM05 (solo si está en EPSG:4326)

```powershell
.\.venv\Scripts\rio.exe warp C:\ruta\ortomosaico.tif C:\ruta\ortomosaico_crtm05.tif --dst-crs EPSG:5367
```

Después se procesa el archivo nuevo (`ortomosaico_crtm05.tif`) con el paso 2.

---

## 5. Ver el resultado

Abran el `.geojson` en **QGIS** junto con el ortomosaico (basta con arrastrar los dos
archivos a QGIS). Cada polígono trae:

| Campo       | Qué es                                         |
|-------------|------------------------------------------------|
| `id`        | número de la copa                              |
| `clase`     | clase predicha (`tree`)                        |
| `confianza` | qué tan seguro está el modelo (0 a 1)          |
| `area_m2`   | área de la copa en m² (vacío si el CRS no es proyectado) |

---

## 6. Ajustes opcionales

Se escriben en la misma terminal **antes** del paso 2:

```powershell
$env:CONFIANZA_MIN = "0.15"   # confianza mínima para aceptar una copa (por defecto 0.25)
$env:AREA_MIN_PX   = "50"     # descarta polígonos más pequeños que esto, en píxeles (por defecto 20)
$env:RUTA_MODELO   = "C:\ruta\otro_modelo.pt"   # usar otros pesos
$env:SIMPLIFICAR_PX = "0.7"   # simplifica los bordes del polígono (0 = sin simplificar)
$env:MAX_MB        = "20000"  # tamaño máximo de subida en la API
$env:TRABAJADORES  = "1"      # trabajos que la API procesa a la vez
$env:GSD_OBJETIVO  = "0.05"   # m/px con que se entrenó el modelo (por defecto 0.05; 0 = no reescalar)
$env:CLASES        = "arbol"  # clases que se detectan y cuentan (por defecto arbol; 'grupo' se ignora)
```

No cambien `TESELA` ni `IMGSZ` (1024): tienen que ser iguales a los usados al entrenar.

**Resolución (`GSD_OBJETIVO`).** El modelo actual se entrenó con teselas de 1024 px a **5 cm/px**
(51 m por tesela). Si el ortomosaico es más fino (p. ej. 1,22 cm/px), la API lo reduce a 5 cm
antes de segmentar y devuelve los polígonos en las coordenadas originales. Si el ortomosaico
es más grueso que 5 cm no se amplía y se avisa. Si se reentrena a otra resolución, cambien
este valor (`$env:GSD_OBJETIVO = "0.03"`). Con `0` no se reescala (se usa la resolución original).

**Clases (`CLASES`).** El modelo tiene dos clases, `arbol` y `grupo`. Solo se detecta y cuenta `arbol`;
`grupo` se descarta en la predicción, así que no aparece en el GeoJSON ni suma al conteo ni al área.
Para ver ambas: `$env:CLASES = "arbol,grupo"`. Con un modelo de una sola clase llamada `tree`
(el modelo anterior) no se filtra nada y se muestra un aviso.

---

## 7. (Opcional) Correrlo como API

Si en algún momento se necesita como servicio web:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload
```

Y abrir <http://127.0.0.1:8000/docs> en el navegador. Para apagarlo: **Ctrl + C**.

| Endpoint | Qué hace |
|---|---|
| `POST /trabajos` | sube el `.tif` y devuelve un `id` (PNG/JPG responde 415: aún no disponible) |
| `GET /trabajos/{id}` | estado, progreso y resumen (conteo y área) |
| `GET /trabajos/{id}/resultado` | descarga el GeoJSON |
| `GET /salud` | confirma que el modelo cargó |

---

## 8. Pruebas automáticas

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt   # solo la primera vez
.\.venv\Scripts\python.exe -m pytest -q
```

Las pruebas usan un segmentador falso, así que no necesitan el modelo ni GPU.

---

## 9. Arquitectura

Capas con "puertos y adaptadores": el núcleo solo conoce interfaces, y las piezas
concretas (rasterio, YOLO, disco, hilos) se pueden cambiar sin tocarlo.

```
API (HTTP)  →  Servicios (núcleo)  →  Puertos (interfaces)  ←  Adaptadores
```

```
app/
├─ main.py              # crea la API; traduce errores a códigos HTTP
├─ config.py            # variables de entorno
├─ contenedor.py        # ÚNICO lugar donde se eligen las clases concretas
├─ api/                 # endpoints y esquemas (solo HTTP, sin lógica)
├─ dominio/             # modelos, errores e interfaces (puertos.py)
├─ servicios/           # núcleo: casos de uso, pipeline y teselado
└─ adaptadores/         # rasterio, YOLO, GeoJSON, memoria, disco, cola de hilos
   └─ lectores/         # un lector por formato + fábrica que elige por extensión
procesar.py             # consola: usa el mismo servicio que la API
tests/                  # pruebas
```

**Cómo se extiende (sin tocar el núcleo):**

| Quiero... | Hago... |
|---|---|
| Aceptar PNG/JPG | implementar `adaptadores/lectores/lector_imagen_simple.py` (ya está registrado en la fábrica) |
| Detectar maleza | entrenar otro modelo y usar `RUTA_MODELO`; las clases salen del propio modelo |
| Guardar trabajos en PostgreSQL | crear `repositorio_postgres.py` con `guardar/obtener/actualizar` y cambiarlo en `contenedor.py` |
| Usar Celery/RQ | crear `ejecutor_celery.py` con `enviar/cerrar` y cambiarlo en `contenedor.py` |
| Otro modelo (no YOLO) | crear un adaptador con `segmentar(imagen) -> list[Deteccion]` |

---

## Problemas comunes

| Mensaje                                   | Solución                                                     |
|-------------------------------------------|--------------------------------------------------------------|
| `No existe el archivo`                    | Revisen la ruta; si tiene espacios, pónganla entre comillas: `"C:\mi carpeta\orto.tif"` |
| `no tiene CRS (no está georreferenciado)` | Exporten el ortomosaico como GeoTIFF desde el software de fotogrametría |
| `no se calcularon áreas`                  | El CRS está en grados: reproyecten a EPSG:5367 (paso 4)      |
| `No se encontró el modelo`                | Copien `best.pt` a la carpeta `modelos\`                    |
| `No module named 'app'`                   | Corran los comandos desde la carpeta del proyecto (`cd C:\Users\Ale\Desktop\api_copas_yolo`) |
| `python` no se reconoce                   | Instalen Python y marquen "Add Python to PATH"               |
