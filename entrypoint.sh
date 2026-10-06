#!/bin/sh
set -e
echo "Waiting for PostgreSQL..."
python -m app.db.wait_for_db
echo "Running migrations / init..."
python -m app.db.init_db
python -m app.db.seed
echo "Starting API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
