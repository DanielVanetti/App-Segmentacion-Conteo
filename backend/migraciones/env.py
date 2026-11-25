"""Configuración de Alembic. Lee DATABASE_URL del entorno o de backend/.env."""

import os
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import create_engine

from app.adaptadores.bd.tablas import metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

url = config.attributes.get("url") or os.getenv("DATABASE_URL")
if not url:
    raise SystemExit("Falta DATABASE_URL (ver backend/.env.example).")


def ejecutar() -> None:
    motor = create_engine(url)
    with motor.connect() as cx:
        context.configure(connection=cx, target_metadata=metadata)
        with context.begin_transaction():
            context.run_migrations()
    motor.dispose()


ejecutar()
