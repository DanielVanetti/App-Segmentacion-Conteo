import pytest

from app.servicios.teselado import inicios, nucleos, rejilla


def test_imagen_mas_pequena_que_la_tesela():
    assert inicios(500, 1024, 192) == [0]
    assert nucleos([0], 500, 1024) == [(0, 500)]


def test_ultima_tesela_pegada_al_borde():
    lista = inicios(2500, 1024, 192)
    assert lista[0] == 0
    assert lista[-1] + 1024 == 2500


@pytest.mark.parametrize("largo", [1024, 1025, 1800, 2500, 7777])
def test_nucleos_cubren_todo_sin_huecos_ni_solapes(largo):
    ns = nucleos(inicios(largo, 1024, 192), largo, 1024)
    assert ns[0][0] == 0
    assert ns[-1][1] == largo
    for (_, fin), (ini, _) in zip(ns, ns[1:]):
        assert fin == ini


def test_cada_punto_pertenece_a_una_sola_tesela():
    ventanas = rejilla(2500, 1800, 1024, 192)
    for x, y in [(0, 0), (928, 100), (927.9, 899.9), (2499, 1799), (1666, 900)]:
        assert sum(v.contiene(x, y) for v in ventanas) == 1
