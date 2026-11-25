"""Proyectos y ortomosaicos por HTTP (RF-01 a RF-04), con el repositorio en memoria."""

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

from app.contenedor import construir
from app.main import crear_app
from tests.conftest import SegmentadorFalso, crear_geotiff


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("DIR_TRABAJOS", str(tmp_path / "trabajos"))
    monkeypatch.setenv("DIR_DATOS", str(tmp_path / "datos"))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    app = crear_app(lambda cfg: construir(cfg, segmentador=SegmentadorFalso()))
    with TestClient(app) as c:
        yield c


def _crear(cliente, **datos):
    cuerpo = {"nombre": "Parcela 10", "sitio": "Santa Cruz", **datos}
    return cliente.post("/api/proyectos", json=cuerpo)


def _subir(cliente, id_proyecto, ruta, nombre=None):
    with open(ruta, "rb") as f:
        return cliente.post(f"/api/proyectos/{id_proyecto}/ortomosaico",
                            files={"archivo": (nombre or ruta.name, f)})


def _tif(ruta, bandas=3, tam_pixel=0.05, crs="EPSG:5367"):
    perfil = dict(driver="GTiff", width=200, height=100, count=bandas, dtype="uint8",
                  transform=from_origin(360000, 1150000, tam_pixel, tam_pixel))
    if crs:
        perfil["crs"] = crs
    with rasterio.open(ruta, "w", **perfil) as d:
        d.write(np.full((bandas, 100, 200), 120, dtype=np.uint8))
    return ruta


# --- proyectos ---------------------------------------------------------------------
def test_crear_listar_obtener_eliminar(cliente):
    r = _crear(cliente, descripcion="Ensayo", fechaVuelo="2026-03-14")
    assert r.status_code == 201
    p = r.json()
    assert p["nombre"] == "Parcela 10" and p["fechaVuelo"] == "2026-03-14"
    assert p["estado"] == "sin_ortomosaico" and p["ortomosaicoId"] is None
    assert {"creadoEn", "actualizadoEn", "totalCopas", "urlMiniatura"} <= p.keys()

    assert [x["id"] for x in cliente.get("/api/proyectos").json()] == [p["id"]]
    assert cliente.get(f"/api/proyectos/{p['id']}").json()["id"] == p["id"]

    assert cliente.delete(f"/api/proyectos/{p['id']}").status_code == 204
    r = cliente.get(f"/api/proyectos/{p['id']}")
    assert r.status_code == 404 and r.json()["mensaje"] == "El proyecto solicitado no existe."


def test_lista_incluye_todos(cliente):
    a = _crear(cliente, nombre="A").json()
    b = _crear(cliente, nombre="B").json()
    ids = [x["id"] for x in cliente.get("/api/proyectos").json()]
    assert set(ids) == {a["id"], b["id"]}


@pytest.mark.parametrize("cuerpo, texto", [
    ({"nombre": "   "}, "obligatorio"),
    ({"nombre": "X", "fechaVuelo": "14/03/2026"}, "AAAA-MM-DD"),
    ({}, "nombre"),   # falta el campo: lo rechaza la validación de FastAPI, en español
])
def test_crear_rechaza_datos_invalidos(cliente, cuerpo, texto):
    r = cliente.post("/api/proyectos", json=cuerpo)
    assert r.status_code == 422
    assert texto in r.json()["mensaje"]


def test_eliminar_inexistente(cliente):
    assert cliente.delete("/api/proyectos/nada").status_code == 404


# --- ortomosaico ---------------------------------------------------------------------
def test_cargar_ortomosaico_valido(cliente, tmp_path):
    p = _crear(cliente).json()
    r = _subir(cliente, p["id"], _tif(tmp_path / "orto.tif"))
    assert r.status_code == 201, r.json()
    o = r.json()
    assert o["crs"] == "EPSG:5367" and o["resolucionCmPorPixel"] == 5.0
    assert (o["anchoPx"], o["altoPx"], o["bandas"]) == (200, 100, 3)
    assert o["validacion"] == {"formato": "valido", "crs": "valido", "resolucion": "valido",
                               "mensajes": []}
    ext = o["extension"]
    assert ext["minX"] == pytest.approx(360000) and ext["maxX"] == pytest.approx(360010)
    assert o["urlCog"] == f"/api/proyectos/{p['id']}/ortomosaico/archivo"

    proyecto = cliente.get(f"/api/proyectos/{p['id']}").json()
    assert proyecto["estado"] == "ortomosaico_cargado" and proyecto["ortomosaicoId"] == o["id"]
    assert cliente.get(f"/api/proyectos/{p['id']}/ortomosaico").json()["id"] == o["id"]


