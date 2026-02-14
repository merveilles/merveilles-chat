#!/bin/bash
# usage: ./scripts/init-certs.sh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "${PROJECT_ROOT}/env/proxy.env"

DOMAIN="${DOMAIN:?DOMAIN not set in proxy.env}"
CERT_EMAIL="${CERT_EMAIL:?CERT_EMAIL not set in proxy.env}"

echo "requesting certs for ${DOMAIN}, sso.${DOMAIN}, xmpp.${DOMAIN}..."

docker exec chat-certbot certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "${CERT_EMAIL}" \
    --agree-tos \
    --no-eff-email \
    -d "${DOMAIN}" \
    -d "sso.${DOMAIN}" \
    -d "xmpp.${DOMAIN}"

echo "certs issued, reloading nginx..."
docker exec chat-proxy nginx -s reload

echo "syncing certs..."
"${PROJECT_ROOT}/scripts/sync-certs.sh" "${DOMAIN}"

echo "done"
