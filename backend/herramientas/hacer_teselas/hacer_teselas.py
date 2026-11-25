# -*- coding: utf-8 -*-
"""
hacer_teselas.py  --  ortomosaico + poligonos anotados + zonas  ->  dataset YOLO-seg

Que hace
  1. Lee los poligonos anotados (copas, parcelas, edificios... lo que sea) de un GeoPackage o GeoJSON.
  2. Lee las zonas rectangulares (GeoPackage o GeoJSON) que dicen que parte del ortomosaico es
     de entrenamiento y cual de validacion.
  3. Separa train de val: quita de cada zona una franja de seguridad (--franja m) hacia
     las zonas del otro conjunto, para que no haya objetos vecinos en ambos lados.
  4. Corta el ortomosaico en teselas de --tile px (con solape), SOLO dentro de las zonas.
     Los pixeles fuera de la zona (o sin datos) se rellenan con gris 114.
  5. Escribe imagenes y etiquetas YOLO-seg (clase = indice, coordenadas 0-1).
  6. Arma tres datasets listos para entrenar:
        fold1 : entrena con zonas train, valida con zonas val
        fold2 : entrena con zonas val,   valida con zonas train
        final : entrena con todo (su val NO sirve para medir: ya fue visto)

Formato de los datos (todo configurable por argumentos)
  poligonos : campo de clase (--campo_clase) y, opcionalmente, de conjunto (--campo_conjunto).
              Si un poligono no trae conjunto valido, hereda el de la zona que lo contiene.
  zonas     : campo de conjunto (--campo_conjunto_zona, valores train/val) y de nombre (--campo_zona).
  clases    : se detectan solas de los datos, o se fijan con --clases "arbol,grupo" (el orden = indice).
  tabla     : en un GPKG se detecta sola si solo hay una; si hay varias, usa --tabla_poligonos / --tabla_zonas.

Requisitos:   pip install numpy rasterio shapely pillow

Ejemplos:
    python hacer_teselas.py --tif orto.tif --poligonos anot.gpkg --zonas zonas.gpkg --solo_resumen
    python hacer_teselas.py --tif orto.tif --poligonos anot.gpkg --zonas zonas.geojson --gsd 0.05
    python hacer_teselas.py --tif orto.tif --poligonos anot.gpkg --zonas zonas.gpkg --gsd 0   # resolucion original
"""
import argparse, csv, json, os, shutil, sqlite3, sys, tempfile
import numpy as np
import shapely.wkb
from shapely.geometry import shape, box, Polygon, MultiPolygon
from shapely.ops import unary_union
from shapely.validation import make_valid
from PIL import Image, ImageDraw

CONJUNTOS = ("train", "val")
PALETA = [(255, 60, 60), (60, 120, 255), (60, 200, 90), (255, 200, 40), (190, 80, 220), (40, 210, 210)]


# ----------------------------------------------------------------------------- lectura
def _valida(g):
    return g if g.is_valid else make_valid(g)


def _leer_gpkg(path, tabla):
    """Lee una tabla de un GeoPackage desde una COPIA temporal (incluye -wal/-shm)."""
    tmp = tempfile.mkdtemp()
    base = os.path.basename(path)
    for suf in ("", "-wal", "-shm"):
        if os.path.exists(path + suf):
            shutil.copy(path + suf, os.path.join(tmp, base + suf))
    con = sqlite3.connect(os.path.join(tmp, base))
    try:
        tablas = [r[0] for r in con.execute("select table_name from gpkg_contents where data_type='features'")]
        if tabla is None:
            if len(tablas) != 1:
                sys.exit("%s tiene varias capas %s: indica cual con --tabla_poligonos / --tabla_zonas." % (base, tablas))
            tabla = tablas[0]
        elif tabla not in tablas:
            sys.exit("%s no tiene la capa '%s'. Capas: %s" % (base, tabla, tablas))
        colgeom, epsg = con.execute(
            "select column_name, srs_id from gpkg_geometry_columns where table_name=?", (tabla,)).fetchone()
        cols = [c[1] for c in con.execute('pragma table_info("%s")' % tabla)]
        con.row_factory = sqlite3.Row
        out = []
        for i, row in enumerate(con.execute('select * from "%s"' % tabla)):
            blob = row[colgeom]
            if blob is None or (blob[3] & 0x10):  # geometria vacia
                continue
            tam = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}[(blob[3] >> 1) & 7]
            g = _valida(shapely.wkb.loads(bytes(blob[8 + tam:])))
            props = {c: row[c] for c in cols if c != colgeom}
            out.append(dict(id=props.get("fid", i), props=props, geom=g))
    finally:
        con.close()
    return out, epsg


