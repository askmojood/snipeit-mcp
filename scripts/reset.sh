#!/usr/bin/env bash
# Start over: delete the local Snipe-IT and its data, set it up again, and fill it with the SAMPLE company.
set -euo pipefail
cd "$(dirname "$0")/.."
docker compose -f docker/compose.yml --env-file docker/.env down -v
rm -f .env docker/.env
./scripts/up.sh
set -a; . ./.env; set +a
uv run snipeit-seed
