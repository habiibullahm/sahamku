#!/bin/sh
set -e
mkdir -p /data/charts
if [ ! -f "$DB_PATH" ]; then
  echo "[entrypoint] DB belum ada -> backfill 3 tahun (sekali saja)..."
  python scripts/backfill.py
fi
exec python -m sahamku.bot.main
