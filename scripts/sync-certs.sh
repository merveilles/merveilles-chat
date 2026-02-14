#!/bin/bash
# usage: ./scripts/sync-certs.sh <domain>

set -euo pipefail

DOMAIN="${1:?Usage: sync-certs.sh <domain>}"

CERTBOT_CERT_DIR="/etc/letsencrypt/live/${DOMAIN}"
DEST_DIR="/tls-certs"

echo "syncing certs for ${DOMAIN}..."

docker exec chat-proxy sh -c "
    if [ ! -d '${CERTBOT_CERT_DIR}' ]; then
        echo 'error: cert directory not found: ${CERTBOT_CERT_DIR}'
        echo 'run cert init first for ${DOMAIN}'
        exit 1
    fi

    cp '${CERTBOT_CERT_DIR}/fullchain.pem' '${DEST_DIR}/${DOMAIN}.crt'
    cp '${CERTBOT_CERT_DIR}/privkey.pem' '${DEST_DIR}/${DOMAIN}.key'

    chown 101:101 '${DEST_DIR}/${DOMAIN}.crt' '${DEST_DIR}/${DOMAIN}.key'
    chmod 640 '${DEST_DIR}/${DOMAIN}.crt' '${DEST_DIR}/${DOMAIN}.key'
"

echo "certs synced for ${DOMAIN}"
