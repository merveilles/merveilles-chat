#!/bin/bash
# quick env sanity checks before deploy

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_DIR="${PROJECT_ROOT}/env"

ERRORS=0
WARNINGS=0

err() { echo "error: $1"; ((ERRORS++)); }
warn() { echo "warn: $1"; ((WARNINGS++)); }
ok() { echo "ok: $1"; }

read_val() {
    local file="$1" key="$2"
    grep -E "^${key}=" "$file" 2>/dev/null | head -1 | cut -d= -f2-
}

echo "checking env files..."
REQUIRED=("stack.env" "db.env" "idp.env" "xmpp.env" "proxy.env")
for file in "${REQUIRED[@]}"; do
    if [ ! -f "${ENV_DIR}/${file}" ]; then
        err "${file} missing. Run: python3 scripts/setup.py"
    else
        ok "${file} exists"
    fi
done

if [ "$ERRORS" -gt 0 ]; then
    echo ""
    echo "stopping: missing env files"
    exit 1
fi

echo ""
echo "checking placeholders..."
for file in "${REQUIRED[@]}"; do
    matches=$(grep -c 'REPLACE_ME' "${ENV_DIR}/${file}" 2>/dev/null || true)
    if [ "$matches" -gt 0 ]; then
        err "${file} has ${matches} REPLACE_ME placeholder(s). Run: bash scripts/secure.sh"
    else
        ok "${file} has no placeholders"
    fi
done

echo ""
echo "checking domain values..."
STACK_DOMAIN=$(read_val "${ENV_DIR}/stack.env" "DOMAIN")
XMPP_DOMAIN=$(read_val "${ENV_DIR}/xmpp.env" "DOMAIN")
PROXY_DOMAIN=$(read_val "${ENV_DIR}/proxy.env" "DOMAIN")
IDP_HOSTNAME=$(read_val "${ENV_DIR}/idp.env" "KC_HOSTNAME")

if [ -z "$STACK_DOMAIN" ]; then
    err "DOMAIN not set in stack.env"
else
    ok "DOMAIN=${STACK_DOMAIN}"

    if [ "$XMPP_DOMAIN" != "$STACK_DOMAIN" ]; then
        err "xmpp.env DOMAIN='${XMPP_DOMAIN}' does not match stack.env DOMAIN='${STACK_DOMAIN}'"
    else
        ok "xmpp.env DOMAIN matches"
    fi

    if [ "$PROXY_DOMAIN" != "$STACK_DOMAIN" ]; then
        err "proxy.env DOMAIN='${PROXY_DOMAIN}' does not match stack.env DOMAIN='${STACK_DOMAIN}'"
    else
        ok "proxy.env DOMAIN matches"
    fi

    EXPECTED_KC_HOST="sso.${STACK_DOMAIN}"
    if [ "$IDP_HOSTNAME" != "$EXPECTED_KC_HOST" ]; then
        err "idp.env KC_HOSTNAME='${IDP_HOSTNAME}' expected 'sso.${STACK_DOMAIN}'"
    else
        ok "idp.env KC_HOSTNAME matches stack domain"
    fi
fi

echo ""
echo "checking realm values..."
STACK_REALM=$(read_val "${ENV_DIR}/stack.env" "KC_REALM")
XMPP_REALM=$(read_val "${ENV_DIR}/xmpp.env" "KC_REALM")

if [ -z "$STACK_REALM" ]; then
    err "KC_REALM not set in stack.env"
else
    ok "KC_REALM=${STACK_REALM}"

    if [ "$XMPP_REALM" != "$STACK_REALM" ]; then
        err "xmpp.env KC_REALM='${XMPP_REALM}' does not match stack.env KC_REALM='${STACK_REALM}'"
    else
        ok "xmpp.env KC_REALM matches"
    fi
fi

echo ""
echo "checking DB credential sync..."

DB_KC_PASS=$(read_val "${ENV_DIR}/db.env" "KC_DB_PASSWORD")
IDP_KC_PASS=$(read_val "${ENV_DIR}/idp.env" "KC_DB_PASSWORD")

if [ -n "$DB_KC_PASS" ] && [ "$DB_KC_PASS" != "REPLACE_ME" ]; then
    if [ "$DB_KC_PASS" != "$IDP_KC_PASS" ]; then
        err "KC_DB_PASSWORD mismatch between db.env and idp.env"
    else
        ok "KC_DB_PASSWORD matches (db.env/idp.env)"
    fi
fi

DB_PROSODY_PASS=$(read_val "${ENV_DIR}/db.env" "PROSODY_DB_PASSWORD")
XMPP_DB_PASS=$(read_val "${ENV_DIR}/xmpp.env" "DB_PASSWORD")

if [ -n "$DB_PROSODY_PASS" ] && [ "$DB_PROSODY_PASS" != "REPLACE_ME" ]; then
    if [ "$DB_PROSODY_PASS" != "$XMPP_DB_PASS" ]; then
        err "PROSODY_DB_PASSWORD (db.env) != DB_PASSWORD (xmpp.env)"
    else
        ok "Prosody DB password matches (db.env/xmpp.env)"
    fi
fi

echo ""
echo "checking prod-only values..."

if [ "$STACK_DOMAIN" != "localhost" ]; then
    CERT_EMAIL=$(read_val "${ENV_DIR}/proxy.env" "CERT_EMAIL")
    if [ -z "$CERT_EMAIL" ] || [ "$CERT_EMAIL" = "admin@example.com" ]; then
        err "CERT_EMAIL in proxy.env is not configured for production"
    else
        ok "CERT_EMAIL=${CERT_EMAIL}"
    fi
else
    echo "localhost mode, skipping prod-only checks"
fi

echo ""
echo "checking required tools..."
for tool in docker openssl python3; do
    if command -v "$tool" >/dev/null 2>&1; then
        ok "${tool} found"
    else
        err "${tool} not found"
    fi
done

if command -v hg >/dev/null 2>&1; then
    ok "hg (mercurial) found"
else
    warn "hg (mercurial) not found, community modules won't sync"
fi

echo ""
echo "summary:"
echo "  errors:   ${ERRORS}"
echo "  warnings: ${WARNINGS}"

if [ "$ERRORS" -gt 0 ]; then
    echo ""
    echo "validation failed"
    exit 1
fi

if [ "$WARNINGS" -gt 0 ]; then
    echo ""
    echo "validation passed (with warnings)"
    exit 0
fi

echo ""
echo "validation passed"
exit 0
