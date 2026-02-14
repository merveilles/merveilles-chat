#!/bin/bash
# usage: ./scripts/renew-certs.sh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "${PROJECT_ROOT}/env/proxy.env"

DOMAIN="${DOMAIN:?DOMAIN not set in proxy.env}"

echo "[$(date)] renewing certs..."

docker exec chat-certbot certbot renew --quiet

echo "reloading nginx..."
docker exec chat-proxy nginx -s reload

echo "syncing certs..."
"${PROJECT_ROOT}/scripts/sync-certs.sh" "${DOMAIN}"

echo "[$(date)] cert renew done"
