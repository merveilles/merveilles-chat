#!/bin/bash
# Orchestration script.
# Creates external networks/volumes, then starts each service group in dependency order.
#
# Usage:
#   ./scripts/compose-up.sh up [dev|prod]    Start all services (default: dev)
#   ./scripts/compose-up.sh down             Stop all services
#   ./scripts/compose-up.sh restart <svc>    Restart a single service
#   ./scripts/compose-up.sh status           Show status of all services
#
# The environment argument controls which nginx config template is used:
#   dev  — self-signed TLS, no certbot needed
#   prod — Let's Encrypt via certbot

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_DIR="${PROJECT_ROOT}/compose"
ENV_DIR="${PROJECT_ROOT}/env"
ENV_FILE="${ENV_DIR}/stack.env"
REQUIRED_ENV_FILES=("stack.env" "db.env" "idp.env" "xmpp.env" "proxy.env")

# All service groups in dependency order
SERVICES=(db idp xmpp proxy)

# State file to remember which environment is active
STATE_FILE="${PROJECT_ROOT}/.compose-env"

compose() {
    local service="$1"
    shift
    COMPOSE_IGNORE_ORPHANS=1 docker compose \
        --project-directory "${PROJECT_ROOT}" \
        --env-file "${ENV_FILE}" \
        -f "${COMPOSE_DIR}/${service}/docker-compose.yml" \
        "$@"
}

ensure_env() {
    for file in "${REQUIRED_ENV_FILES[@]}"; do
        if [ ! -f "${ENV_DIR}/${file}" ]; then
            echo "Missing ${ENV_DIR}/${file}. Run: python3 scripts/setup.py"
            exit 1
        fi
    done
}

create_networks() {
    for net in db-mesh proxy-mesh; do
        if ! docker network inspect "$net" >/dev/null 2>&1; then
            echo "Creating network: ${net}"
            docker network create "$net"
        fi
    done
}

create_volumes() {
    if ! docker volume inspect tls-certs >/dev/null 2>&1; then
        echo "Creating volume: tls-certs"
        docker volume create tls-certs
    fi
}

select_nginx_config() {
    local env="${1:-dev}"
    local proxy_dir="${COMPOSE_DIR}/proxy"

    case "$env" in
        dev)
            echo "Environment: dev (self-signed TLS)"
            # Generate self-signed cert if missing
            local cert_dir="${proxy_dir}/dev-certs"
            mkdir -p "$cert_dir"
            if [ ! -f "${cert_dir}/selfsigned.crt" ]; then
                echo "Generating self-signed certificate for dev..."
                openssl req -x509 -nodes -days 365 \
                    -newkey rsa:2048 \
                    -keyout "${cert_dir}/selfsigned.key" \
                    -out "${cert_dir}/selfsigned.crt" \
                    -subj "/CN=localhost" \
                    -addext "subjectAltName=DNS:localhost,DNS:sso.localhost,DNS:xmpp.localhost" \
                    2>/dev/null
            fi
            # Swap nginx template to dev version
            ln -sf nginx-dev.conf.template "${proxy_dir}/active.conf.template"
            ;;
        prod)
            echo "Environment: prod (Let's Encrypt)"
            ln -sf nginx.conf.template "${proxy_dir}/active.conf.template"
            ;;
        *)
            echo "Unknown environment: ${env}. Use 'dev' or 'prod'."
            exit 1
            ;;
    esac

    # Remember the environment
    echo "$env" > "$STATE_FILE"
}

cmd_up() {
    local env="${1:-dev}"
    ensure_env
    create_networks
    create_volumes
    select_nginx_config "$env"

    for svc in "${SERVICES[@]}"; do
        echo "Starting: ${svc}"
        compose "$svc" up -d
    done
    echo ""
    echo "All services started (${env}). Check status with: $0 status"

    if [ "$env" = "prod" ]; then
        echo ""
        echo "Next: Run ./scripts/init-certs.sh to obtain Let's Encrypt certificates."
        echo "Then:  ./scripts/sync-certs.sh <domain> to sync certs to Prosody."
    fi
}

cmd_down() {
    ensure_env
    # Stop in reverse order
    for (( i=${#SERVICES[@]}-1; i>=0; i-- )); do
        local svc="${SERVICES[$i]}"
        echo "Stopping: ${svc}"
        compose "$svc" down
    done
}

cmd_restart() {
    ensure_env
    local target="${1:-}"
    if [ -z "$target" ]; then
        echo "Usage: $0 restart <service>"
        echo "Services: ${SERVICES[*]}"
        exit 1
    fi

    if [ ! -d "${COMPOSE_DIR}/${target}" ]; then
        echo "Unknown service: ${target}"
        echo "Available: ${SERVICES[*]}"
        exit 1
    fi

    echo "Restarting: ${target}"
    compose "$target" down
    compose "$target" up -d
}

cmd_status() {
    ensure_env
    local env="unknown"
    [ -f "$STATE_FILE" ] && env="$(cat "$STATE_FILE")"
    echo "Environment: ${env}"
    echo ""
    for svc in "${SERVICES[@]}"; do
        echo "=== ${svc} ==="
        compose "$svc" ps
        echo ""
    done
}

case "${1:-up}" in
    up)      cmd_up "${2:-dev}" ;;
    down)    cmd_down ;;
    restart) cmd_restart "${2:-}" ;;
    status)  cmd_status ;;
    *)
        echo "Usage: $0 [up [dev|prod]|down|restart <service>|status]"
        exit 1
        ;;
esac
