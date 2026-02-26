#!/bin/bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPTS="${PROJECT_ROOT}/scripts"

ENV_MODE="${1:-}"
DOMAIN_ARG=""
SKIP_MODULES=false

if [ -z "$ENV_MODE" ]; then
    echo "Usage: $0 <dev|prod> [domain] [--skip-modules]"
    echo ""
    echo "  dev                  local setup on localhost"
    echo "  prod example.com     production domain"
    echo "  --skip-modules       Skip Prosody community module sync"
    exit 1
fi

shift
while [ $# -gt 0 ]; do
    case "$1" in
        --skip-modules) SKIP_MODULES=true ;;
        *)
            if [ -z "$DOMAIN_ARG" ]; then
                DOMAIN_ARG="$1"
            else
                echo "unknown argument: $1"
                exit 1
            fi
            ;;
    esac
    shift
done

case "$ENV_MODE" in
    dev)
        DOMAIN="${DOMAIN_ARG:-localhost}"
        ;;
    prod)
        if [ -z "$DOMAIN_ARG" ]; then
            echo "prod needs a domain: $0 prod example.com"
            exit 1
        fi
        DOMAIN="$DOMAIN_ARG"
        ;;
    *)
        echo "unknown mode: ${ENV_MODE}. use 'dev' or 'prod'."
        exit 1
        ;;
esac

HEALTH_TIMEOUT=120   # how long to wait for all containers to be healthy (seconds)
HEALTH_INTERVAL=5    # seconds between health polls
KC_RETRIES=12        # retries for keycloak bootstrap (seconds)
KC_RETRY_DELAY=10    # seconds between said retries

read_proxy_val() {
    local key="$1"
    grep -E "^${key}=" "${PROJECT_ROOT}/env/proxy.env" 2>/dev/null | head -1 | cut -d= -f2-
}

echo "setup..."

SETUP_ARGS=(python3 "${SCRIPTS}/setup.py" --domain "$DOMAIN")
if $SKIP_MODULES; then
    echo "skip-modules is on"
    SETUP_ARGS+=(--skip-modules)
fi

"${SETUP_ARGS[@]}"
echo "setup done (domain=${DOMAIN})"

SSO_SUBDOMAIN="$(read_proxy_val "SSO_SUBDOMAIN")"
CHAT_SUBDOMAIN="$(read_proxy_val "CHAT_SUBDOMAIN")"
SSO_SUBDOMAIN="${SSO_SUBDOMAIN:-sso}"
CHAT_SUBDOMAIN="${CHAT_SUBDOMAIN:-xmpp}"
SSO_HOST="${SSO_SUBDOMAIN}.${DOMAIN}"
CHAT_HOST="${CHAT_SUBDOMAIN}.${DOMAIN}"

echo "validating env/config..."

if ! bash "${SCRIPTS}/validate.sh"; then
    echo "validation failed" >&2
    exit 1
fi
echo "config check passed"

echo "starting containers..."

START_MODE="$ENV_MODE"
if [ "$ENV_MODE" = "prod" ]; then
    START_MODE="prod-bootstrap"
fi

bash "${SCRIPTS}/compose-up.sh" up "$START_MODE"
echo "containers started"

echo "waiting for health checks..."

CONTAINERS=("chat-db" "chat-idp" "chat-server" "chat-proxy")
DEADLINE=$((SECONDS + HEALTH_TIMEOUT))

all_healthy() {
    for container in "${CONTAINERS[@]}"; do
        status=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "missing")
        if [ "$status" != "healthy" ]; then
            return 1
        fi
    done
    return 0
}

while ! all_healthy; do
    if [ $SECONDS -ge $DEADLINE ]; then
        echo "health checks timed out after ${HEALTH_TIMEOUT}s" >&2
        echo ""
        echo "status snapshot:"
        for container in "${CONTAINERS[@]}"; do
            status=$(docker inspect --format='{{.State.Health.Status}}' "$container" 2>/dev/null || echo "not found")
            echo "  ${container}: ${status}"
        done
        echo ""
        echo "check logs with: docker logs <container-name>"
        exit 1
    fi
    ELAPSED=$((SECONDS))
    echo "still waiting (${ELAPSED}s/${HEALTH_TIMEOUT}s)"
    sleep "$HEALTH_INTERVAL"
