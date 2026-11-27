"""Ejecuciones de detección: cola en PostgreSQL (RF-06 a RF-12; DD-01, DD-02)

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ejecucion",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("proyecto_id", sa.String(36),
                  sa.ForeignKey("proyecto.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ortomosaico_id", sa.String(36), nullable=False),
        sa.Column("estado", sa.String(16), nullable=False),
        sa.Column("parametros", JSONB, nullable=False),
        sa.Column("progreso", sa.Double, nullable=False, server_default="0"),
        sa.Column("etapa", sa.Text, nullable=False, server_default=""),
        sa.Column("mosaico_actual", sa.Integer, nullable=False, server_default="0"),
        sa.Column("mosaicos_totales", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cancelacion_solicitada", sa.Boolean, nullable=False,
                  server_default=sa.false()),
        sa.Column("creado_en", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("iniciado_en", sa.DateTime(timezone=True)),
        sa.Column("finalizado_en", sa.DateTime(timezone=True)),
        sa.Column("latido", sa.DateTime(timezone=True)),
        sa.Column("copas_detectadas", sa.Integer),
        sa.Column("copas_guardadas", sa.Integer),
        sa.Column("area_total_m2", sa.Double),
        sa.Column("bitacora", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.create_index("ix_ejecucion_cola", "ejecucion", ["estado", "creado_en"])
    op.create_index("ux_ejecucion_activa", "ejecucion", ["proyecto_id"], unique=True,
                    postgresql_where=sa.text("estado IN ('en_cola', 'ejecutando')"))


def downgrade() -> None:
    op.drop_table("ejecucion")
