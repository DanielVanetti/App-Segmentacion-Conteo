"""
Tablas de PostgreSQL/PostGIS (modelo de datos del informe, Tabla 27).

Por ahora: proyecto, ortomosaico y ejecucion. Las siguientes (modelo, copa, correccion)
se agregan con nuevas migraciones de Alembic en `migraciones/versions/`.

Geometrías: la huella del ortomosaico se guarda en el sistema de referencia del archivo
(DD-04), con su SRID. La columna no fija un SRID porque cada ortomosaico puede traer el
suyo. La envolvente en CRTM05 se guarda aparte porque es la que usa el visor.
"""

from geoalchemy2 import Geometry
from sqlalchemy import (BigInteger, Boolean, Column, Date, DateTime, Double, ForeignKey, Integer,
                        Index, MetaData, String, Table, Text, func, text)
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

# Cola de procesamiento (DD-02): el procesador toma filas 'en_cola' con
# SELECT ... FOR UPDATE SKIP LOCKED. `latido` se renueva en cada mosaico; si deja de
# moverse, el procesador se cayó y la ejecución se marca como fallida.
ESTADOS_ACTIVOS = "estado IN ('en_cola', 'ejecutando')"

ejecucion = Table(
    "ejecucion", metadata,
    Column("id", String(36), primary_key=True),
    Column("proyecto_id", String(36), ForeignKey("proyecto.id", ondelete="CASCADE"),
           nullable=False),
    # Sin llave foránea: al reemplazar el ortomosaico cambia su id y el historial se conserva.
    Column("ortomosaico_id", String(36), nullable=False),
    Column("estado", String(16), nullable=False),
    Column("parametros", JSONB, nullable=False),
    Column("progreso", Double, nullable=False, server_default="0"),
    Column("etapa", Text, nullable=False, server_default=""),
    Column("mosaico_actual", Integer, nullable=False, server_default="0"),
    Column("mosaicos_totales", Integer, nullable=False, server_default="0"),
    Column("cancelacion_solicitada", Boolean, nullable=False, server_default="false"),
    Column("creado_en", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("iniciado_en", DateTime(timezone=True)),
    Column("finalizado_en", DateTime(timezone=True)),
    Column("latido", DateTime(timezone=True)),
    Column("copas_detectadas", Integer),
    Column("copas_guardadas", Integer),
    Column("area_total_m2", Double),
    Column("bitacora", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Index("ix_ejecucion_cola", "estado", "creado_en"),
    # Una sola ejecución activa por proyecto, garantizado por la base.
    Index("ux_ejecucion_activa", "proyecto_id", unique=True,
          postgresql_where=text(ESTADOS_ACTIVOS)),
)
