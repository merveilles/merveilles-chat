#!/bin/bash
# sync-certs.sh
#
# Copies TLS certificates from Caddy's ACME storage into the shared
# tls-certs volume so Prosody can use them for direct XMPP connections
# (ports 5222/5269 which bypass the reverse proxy).
#
# Usage: ./scripts/sync-certs.sh <domain>

set -euo pipefail

DOMAIN="${1:?Usage: sync-certs.sh <domain>}"

CADDY_CERT_DIR="/data/caddy/certificates/acme-v02.api.letsencrypt.org-directory/${DOMAIN}"
DEST_DIR="/tls-certs"

if [ ! -d "$CADDY_CERT_DIR" ]; then
    echo "Error: Certificate directory not found: ${CADDY_CERT_DIR}"
    echo "Has Caddy obtained certificates for ${DOMAIN} yet?"
    exit 1
fi

cp "${CADDY_CERT_DIR}/${DOMAIN}.crt" "${DEST_DIR}/${DOMAIN}.crt"
cp "${CADDY_CERT_DIR}/${DOMAIN}.key" "${DEST_DIR}/${DOMAIN}.key"

# Prosody reads certs as the prosody user (uid 101 in the official image)
chown 101:101 "${DEST_DIR}/${DOMAIN}.crt" "${DEST_DIR}/${DOMAIN}.key"
chmod 640 "${DEST_DIR}/${DOMAIN}.crt" "${DEST_DIR}/${DOMAIN}.key"

echo "Certificates synced for ${DOMAIN}"
