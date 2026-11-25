"""
Proyectos y ortomosaicos en PostgreSQL/PostGIS (RF-01: persisten tras reiniciar).
Misma interfaz que RepositorioProyectosMemoria (puerto RepositorioProyectos).
"""

from datetime import date, datetime

from geoalchemy2.shape import from_shape, to_shape
from shapely.geometry import box
from sqlalchemy import Engine, delete, func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.adaptadores.bd.tablas import ortomosaico as t_orto
from app.adaptadores.bd.tablas import proyecto as t_proy
from app.dominio.modelos import (Extension, MetadatosRaster, Ortomosaico, Proyecto,
                                 ResultadoValidacion, Validacion)


def _iso(valor: datetime | date | None) -> str | None:
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.isoformat(timespec="seconds")
    return valor.isoformat()


class RepositorioProyectosPostgis:
    def __init__(self, motor: Engine):
        self._motor = motor

    # --- proyectos -------------------------------------------------------------
    def _consulta_proyectos(self):
        return (select(t_proy, t_orto.c.id.label("ortomosaico_id"))
                .select_from(t_proy.outerjoin(t_orto, t_orto.c.proyecto_id == t_proy.c.id)))

    @staticmethod
    def _a_proyecto(fila) -> Proyecto:
        return Proyecto(id=fila.id, nombre=fila.nombre, descripcion=fila.descripcion,
                        sitio=fila.sitio, fecha_vuelo=_iso(fila.fecha_vuelo),
                        creado_en=_iso(fila.creado_en), actualizado_en=_iso(fila.actualizado_en),
                        ortomosaico_id=fila.ortomosaico_id)

    def crear(self, proyecto: Proyecto) -> None:
        with self._motor.begin() as cx:
            cx.execute(t_proy.insert().values(
                id=proyecto.id, nombre=proyecto.nombre, descripcion=proyecto.descripcion,
                sitio=proyecto.sitio,
                fecha_vuelo=date.fromisoformat(proyecto.fecha_vuelo) if proyecto.fecha_vuelo else None,
                creado_en=datetime.fromisoformat(proyecto.creado_en),
                actualizado_en=datetime.fromisoformat(proyecto.actualizado_en)))

    def listar(self) -> list[Proyecto]:
        with self._motor.connect() as cx:
            filas = cx.execute(self._consulta_proyectos().order_by(t_proy.c.creado_en.desc()))
            return [self._a_proyecto(f) for f in filas]

    def obtener(self, id_proyecto: str) -> Proyecto | None:
        with self._motor.connect() as cx:
            fila = cx.execute(self._consulta_proyectos()
                              .where(t_proy.c.id == id_proyecto)).first()
            return self._a_proyecto(fila) if fila else None

    def eliminar(self, id_proyecto: str) -> bool:
        with self._motor.begin() as cx:
            # El ortomosaico se borra en cascada (ON DELETE CASCADE).
            return cx.execute(delete(t_proy).where(t_proy.c.id == id_proyecto)).rowcount > 0

    # --- ortomosaico -----------------------------------------------------------
    def guardar_ortomosaico(self, o: Ortomosaico) -> None:
        m, v = o.metadatos, o.validacion
        huella = None
        if m.extension_nativa:
            e = m.extension_nativa
            huella = from_shape(box(e.min_x, e.min_y, e.max_x, e.max_y), srid=m.epsg or 0)
        crt = m.extension_crtm05
        valores = dict(
            id=o.id, proyecto_id=o.proyecto_id, nombre_archivo=o.nombre_archivo, ruta=o.ruta,
            tamano_bytes=o.tamano_bytes, formato=o.formato, crs=m.crs, epsg=m.epsg,
            proyectado=m.proyectado, gsd_m=m.gsd_m, ancho=m.ancho, alto=m.alto,
            bandas=m.bandas, tipo_dato=m.tipo_dato, huella=huella,
            ext_crtm05_min_x=crt.min_x if crt else None, ext_crtm05_min_y=crt.min_y if crt else None,
            ext_crtm05_max_x=crt.max_x if crt else None, ext_crtm05_max_y=crt.max_y if crt else None,
            validacion={"formato": v.formato.value, "crs": v.crs.value,
                        "resolucion": v.resolucion.value, "mensajes": list(v.mensajes)},
            subido_en=datetime.fromisoformat(o.subido_en),
        )
        with self._motor.begin() as cx:
            # Un ortomosaico por proyecto: si ya hay uno, se reemplaza.
            sentencia = insert(t_orto).values(**valores)
            cx.execute(sentencia.on_conflict_do_update(
                index_elements=[t_orto.c.proyecto_id],
                set_={k: sentencia.excluded[k] for k in valores if k != "proyecto_id"}))
            cx.execute(update(t_proy).where(t_proy.c.id == o.proyecto_id)
                       .values(actualizado_en=func.now()))

    def obtener_ortomosaico(self, id_proyecto: str) -> Ortomosaico | None:
        with self._motor.connect() as cx:
            f = cx.execute(select(t_orto).where(t_orto.c.proyecto_id == id_proyecto)).first()
        if f is None:
            return None
        nativa = None
        if f.huella is not None:
            nativa = Extension(*to_shape(f.huella).bounds)
        crtm05 = (Extension(f.ext_crtm05_min_x, f.ext_crtm05_min_y,
                            f.ext_crtm05_max_x, f.ext_crtm05_max_y)
                  if f.ext_crtm05_min_x is not None else None)
        meta = MetadatosRaster(ancho=f.ancho, alto=f.alto, bandas=f.bandas, tipo_dato=f.tipo_dato,
                               crs=f.crs, epsg=f.epsg, proyectado=f.proyectado, gsd_m=f.gsd_m,
                               extension_nativa=nativa, extension_crtm05=crtm05)
        val = f.validacion
        validacion = Validacion(formato=ResultadoValidacion(val["formato"]),
                                crs=ResultadoValidacion(val["crs"]),
                                resolucion=ResultadoValidacion(val["resolucion"]),
                                mensajes=tuple(val.get("mensajes", ())))
        return Ortomosaico(id=f.id, proyecto_id=f.proyecto_id, nombre_archivo=f.nombre_archivo,
                           ruta=f.ruta, tamano_bytes=f.tamano_bytes, metadatos=meta,
                           validacion=validacion, formato=f.formato, subido_en=_iso(f.subido_en))
