#!/bin/bash
# usage: ./scripts/init-certs.sh

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
source "${PROJECT_ROOT}/env/proxy.env"

DOMAIN="${DOMAIN:?DOMAIN not set in proxy.env}"
CERT_EMAIL="${CERT_EMAIL:?CERT_EMAIL not set in proxy.env}"
SSO_SUBDOMAIN="${SSO_SUBDOMAIN:-sso}"
CHAT_SUBDOMAIN="${CHAT_SUBDOMAIN:-xmpp}"
SSO_HOST="${SSO_SUBDOMAIN}.${DOMAIN}"
CHAT_HOST="${CHAT_SUBDOMAIN}.${DOMAIN}"

echo "requesting certs for ${DOMAIN}, ${SSO_HOST}, ${CHAT_HOST}..."

docker exec chat-certbot certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email "${CERT_EMAIL}" \
    --agree-tos \
    --no-eff-email \
    -d "${DOMAIN}" \
    -d "${SSO_HOST}" \
    -d "${CHAT_HOST}"

echo "certs issued, reloading nginx..."
docker exec chat-proxy nginx -s reload

echo "syncing certs..."
"${PROJECT_ROOT}/scripts/sync-certs.sh" "${DOMAIN}"

echo "switching nginx to full TLS config..."
"${PROJECT_ROOT}/scripts/compose-up.sh" switch-nginx prod

echo "done"
