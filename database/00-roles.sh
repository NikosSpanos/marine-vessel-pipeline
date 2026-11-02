#!/usr/bin/env bash
# Creates the application roles. Grants are in init.sql, once the tables exist.
# \getenv reads passwords inside psql, which keeps them out of the process list,
# and :'var' quotes them safely.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
\getenv writer_password VESSEL_WRITER_PASSWORD
\getenv reader_password VESSEL_READER_PASSWORD

CREATE ROLE vessel_writer LOGIN PASSWORD :'writer_password';
CREATE ROLE vessel_reader LOGIN PASSWORD :'reader_password';
SQL
