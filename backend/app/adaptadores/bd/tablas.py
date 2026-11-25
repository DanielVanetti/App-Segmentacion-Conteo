"""
Tablas de PostgreSQL/PostGIS (modelo de datos del informe, Tabla 27).

Por ahora: proyecto y ortomosaico. Las siguientes (modelo, ejecucion, copa, correccion)
se agregan con nuevas migraciones de Alembic en `migraciones/versions/`.

Geometrías: la huella del ortomosaico se guarda en el sistema de referencia del archivo
(DD-04), con su SRID. La columna no fija un SRID porque cada ortomosaico puede traer el
suyo. La envolvente en CRTM05 se guarda aparte porque es la que usa el visor.
"""

from geoalchemy2 import Geometry
from sqlalchemy import (BigInteger, Boolean, Column, Date, DateTime, Double, ForeignKey, Integer,
                        MetaData, String, Table, Text, func)
from sqlalchemy.dialects.postgresql import JSONB

metadata = MetaData()

proyecto = Table(
    "proyecto", metadata,
    Column("id", String(36), primary_key=True),
    Column("nombre", Text, nullable=False),
    Column("descripcion", Text, nullable=False, server_default=""),
    Column("sitio", Text, nullable=False, server_default=""),
    Column("fecha_vuelo", Date, nullable=True),
    Column("creado_en", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("actualizado_en", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

ortomosaico = Table(
    "ortomosaico", metadata,
    Column("id", String(36), primary_key=True),
    Column("proyecto_id", String(36), ForeignKey("proyecto.id", ondelete="CASCADE"),
           nullable=False, unique=True),
    Column("nombre_archivo", Text, nullable=False),
    Column("ruta", Text, nullable=False),
    Column("tamano_bytes", BigInteger, nullable=False),
    Column("formato", String(16), nullable=False),
    Column("crs", Text, nullable=True),
    Column("epsg", Integer, nullable=True),
    Column("proyectado", Boolean, nullable=False),
    Column("gsd_m", Double, nullable=True),
    Column("ancho", Integer, nullable=False),
    Column("alto", Integer, nullable=False),
    Column("bandas", Integer, nullable=False),
    Column("tipo_dato", String(16), nullable=False),
    Column("huella", Geometry(geometry_type="POLYGON", srid=-1, spatial_index=False),
           nullable=True),
    Column("ext_crtm05_min_x", Double), Column("ext_crtm05_min_y", Double),
    Column("ext_crtm05_max_x", Double), Column("ext_crtm05_max_y", Double),
    Column("validacion", JSONB, nullable=False),
    Column("subido_en", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
