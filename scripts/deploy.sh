#!/usr/bin/env bash
# Deploy kode dari laptop ke VPS tanpa akses GitHub di VPS (repo private):
# kirim `git archive HEAD` lewat SSH, lalu rebuild container.
#   bash scripts/deploy.sh [ssh-alias]   (default: bot-vps)
set -euo pipefail
HOST="${1:-bot-vps}"
APP_DIR="/opt/sahamku"
cd "$(dirname "$0")/.."
echo "==> kirim $(git rev-parse --short HEAD) ke $HOST:$APP_DIR"
git archive --format=tar HEAD | ssh -o BatchMode=yes "$HOST" \
  "sudo mkdir -p $APP_DIR && sudo tar -x -C $APP_DIR -f - && sudo chown -R deploy:deploy $APP_DIR"
echo "==> rebuild & restart"
ssh -o BatchMode=yes "$HOST" \
  "cd $APP_DIR && sudo docker compose up -d --build --force-recreate"
ssh -o BatchMode=yes "$HOST" "sleep 8; sudo docker compose -f $APP_DIR/docker-compose.yml logs --since 30s 2>&1 | grep -E 'Run polling|Traceback|Error' | tail -3"