def test_archivo_admite_rangos(cliente, tmp_path):
    p = _crear(cliente).json()
    ruta = _tif(tmp_path / "orto.tif")
    _subir(cliente, p["id"], ruta)
    r = cliente.get(f"/api/proyectos/{p['id']}/ortomosaico/archivo",
                    headers={"Range": "bytes=0-15"})
    assert r.status_code == 206 and r.content == ruta.read_bytes()[:16]


def test_resolucion_fuera_de_rango_es_advertencia(cliente, tmp_path):
    p = _crear(cliente).json()
    r = _subir(cliente, p["id"], _tif(tmp_path / "grueso.tif", tam_pixel=0.3))
    assert r.status_code == 201
    v = r.json()["validacion"]
    assert v["resolucion"] == "advertencia" and "30.0 cm/píxel" in v["mensajes"][0]


def test_otro_crs_proyectado_es_advertencia_y_se_reproyecta(cliente, tmp_path):
    p = _crear(cliente).json()
    # UTM 16N, en la zona de Guanacaste
    r = _subir(cliente, p["id"], _tif(tmp_path / "utm.tif", crs="EPSG:32616"))
    o = r.json()
    assert r.status_code == 201 and o["validacion"]["crs"] == "advertencia"
    assert o["extension"]["minX"] != pytest.approx(360000)   # convertida a CRTM05
    assert o["extensionNativa"]["minX"] == pytest.approx(360000)


@pytest.mark.parametrize("hacer, codigo, texto", [
    (lambda d: _tif(d / "sin_crs.tif", crs=None), 422, "sistema de referencia"),
    (lambda d: _tif(d / "gris.tif", bandas=1), 422, "3 (rojo, verde y azul)"),
])
def test_ortomosaico_invalido_se_rechaza_y_no_se_guarda(cliente, tmp_path, hacer, codigo, texto):
    p = _crear(cliente).json()
    r = _subir(cliente, p["id"], hacer(tmp_path))
    assert r.status_code == codigo and texto in r.json()["mensaje"]
    assert cliente.get(f"/api/proyectos/{p['id']}/ortomosaico").status_code == 404
    assert not any((tmp_path / "datos" / "temporales").iterdir())   # sin basura


def test_archivo_invalido_no_borra_el_anterior(cliente, tmp_path):
    p = _crear(cliente).json()
    bueno = _subir(cliente, p["id"], _tif(tmp_path / "bueno.tif")).json()
    malo = tmp_path / "malo.tif"
    malo.write_bytes(b"no soy un tif")
    r = _subir(cliente, p["id"], malo)
    assert r.status_code == 422 and "GeoTIFF" in r.json()["mensaje"]
    assert cliente.get(f"/api/proyectos/{p['id']}/ortomosaico").json()["id"] == bueno["id"]


def test_reemplazar_ortomosaico(cliente, tmp_path):
    p = _crear(cliente).json()
    a = _subir(cliente, p["id"], _tif(tmp_path / "a.tif")).json()
    b = _subir(cliente, p["id"], crear_geotiff(tmp_path / "b.tif")).json()
    assert a["id"] != b["id"]
    actual = cliente.get(f"/api/proyectos/{p['id']}/ortomosaico").json()
    assert actual["id"] == b["id"] and actual["anchoPx"] == 2500


@pytest.mark.parametrize("nombre, codigo", [("foto.png", 415), ("notas.txt", 400)])
def test_formatos_no_soportados(cliente, tmp_path, nombre, codigo):
    p = _crear(cliente).json()
    ruta = tmp_path / nombre
    ruta.write_bytes(b"x")
    assert _subir(cliente, p["id"], ruta).status_code == codigo


def test_ortomosaico_de_proyecto_inexistente(cliente, tmp_path):
    assert _subir(cliente, "nada", _tif(tmp_path / "o.tif")).status_code == 404
    assert cliente.get("/api/proyectos/nada/ortomosaico").status_code == 404


def test_eliminar_proyecto_borra_sus_archivos(cliente, tmp_path):
    p = _crear(cliente).json()
    _subir(cliente, p["id"], _tif(tmp_path / "orto.tif"))
    carpeta = tmp_path / "datos" / "proyectos" / p["id"]
    assert carpeta.exists()
    cliente.delete(f"/api/proyectos/{p['id']}")
    assert not carpeta.exists()


def test_salud_informa_persistencia(cliente):
    assert cliente.get("/salud").json()["persistencia"] == "memoria"


def test_json_mal_formado_responde_en_espanol(cliente):
    r = cliente.post("/api/proyectos", content=b'{"nombre": "Parcela\xed"}',
                     headers={"Content-Type": "application/json"})
    assert r.status_code in (400, 422)
    assert "There was" not in r.json()["mensaje"]
