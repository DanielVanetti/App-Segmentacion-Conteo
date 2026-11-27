"""Ejecuciones ligadas a proyectos (RF-06 a RF-12), con el procesador integrado y en memoria."""

import threading
import time

import pytest
from fastapi.testclient import TestClient

from app.contenedor import construir
from app.main import crear_app
from tests.conftest import SegmentadorFalso, crear_geotiff

FINALES = {"completado", "fallido", "cancelado"}


class SegmentadorConPaso(SegmentadorFalso):
    """Espera a que la prueba abra el paso antes de segmentar cada mosaico."""

    def __init__(self):
        self.paso = threading.Event()
        self.paso.set()

    def segmentar(self, imagen_bgr):
        assert self.paso.wait(15), "la prueba no abrió el paso"
        return super().segmentar(imagen_bgr)


class SegmentadorRoto(SegmentadorFalso):
    def segmentar(self, imagen_bgr):
        raise RuntimeError("CUDA out of memory")


def _cliente(tmp_path, monkeypatch, segmentador):
    monkeypatch.setenv("DIR_TRABAJOS", str(tmp_path / "trabajos"))
    monkeypatch.setenv("DIR_DATOS", str(tmp_path / "datos"))
    monkeypatch.setenv("ESPERA_COLA_S", "0.05")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("PROCESADOR_INTEGRADO", raising=False)
    return TestClient(crear_app(lambda cfg: construir(cfg, segmentador=segmentador)))


@pytest.fixture
def seg():
    return SegmentadorConPaso()


@pytest.fixture
def cliente(tmp_path, monkeypatch, seg):
    with _cliente(tmp_path, monkeypatch, seg) as c:
        try:
            yield c
        finally:
            seg.paso.set()   # que el procesador no quede esperando al cerrar


def _proyecto(cliente, tmp_path, nombre="Parcela", con_orto=True):
    p = cliente.post("/api/proyectos", json={"nombre": nombre}).json()
    if con_orto:
        ruta = crear_geotiff(tmp_path / f"{nombre}.tif")
        with open(ruta, "rb") as f:
            r = cliente.post(f"/api/proyectos/{p['id']}/ortomosaico",
                             files={"archivo": (ruta.name, f)})
        assert r.status_code == 201, r.json()
    return p["id"]


def _lanzar(cliente, pid, **parametros):
    return cliente.post(f"/api/proyectos/{pid}/trabajos", json=parametros)


def _esperar(cliente, pid, tid, condicion=lambda t: t["estado"] in FINALES, segundos=20):
    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        t = cliente.get(f"/api/proyectos/{pid}/trabajos/{tid}").json()
        if condicion(t):
            return t
        time.sleep(0.05)
    raise AssertionError(f"no se cumplió la condición; último estado: {t}")


# --- flujo completo -----------------------------------------------------------------
def test_deteccion_completa(cliente, tmp_path):
    pid = _proyecto(cliente, tmp_path)
    r = _lanzar(cliente, pid, tamanoMosaicoPx=1024, traslapePct=20, confianzaMinima=0.5,
                areaMinimaM2=1.5)
    assert r.status_code == 202, r.json()
    t = r.json()
    assert t["estado"] == "en_cola" and t["proyectoId"] == pid and t["progreso"] == 0
    assert t["parametros"]["traslapePct"] == 20 and t["urlResultado"] is None

    t = _esperar(cliente, pid, t["id"])
    assert t["estado"] == "completado", t["bitacora"]
    assert t["progreso"] == 100 and t["etapa"] == "Terminado"
    assert t["copasDetectadas"] == 2 and t["copasGuardadas"] == 2
    assert t["areaTotalM2"] == pytest.approx(32, rel=0.05)      # 2 copas de 4 m × 4 m
    assert t["mosaicosTotales"] > 1 and t["mosaicoActual"] == t["mosaicosTotales"]
    assert t["iniciadoEn"] and t["finalizadoEn"]
    assert any("copas con confianza" in b["mensaje"] for b in t["bitacora"])

    geo = cliente.get(t["urlResultado"])
    assert geo.status_code == 200 and len(geo.json()["features"]) == 2

    proyecto = cliente.get(f"/api/proyectos/{pid}").json()
    assert proyecto["estado"] == "completado" and proyecto["totalCopas"] == 2
    assert [x["id"] for x in cliente.get(f"/api/proyectos/{pid}/trabajos").json()] == [t["id"]]


