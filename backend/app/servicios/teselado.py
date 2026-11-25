"""
Cálculo de la rejilla de teselas con traslape (lógica pura, sin leer imágenes).

Para evitar copas duplicadas en el traslape, cada tesela tiene un "núcleo":
la tesela menos la mitad del traslape en los lados que tocan otra tesela.
Una copa pertenece solo a la tesela cuyo núcleo contiene su centroide.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Ventana:
    x0: int
    y0: int
    ancho: int
    alto: int
    # núcleo en coordenadas de píxel de la imagen completa: [desde, hasta)
    nx0: float
    nx1: float
    ny0: float
    ny1: float

    def contiene(self, x: float, y: float) -> bool:
        return self.nx0 <= x < self.nx1 and self.ny0 <= y < self.ny1


def inicios(largo: int, tam: int, traslape: int) -> list[int]:
    """Posiciones de inicio a lo largo de un eje. La última se pega al borde."""
    if largo <= tam:
        return [0]
    paso = tam - traslape
    lista = list(range(0, largo - tam + 1, paso))
    if lista[-1] + tam < largo:
        lista.append(largo - tam)
    return lista


def nucleos(lista_inicios: list[int], largo: int, tam: int) -> list[tuple[float, float]]:
    """Intervalo [desde, hasta) de cada tesela. El corte entre vecinas es la mitad
    de su traslape real (funciona también con la última, que puede traslapar más)."""
    fines = [min(i + tam, largo) for i in lista_inicios]
    ultimo = len(lista_inicios) - 1
    resultado = []
    for k, (ini, fin) in enumerate(zip(lista_inicios, fines)):
        desde = 0 if k == 0 else (ini + fines[k - 1]) / 2
        hasta = largo if k == ultimo else (fin + lista_inicios[k + 1]) / 2
        resultado.append((desde, hasta))
    return resultado


def rejilla(ancho: int, alto: int, tam: int, traslape: int) -> list[Ventana]:
    xs, ys = inicios(ancho, tam, traslape), inicios(alto, tam, traslape)
    nxs, nys = nucleos(xs, ancho, tam), nucleos(ys, alto, tam)
    return [
        Ventana(x0, y0, min(tam, ancho - x0), min(tam, alto - y0), nx0, nx1, ny0, ny1)
        for y0, (ny0, ny1) in zip(ys, nys)
        for x0, (nx0, nx1) in zip(xs, nxs)
    ]
