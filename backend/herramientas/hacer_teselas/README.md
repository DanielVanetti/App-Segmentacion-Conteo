# hacer_teselas

Corta el ortomosaico en teselas y arma un dataset YOLO-seg (imágenes + etiquetas) a partir de las copas anotadas y de las zonas train/val.

## Comando

Desde la carpeta `backend` (las rutas `Tiff\...` son de ejemplo: usá donde tengás el ortomosaico y las anotaciones):

```powershell
cd "C:\Users\Daniel\Desktop\LICENCIATURA CURSOS\SEMESTRE 2\DISEÑO DE INVESTIGACIONES 2\APP\App_Segmentacion_Conteo\backend"

.\.venv\Scripts\python.exe herramientas\hacer_teselas\hacer_teselas.py --tif "Tiff\Mario_BLion_Santa_Cruz.tif" --poligonos "Tiff\Practica\anotacion_copas_santa_cruz.gpkg" --zonas "Tiff\Practica\zonas_entrenamiento_santa_cruz.gpkg" --gsd 0.05 --out "Tiff\Practica\dataset_sc2"
```

Para solo contar las teselas sin escribir nada, agregar `--solo_resumen`.

## Qué significa cada parte

| Parte | Significado |
|---|---|
| `.\.venv\Scripts\python.exe` | Python del entorno virtual del backend (ya trae `numpy`, `rasterio`, `shapely`, `pillow`). |
| `herramientas\hacer_teselas\hacer_teselas.py` | El script que corta las teselas. |
| `--tif` | Ortomosaico GeoTIFF que se va a cortar. |
| `--poligonos` | Copas anotadas a mano (`.gpkg` o `.geojson`). Son las etiquetas. |
| `--zonas` | Rectángulos que marcan qué parte es `train` y cuál `val`. Solo se generan teselas dentro de ellas. |
| `--gsd 0.05` | Resolución de trabajo: 5 cm/px (la del modelo). Con `0` se usa la resolución original. |
| `--out` | Carpeta de salida. |

## Valores por defecto

- `--tile 1024`: lado de la tesela en px.
- `--solape 0.25`: solape entre teselas vecinas.
- `--franja 10`: metros de separación entre zonas train y val, para que un mismo árbol no quede en ambos lados.

## Opciones útiles

- `--clases "arbol,grupo"`: fija el orden de las clases (por defecto se detectan de los datos).
- `--sin_vacias`: descarta teselas sin ningún polígono.
- `--max 20`: limita el número de teselas, para pruebas.
- `--tabla_poligonos` / `--tabla_zonas`: nombre de la capa si el GPKG trae varias.

## Resultado

Dentro de la carpeta `--out` quedan tres datasets listos para entrenar:

- `fold1`: entrena con zonas train, valida con zonas val.
- `fold2`: entrena con zonas val, valida con zonas train.
- `final`: entrena con todo. Su validación no sirve para medir el modelo, porque ya vio esos datos.

Las comillas son necesarias porque algunas rutas tienen espacios.
