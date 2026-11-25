import json
import time

import pytest
from fastapi.testclient import TestClient

from app.contenedor import construir
from app.main import crear_app
from tests.conftest import SegmentadorFalso, crear_geotiff


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setenv("DIR_TRABAJOS", str(tmp_path / "trabajos"))
    app = crear_app(lambda cfg: construir(cfg, segmentador=SegmentadorFalso()))
    with TestClient(app) as c:
        yield c


def _subir(cliente, ruta, nombre=None):
    with open(ruta, "rb") as f:
        return cliente.post("/trabajos", files={"archivo": (nombre or ruta.name, f)})


def _esperar(cliente, id_trabajo, limite=30):
    for _ in range(limite * 10):
        estado = cliente.get(f"/trabajos/{id_trabajo}").json()
        if estado["estado"] in ("terminado", "error"):
            return estado
        time.sleep(0.1)
    raise TimeoutError


def test_salud(cliente):
    r = cliente.get("/salud").json()
    assert r["ok"] and r["clases"] == {"0": "tree"} and ".png" in r["formatos"]


def test_flujo_completo(cliente, geotiff):
    r = _subir(cliente, geotiff)
    assert r.status_code == 202
    assert r.json()["estado"] == "en cola"
    estado = _esperar(cliente, r.json()["id"])
    assert estado["estado"] == "terminado"
    assert estado["resumen"]["conteo"] == 2

    r = cliente.get(f"/trabajos/{estado['id']}/resultado")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/geo+json"
    assert "attachment" in r.headers["content-disposition"]
    assert len(json.loads(r.content)["features"]) == 2


def test_png_responde_415(cliente, tmp_path):
    ruta = tmp_path / "foto.png"
    ruta.write_bytes(b"\x89PNG")
    r = _subir(cliente, ruta)
    assert r.status_code == 415
    assert "aún no está disponible" in r.json()["detail"]


def test_txt_responde_400(cliente, tmp_path):
    ruta = tmp_path / "notas.txt"
    ruta.write_text("hola")
    assert _subir(cliente, ruta).status_code == 400


def test_tif_sin_crs_responde_422(cliente, tmp_path):
    ruta = crear_geotiff(tmp_path / "sin_crs.tif", crs=None)
    assert _subir(cliente, ruta).status_code == 422


def test_tif_corrupto_responde_422(cliente, tmp_path):
    ruta = tmp_path / "malo.tif"
    ruta.write_bytes(b"no soy un tif")
    assert _subir(cliente, ruta).status_code == 422


def test_trabajo_inexistente(cliente):
    assert cliente.get("/trabajos/nada").status_code == 404
    assert cliente.get("/trabajos/nada/resultado").status_code == 404
