#!/usr/bin/env bash
set -e

echo "==> Running Alembic Database Migrations..."
alembic upgrade head

echo "==> Starting Telegram Business Saver Bot..."
exec python -m app.bot