def _leer_geojson(path):
    gj = json.load(open(path, encoding="utf-8"))
    out = [dict(id=i, props=f.get("properties") or {}, geom=_valida(shape(f["geometry"])))
           for i, f in enumerate(gj["features"]) if f.get("geometry")]
    return out, None


def leer_vectores(path, tabla=None):
    if not os.path.exists(path):
        sys.exit("No existe: %s" % path)
    if path.lower().endswith((".geojson", ".json")):
        return _leer_geojson(path)
    return _leer_gpkg(path, tabla)


def cargar_poligonos(a, zonas):
    regs, epsg = leer_vectores(a.poligonos, a.tabla_poligonos)
    if regs and a.campo_clase not in regs[0]["props"]:
        sys.exit("Los poligonos no tienen el campo '%s'. Campos: %s (usa --campo_clase)"
                 % (a.campo_clase, list(regs[0]["props"])))
    if a.clases:
        clases = [c.strip() for c in a.clases.split(",") if c.strip()]
    else:
        clases = sorted({str(r["props"][a.campo_clase]) for r in regs if r["props"][a.campo_clase] is not None})
    indice = {c: i for i, c in enumerate(clases)}

    polis, sin_conj, sin_clase = [], [], 0
    for r in regs:
        cl = r["props"].get(a.campo_clase)
        if cl is None or str(cl) not in indice:
            sin_clase += 1
            continue
        conj = r["props"].get(a.campo_conjunto)
        if conj not in CONJUNTOS:   # hereda el conjunto de la zona que lo contiene
            punto = r["geom"].representative_point()
            conj = next((z["conjunto"] for z in zonas if z["geom"].contains(punto)), None)
        p = dict(fid=r["id"], geom=r["geom"], clase=str(cl), conjunto=conj)
        (polis if conj in CONJUNTOS else sin_conj).append(p)
    return polis, sin_conj, sin_clase, clases, epsg


def cargar_zonas(a):
    regs, epsg = leer_vectores(a.zonas, a.tabla_zonas)
    zonas = []
    for i, r in enumerate(regs):
        conj = r["props"].get(a.campo_conjunto_zona)
        if conj not in CONJUNTOS:
            sys.exit("La zona %s tiene conjunto '%s' (campo '%s'); debe ser train o val."
                     % (r["props"].get(a.campo_zona, i), conj, a.campo_conjunto_zona))
        zonas.append(dict(zona=str(r["props"].get(a.campo_zona, "z%d" % i)), conjunto=conj, geom=r["geom"]))
    if not zonas:
        sys.exit("El archivo de zonas no tiene geometrias.")
    return zonas, epsg


def poligonos(g):
    """Devuelve solo las partes poligonales de una geometria."""
    if g.is_empty:
        return []
    if isinstance(g, Polygon):
        return [g]
    if isinstance(g, MultiPolygon):
        return list(g.geoms)
    return [p for geom in getattr(g, "geoms", []) for p in poligonos(geom)]


def posiciones(lo, hi, tam, paso):
    if hi - lo <= tam:
        return [lo]
    pos, p = [], lo
    while p + tam < hi:
        pos.append(p)
        p += paso
    pos.append(hi - tam)
    return pos