def test_umbral_de_confianza_cuenta_pero_no_borra(cliente, tmp_path):
    pid = _proyecto(cliente, tmp_path)
    t = _esperar(cliente, pid, _lanzar(cliente, pid, confianzaMinima=0.95).json()["id"])
    assert t["copasDetectadas"] == 0 and t["copasGuardadas"] == 2   # DD-05
    assert len(cliente.get(t["urlResultado"]).json()["features"]) == 2


def test_area_minima_descarta(cliente, tmp_path):
    pid = _proyecto(cliente, tmp_path)
    t = _esperar(cliente, pid, _lanzar(cliente, pid, areaMinimaM2=20).json()["id"])
    assert t["copasGuardadas"] == 0
    assert any("menores a 20 m²" in b["mensaje"] for b in t["bitacora"])


def test_otro_tamano_de_mosaico_avisa(cliente, tmp_path):
    pid = _proyecto(cliente, tmp_path)
    t = _lanzar(cliente, pid, tamanoMosaicoPx=512).json()
    assert any(b["nivel"] == "advertencia" and "1024 px" in b["mensaje"] for b in t["bitacora"])
    assert _esperar(cliente, pid, t["id"])["estado"] == "completado"


# --- validaciones ----------------------------------------------------------------------
def test_sin_ortomosaico_responde_409(cliente, tmp_path):
    pid = _proyecto(cliente, tmp_path, con_orto=False)
    r = _lanzar(cliente, pid)
    assert r.status_code == 409 and "imagen cargada" in r.json()["mensaje"]


def test_proyecto_inexistente(cliente):
    assert _lanzar(cliente, "nada").status_code == 404
    assert cliente.get("/api/proyectos/nada/trabajos").status_code == 404


@pytest.mark.parametrize("parametros, texto", [
    ({"tamanoMosaicoPx": 1000}, "múltiplo de 32"),
    ({"traslapePct": 80}, "traslape"),
    ({"confianzaMinima": 1.5}, "confianza"),
    ({"areaMinimaM2": -1}, "área"),
])
def test_parametros_invalidos(cliente, tmp_path, parametros, texto):
    pid = _proyecto(cliente, tmp_path)
    r = _lanzar(cliente, pid, **parametros)
    assert r.status_code == 422 and texto in r.json()["mensaje"]


def test_trabajo_de_otro_proyecto_es_404(cliente, tmp_path):
    a = _proyecto(cliente, tmp_path, "A")
    b = _proyecto(cliente, tmp_path, "B", con_orto=False)
    t = _lanzar(cliente, a).json()
    r = cliente.get(f"/api/proyectos/{b}/trabajos/{t['id']}")
    assert r.status_code == 404 and r.json()["mensaje"] == "El trabajo solicitado no existe."


def test_resultado_antes_de_terminar_es_409(cliente, tmp_path, seg):
    seg.paso.clear()
    pid = _proyecto(cliente, tmp_path)
    t = _lanzar(cliente, pid).json()
    assert cliente.get(f"/api/proyectos/{pid}/trabajos/{t['id']}/resultado").status_code == 409


# --- una sola activa y bloqueos ------------------------------------------------------------
def test_una_activa_por_proyecto_y_bloqueos(cliente, tmp_path, seg):
    seg.paso.clear()
    pid = _proyecto(cliente, tmp_path)
    t = _lanzar(cliente, pid).json()
    _esperar(cliente, pid, t["id"], lambda x: x["estado"] == "ejecutando")

    r = _lanzar(cliente, pid)
    assert r.status_code == 409 and "en curso" in r.json()["mensaje"]
    assert cliente.get(f"/api/proyectos/{pid}").json()["estado"] == "procesando"
    assert cliente.delete(f"/api/proyectos/{pid}").status_code == 409
    ruta = crear_geotiff(tmp_path / "otro.tif")
    with open(ruta, "rb") as f:
        r = cliente.post(f"/api/proyectos/{pid}/ortomosaico", files={"archivo": ("o.tif", f)})
    assert r.status_code == 409

    seg.paso.set()
    assert _esperar(cliente, pid, t["id"])["estado"] == "completado"
    assert _lanzar(cliente, pid).status_code == 202     # ya se puede lanzar otra


