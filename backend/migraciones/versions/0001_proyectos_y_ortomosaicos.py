"""Proyectos y ortomosaicos (RF-01 a RF-04)

Revision ID: 0001
Revises:
"""
import geoalchemy2
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    op.create_table(
        "proyecto",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("nombre", sa.Text, nullable=False),
        sa.Column("descripcion", sa.Text, nullable=False, server_default=""),
        sa.Column("sitio", sa.Text, nullable=False, server_default=""),
        sa.Column("fecha_vuelo", sa.Date, nullable=True),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("actualizado_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )
    op.create_table(
        "ortomosaico",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("proyecto_id", sa.String(36),
                  sa.ForeignKey("proyecto.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("nombre_archivo", sa.Text, nullable=False),
        sa.Column("ruta", sa.Text, nullable=False),
        sa.Column("tamano_bytes", sa.BigInteger, nullable=False),
        sa.Column("formato", sa.String(16), nullable=False),
        sa.Column("crs", sa.Text, nullable=True),
        sa.Column("epsg", sa.Integer, nullable=True),
        sa.Column("proyectado", sa.Boolean, nullable=False),
        sa.Column("gsd_m", sa.Double, nullable=True),
        sa.Column("ancho", sa.Integer, nullable=False),
        sa.Column("alto", sa.Integer, nullable=False),
        sa.Column("bandas", sa.Integer, nullable=False),
        sa.Column("tipo_dato", sa.String(16), nullable=False),
        sa.Column("huella", geoalchemy2.Geometry(geometry_type="POLYGON", srid=-1,
                                                 spatial_index=False), nullable=True),
        sa.Column("ext_crtm05_min_x", sa.Double), sa.Column("ext_crtm05_min_y", sa.Double),
        sa.Column("ext_crtm05_max_x", sa.Double), sa.Column("ext_crtm05_max_y", sa.Double),
        sa.Column("validacion", JSONB, nullable=False),
        sa.Column("subido_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("ortomosaico")
    op.drop_table("proyecto")
