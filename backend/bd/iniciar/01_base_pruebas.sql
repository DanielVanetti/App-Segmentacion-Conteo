-- Se ejecuta solo la primera vez que se crea el volumen de la base.
-- Base aparte para las pruebas automáticas (tests/test_repositorio_postgis.py la vacía).
CREATE DATABASE copas_pruebas OWNER copas;
\connect copas_pruebas
CREATE EXTENSION IF NOT EXISTS postgis;
\connect copas
CREATE EXTENSION IF NOT EXISTS postgis;
