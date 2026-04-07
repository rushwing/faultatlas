#!/usr/bin/env bash
# Wipe all local dev volumes and restart clean
set -euo pipefail

echo "Stopping containers..."
docker compose -f infra/compose/docker-compose.yml down -v

echo "Removing leftover volumes..."
docker volume prune -f

echo "Done. Run 'docker compose -f infra/compose/docker-compose.yml up --build' to restart."