# ----------------------------------------------------------------------------- principal
def main():
    ap = argparse.ArgumentParser(description="Ortomosaico + poligonos + zonas -> dataset YOLO-seg")
    ap.add_argument("--tif", required=True, help="ortomosaico GeoTIFF")
    ap.add_argument("--poligonos", "--gpkg", dest="poligonos", required=True,
                    help="poligonos anotados (.gpkg o .geojson)")
    ap.add_argument("--zonas", required=True, help="zonas train/val (.gpkg o .geojson)")
    ap.add_argument("--out", default="dataset", help="carpeta de salida")
    ap.add_argument("--tabla_poligonos", help="capa del GPKG de poligonos (auto si solo hay una)")
    ap.add_argument("--tabla_zonas", help="capa del GPKG de zonas (auto si solo hay una)")
    ap.add_argument("--campo_clase", default="clase")
    ap.add_argument("--campo_conjunto", default="conjunto", help="campo train/val de los poligonos (opcional)")
    ap.add_argument("--campo_conjunto_zona", default="conjunto", help="campo train/val de las zonas")
    ap.add_argument("--campo_zona", default="zona", help="campo con el nombre de la zona")
    ap.add_argument("--clases", help='clases en orden, ej. "arbol,grupo". Por defecto se detectan de los datos')
    ap.add_argument("--tile", type=int, default=1024, help="lado de la tesela en px")
    ap.add_argument("--gsd", type=float, default=0.05,
                    help="tamano de pixel de las teselas en m/px. 0 = el original del ortomosaico")
    ap.add_argument("--solape", type=float, default=0.25, help="fraccion de solape entre teselas")
    ap.add_argument("--franja", type=float, default=10.0, help="m de separacion entre zonas de train y val")
    ap.add_argument("--min_visible", type=float, default=0.30,
                    help="un poligono recortado se conserva si queda al menos esta fraccion dentro de la tesela")
    ap.add_argument("--min_valido", type=float, default=0.5, help="fraccion minima de pixeles con datos")
    ap.add_argument("--min_cobertura", type=float, default=0.2, help="fraccion minima de la ventana dentro de la zona")
    ap.add_argument("--sin_vacias", action="store_true", help="descartar teselas sin ningun poligono")
    ap.add_argument("--previas", type=int, default=6, help="n de imagenes de control con poligonos dibujados")
    ap.add_argument("--max", type=int, default=0, help="limite de teselas (solo para pruebas)")
    ap.add_argument("--solo_resumen", action="store_true", help="contar sin leer ni escribir imagenes")
    a = ap.parse_args()

    zonas, epsg_z = cargar_zonas(a)
    copas, sin_conj, sin_clase, clases, epsg_p = cargar_poligonos(a, zonas)
    if not clases:
        sys.exit("No hay clases: revisa --campo_clase o pasa --clases.")
    indice = {c: i for i, c in enumerate(clases)}
    print("poligonos:", len(copas), "| clases:", indice, "| zonas:", [(z["zona"], z["conjunto"]) for z in zonas])

    # ---- georreferencia del ortomosaico
    src, gsd0 = None, None
    try:
        import rasterio
        from rasterio.windows import from_bounds
        from rasterio.enums import Resampling
        src = rasterio.open(a.tif)
        gsd0 = abs(src.transform.a)
        epsg_t = src.crs.to_epsg() if src.crs else None
        for nombre, e in (("poligonos", epsg_p), ("zonas", epsg_z)):
            if e and epsg_t and e != epsg_t:
                print("(AVISO) CRS distinto: %s EPSG:%s vs ortomosaico EPSG:%s. Reproyecta antes de seguir." % (nombre, e, epsg_t))
        if not a.solo_resumen and src.dtypes[0] != "uint8":
            sys.exit("El ortomosaico es %s; convierte a 8 bits (uint8) antes de teselar." % src.dtypes[0])
    except Exception as e:
        if not a.solo_resumen:
            sys.exit("No pude abrir el ortomosaico con rasterio: %s" % e)
        print("(aviso) sin rasterio/tif (%s)" % e)
    if a.gsd and a.gsd > 0:
        gsd = a.gsd
    elif gsd0:
        gsd = gsd0
    else:
        sys.exit("Con --gsd 0 hace falta poder leer el ortomosaico.")
    tile_m = a.tile * gsd
    paso = tile_m * (1 - a.solape)
    print("GSD original %s m/px | GSD de las teselas %.4f m/px | tesela = %d px = %.1f m | paso %.1f m"
          % ("%.4f" % gsd0 if gsd0 else "?", gsd, a.tile, tile_m, paso))

    # ---- zonas con franja de seguridad
    piezas = []
    for z in zonas:
        otros = [o["geom"] for o in zonas if o["conjunto"] != z["conjunto"]]
        g = z["geom"]
        if otros and a.franja > 0:
            g = g.difference(unary_union(otros).buffer(a.franja))
        for p in poligonos(g):
            piezas.append(dict(zona=z["zona"], conjunto=z["conjunto"], geom=p))
    print("zonas utiles (tras franja de %.0f m): %d" % (a.franja, len(piezas)))

    por_conj = {c: [p for p in copas if p["conjunto"] == c] for c in CONJUNTOS}

    # ---- ventanas
    ventanas = []
    for pz in piezas:
        minx, miny, maxx, maxy = pz["geom"].bounds
        xs = posiciones(minx, maxx, tile_m, paso)
        ys = posiciones(miny, maxy, tile_m, paso)
        for i, yb in enumerate(sorted(ys, reverse=True)):
            for j, xl in enumerate(xs):
                w = box(xl, yb, xl + tile_m, yb + tile_m)
                if w.intersection(pz["geom"]).area / (tile_m ** 2) < a.min_cobertura:
                    continue
                ventanas.append(dict(pz=pz, i=i, j=j, x0=xl, yb=yb, win=w))
    print("ventanas candidatas:", len(ventanas))

    # ---- salida
    d_img = os.path.join(a.out, "teselas", "images")
    d_lab = os.path.join(a.out, "teselas", "labels")
    d_pre = os.path.join(a.out, "previas")
    if not a.solo_resumen:
        for d in (d_img, d_lab, d_pre):
            os.makedirs(d, exist_ok=True)

    filas = []
    usadas = {c: set() for c in CONJUNTOS}
    contar_inst = {(c, k): 0 for c in CONJUNTOS for k in clases}
    n_prev = {c: 0 for c in CONJUNTOS}
    n_escritas = n_sin_datos = n_vacias_omitidas = n_recortadas = n_descartadas = con_huecos = 0

    for v in ventanas:
        if a.max and n_escritas >= a.max:
            break
        pz, win = v["pz"], v["win"]
        conj = pz["conjunto"]
        area_win = tile_m ** 2
        lineas, dibujo = [], []
        recort = desc = 0
        cnt = {k: 0 for k in clases}
        for c in por_conj[conj]:
            g = c["geom"]
            if not g.intersects(win):
                continue
            parte = g.intersection(win).intersection(pz["geom"])
            if parte.is_empty:
                continue
            visible = parte.area / g.area
            if visible < a.min_visible and parte.area < 0.25 * area_win:
                desc += 1
                continue
            if visible < 0.999:
                recort += 1
            for p in poligonos(parte):
                if p.area < (6 * gsd) ** 2:   # trozo diminuto
                    continue
                if len(p.interiors):
                    con_huecos += 1
                p = p.simplify(0.4 * gsd, preserve_topology=True)
                pts = [((x - v["x0"]) / tile_m, (v["yb"] + tile_m - y) / tile_m) for x, y in p.exterior.coords[:-1]]
                if len(pts) < 3:
                    continue
                pts = [(min(1.0, max(0.0, x)), min(1.0, max(0.0, y))) for x, y in pts]
                lineas.append("%d " % indice[c["clase"]] + " ".join("%.6f %.6f" % q for q in pts))
                dibujo.append((c["clase"], pts))
                cnt[c["clase"]] += 1
            usadas[conj].add(c["fid"])
        if a.sin_vacias and not lineas:
            n_vacias_omitidas += 1
            continue

        nombre = "%s_%02d_%02d" % (pz["zona"], v["i"], v["j"])
        vfrac = float("nan")
        if not a.solo_resumen:
            win_r = from_bounds(v["x0"], v["yb"], v["x0"] + tile_m, v["yb"] + tile_m, src.transform)
            arr = src.read(window=win_r, out_shape=(src.count, a.tile, a.tile), boundless=True,
                           fill_value=0, resampling=Resampling.average)
            # mascara de la zona (pixeles dentro de la zona util)
            m = Image.new("L", (a.tile, a.tile), 0)
            dr = ImageDraw.Draw(m)
            for p in poligonos(win.intersection(pz["geom"])):
                dr.polygon([((x - v["x0"]) / gsd, (v["yb"] + tile_m - y) / gsd) for x, y in p.exterior.coords], fill=255)
            en_zona = np.array(m) > 0
            alfa = arr[3] > 0 if src.count >= 4 else np.ones((a.tile, a.tile), bool)
            valido = alfa & en_zona
            vfrac = valido.sum() / max(1, en_zona.sum())
            if vfrac < a.min_valido:
                n_sin_datos += 1
                continue
            rgb = np.transpose(arr[:3], (1, 2, 0)) if src.count >= 3 else np.dstack([arr[0]] * 3)
            rgb = rgb.astype(np.uint8)
            rgb[~valido] = 114
            im = Image.fromarray(rgb)
            im.save(os.path.join(d_img, nombre + ".png"), compress_level=3)
            with open(os.path.join(d_lab, nombre + ".txt"), "w") as f:
                f.write("\n".join(lineas) + ("\n" if lineas else ""))
            if n_prev[conj] < a.previas and lineas:
                pv = im.copy(); dd = ImageDraw.Draw(pv)
                for cl, pts in dibujo:
                    dd.line([(x * a.tile, y * a.tile) for x, y in pts + [pts[0]]],
                            fill=PALETA[indice[cl] % len(PALETA)], width=3)
                pv.resize((a.tile // 2, a.tile // 2)).save(os.path.join(d_pre, "%s.jpg" % nombre), quality=90)
                n_prev[conj] += 1
        n_escritas += 1
        n_recortadas += recort
        n_descartadas += desc
        for k in cnt:
            contar_inst[(conj, k)] += cnt[k]
        fila = dict(tesela=nombre, zona=pz["zona"], conjunto=conj, x_izq_m=round(v["x0"], 2),
                    y_sup_m=round(v["yb"] + tile_m, 2), px=a.tile, gsd_m=round(gsd, 5), lado_m=round(tile_m, 2))
        fila.update({"n_" + k: cnt[k] for k in clases})
        fila.update(recortadas=recort, descartadas=desc, frac_valida=round(vfrac, 3) if vfrac == vfrac else "")
        filas.append(fila)

    # ---- resumen
    L = ["=== RESUMEN ===",
         "GSD teselas %.4f m/px | tesela %d px = %.1f m | solape %.0f%% | franja train/val %.0f m"
         % (gsd, a.tile, tile_m, 100 * a.solape, a.franja)]
    for conj in CONJUNTOS:
        ft = [f for f in filas if f["conjunto"] == conj]
        n_v = sum(1 for f in ft if sum(f["n_" + k] for k in clases) == 0)
        tot = {k: sum(1 for c in por_conj[conj] if c["clase"] == k) for k in clases}
        uso = {k: sum(1 for c in por_conj[conj] if c["clase"] == k and c["fid"] in usadas[conj]) for k in clases}
        L.append("%-5s teselas %4d (vacias %d)" % (conj, len(ft), n_v))
        L.append("      anotados: %s | en alguna tesela: %s | instancias en teselas (con repeticion por solape): %s"
                 % (tot, uso, {k: contar_inst[(conj, k)] for k in clases}))
    L.append("recortados por el borde de una tesela: %d | etiquetas descartadas por quedar <%.0f%% visibles: %d"
             % (n_recortadas, 100 * a.min_visible, n_descartadas))
    L.append("teselas descartadas por falta de datos: %d | por estar vacias (--sin_vacias): %d" % (n_sin_datos, n_vacias_omitidas))
    L.append("poligonos con huecos internos (se ignoran los huecos): %d" % con_huecos)
    if sin_conj:
        L.append("AVISO: %d poligonos fuera de toda zona y sin conjunto (no se usan)" % len(sin_conj))
    if sin_clase:
        L.append("AVISO: %d poligonos sin clase valida (no se usan)" % sin_clase)
    perd = {}
    for conj in CONJUNTOS:
        for c in por_conj[conj]:
            if c["fid"] not in usadas[conj]:
                perd[(conj, c["clase"])] = perd.get((conj, c["clase"]), 0) + 1
    L.append("poligonos que no entraron en ninguna tesela (franja, bordes o sin datos): %s" % (perd or "ninguno"))
    txt = "\n".join(L)
    print("\n" + txt)
    if a.solo_resumen:
        return
    if not filas:
        sys.exit("No se genero ninguna tesela: revisa CRS, zonas y --min_valido.")

    with open(os.path.join(a.out, "resumen_teselas.txt"), "w", encoding="utf-8") as f:
        f.write(txt + "\n")
    with open(os.path.join(a.out, "manifiesto.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(filas[0].keys()))
        w.writeheader(); w.writerows(filas)

    # ---- datasets (fold1, fold2, final) con enlaces duros o copias
    def poner(src_n, dst_dir_img, dst_dir_lab):
        os.makedirs(dst_dir_img, exist_ok=True); os.makedirs(dst_dir_lab, exist_ok=True)
        for sub, d in ((os.path.join(d_img, src_n + ".png"), dst_dir_img), (os.path.join(d_lab, src_n + ".txt"), dst_dir_lab)):
            dst = os.path.join(d, os.path.basename(sub))
            if os.path.exists(dst):
                os.remove(dst)
            try:
                os.link(sub, dst)
            except OSError:
                shutil.copy2(sub, dst)

    nombres_yaml = "".join("  %d: %s\n" % (i, k) for i, k in enumerate(clases))

    def armar(nombre, tr, va):
        raiz = os.path.abspath(os.path.join(a.out, "dataset_yolo", nombre))
        if os.path.isdir(raiz):
            shutil.rmtree(raiz)
        for conjs, sp in ((tr, "train"), (va, "val")):
            for f in filas:
                if f["conjunto"] in conjs:
                    poner(f["tesela"], os.path.join(raiz, "images", sp), os.path.join(raiz, "labels", sp))
        with open(os.path.join(raiz, "data.yaml"), "w", encoding="utf-8") as y:
            y.write("path: %s\ntrain: images/train\nval: images/val\nnames:\n%s" % (raiz.replace("\\", "/"), nombres_yaml))
        print("dataset", nombre, ":", raiz)

    armar("fold1", ["train"], ["val"])
    armar("fold2", ["val"], ["train"])
    armar("final", ["train", "val"], ["val"])
    print("\nListo. Control visual: %s" % d_pre)


if __name__ == "__main__":
    main()