# --- cancelación (RF-12) -----------------------------------------------------------------
def test_cancelar_mientras_se_ejecuta(cliente, tmp_path, seg):
    seg.paso.clear()
    pid = _proyecto(cliente, tmp_path)
    t = _lanzar(cliente, pid).json()
    _esperar(cliente, pid, t["id"], lambda x: x["estado"] == "ejecutando")

    r = cliente.post(f"/api/proyectos/{pid}/trabajos/{t['id']}/cancelacion", json={})
    assert r.status_code == 200
    assert r.json()["cancelacionSolicitada"] is True and r.json()["etapa"] == "Cancelando"

    seg.paso.set()   # termina el mosaico en curso y se detiene
    t = _esperar(cliente, pid, t["id"])
    assert t["estado"] == "cancelado" and t["copasDetectadas"] is None
    assert t["mosaicoActual"] < t["mosaicosTotales"]
    assert cliente.get(f"/api/proyectos/{pid}/trabajos/{t['id']}/resultado").status_code == 409
    assert not list((tmp_path / "datos" / "proyectos" / pid / "ejecuciones").glob("*.geojson"))
    assert cliente.get(f"/api/proyectos/{pid}").json()["estado"] == "ortomosaico_cargado"


def test_cancelar_en_cola_es_inmediato(cliente, tmp_path, seg):
    seg.paso.clear()
    a = _proyecto(cliente, tmp_path, "A")
    b = _proyecto(cliente, tmp_path, "B")
    ta = _lanzar(cliente, a).json()
    _esperar(cliente, a, ta["id"], lambda x: x["estado"] == "ejecutando")
    tb = _lanzar(cliente, b).json()      # espera: el procesador está ocupado con A

    r = cliente.post(f"/api/proyectos/{b}/trabajos/{tb['id']}/cancelacion", json={}).json()
    assert r["estado"] == "cancelado" and r["finalizadoEn"]
    seg.paso.set()
    assert _esperar(cliente, a, ta["id"])["estado"] == "completado"


def test_cancelar_terminado_no_cambia(cliente, tmp_path):
    pid = _proyecto(cliente, tmp_path)
    t = _esperar(cliente, pid, _lanzar(cliente, pid).json()["id"])
    r = cliente.post(f"/api/proyectos/{pid}/trabajos/{t['id']}/cancelacion", json={}).json()
    assert r["estado"] == "completado"


# --- fallos ----------------------------------------------------------------------------
def test_fallo_del_modelo_queda_en_bitacora(tmp_path, monkeypatch):
    with _cliente(tmp_path, monkeypatch, SegmentadorRoto()) as cliente:
        pid = _proyecto(cliente, tmp_path)
        t = _esperar(cliente, pid, _lanzar(cliente, pid).json()["id"])
    assert t["estado"] == "fallido" and t["etapa"] == "Falló"
    error = [b for b in t["bitacora"] if b["nivel"] == "error"]
    assert error and "CUDA" not in error[0]["mensaje"]    # sin detalles técnicos (RNF-11)


def test_ejecucion_huerfana_se_marca_interrumpida():
    from app.adaptadores.repositorio_ejecuciones_memoria import RepositorioEjecucionesMemoria
    from app.dominio.modelos import Ejecucion, ParametrosEjecucion

    repo = RepositorioEjecucionesMemoria()
    repo.crear(Ejecucion(id="e1", proyecto_id="p", ortomosaico_id="o",
                         parametros=ParametrosEjecucion()))
    repo.tomar_siguiente()
    assert repo.recuperar_interrumpidas(60) == []      # tiene latido reciente
    assert repo.recuperar_interrumpidas(0) == ["e1"]
    e = repo.obtener("e1")
    assert e.estado.value == "fallido" and "interrumpió" in e.bitacora[-1].mensaje