done

echo "all core containers healthy"

echo "bootstrapping keycloak..."
ATTEMPT=0
while true; do
    ((ATTEMPT++))
    if python3 "${SCRIPTS}/bootstrap-keycloak.py" 2>&1; then
        echo "keycloak bootstrap done"
        break
    fi

    if [ "$ATTEMPT" -ge "$KC_RETRIES" ]; then
        echo "keycloak bootstrap failed after ${KC_RETRIES} tries" >&2
        echo "run manually: python3 scripts/bootstrap-keycloak.py"
        exit 1
    fi

    echo "idp still warming up, retry in ${KC_RETRY_DELAY}s (${ATTEMPT}/${KC_RETRIES})"
    sleep "$KC_RETRY_DELAY"
done

if [ "$ENV_MODE" = "prod" ]; then
    echo "checking TLS certs..."
    TLS_READY=false
    NGINX_TLS_APPLIED=false

    CERT_EXISTS=$(docker exec chat-proxy sh -c "test -f /etc/letsencrypt/live/${DOMAIN}/fullchain.pem && echo yes || echo no" 2>/dev/null || echo "no")

    if [ "$CERT_EXISTS" = "yes" ]; then
        echo "certs already exist for ${DOMAIN}"
        bash "${SCRIPTS}/sync-certs.sh" "$DOMAIN"
        echo "synced certs to prosody"
        TLS_READY=true
    else
        echo "requesting Let's Encrypt certs for ${DOMAIN}..."
        if bash "${SCRIPTS}/init-certs.sh"; then
            echo "certs obtained and synced"
            TLS_READY=true
            NGINX_TLS_APPLIED=true
        else
            echo "cert request failed" >&2
            echo ""
            echo "usually this means:"
            echo "  - DNS for ${DOMAIN} / ${SSO_HOST} / ${CHAT_HOST} doesn't resolve to this host"
            echo "  - Ports 80/443 are not reachable from the internet"
            echo ""
            echo "stack remains in HTTP bootstrap mode. fix DNS/ports then run:"
            echo "  ./scripts/init-certs.sh"
            echo "  ./scripts/compose-up.sh switch-nginx prod"
        fi
    fi

    if $TLS_READY && ! $NGINX_TLS_APPLIED; then
        echo "switching nginx to full TLS config..."
        bash "${SCRIPTS}/compose-up.sh" switch-nginx prod
        echo "nginx now running with Let's Encrypt certs"
    fi
fi

echo ""
echo "deploy finished (${ENV_MODE})"

echo ""
if [ "$ENV_MODE" = "dev" ]; then
    echo "dev stack is up. quick checks:"
    echo ""
    echo "  ./scripts/compose-up.sh status"
    echo "  curl -k https://${SSO_HOST}/realms/community/.well-known/openid-configuration"
    echo ""
    echo "make a test user:"
    echo ""
    echo "  python3 scripts/bootstrap-keycloak.py --user testuser --password changeme"
    echo ""
else
    if [ "${TLS_READY:-false}" = "true" ]; then
        echo "prod stack is up at ${DOMAIN}. quick checks:"
        echo ""
        echo "  ./scripts/compose-up.sh status"
        echo "  curl https://${SSO_HOST}/realms/community/.well-known/openid-configuration"
        echo ""
        echo "set cert renewal cron:"
        echo ""
        echo "  crontab -e"
        echo "  0 3 * * * ${SCRIPTS}/renew-certs.sh >> /var/log/cert-renew.log 2>&1"
        echo ""
    else
        echo "prod stack is up in HTTP bootstrap mode for ${DOMAIN}."
        echo ""
        echo "finish TLS after DNS/ports are fixed:"
        echo "  ./scripts/init-certs.sh"
        echo "  ./scripts/compose-up.sh switch-nginx prod"
        echo ""
    fi
fi
