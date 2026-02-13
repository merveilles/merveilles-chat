#!/bin/bash
# orchestration script.
# Creates external networks, then starts each service group in dependency order.
#
# Usage: ./scripts/compose-up.sh [up|down|restart|status]

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPOSE_DIR="${PROJECT_ROOT}/compose"
ENV_FILE="${PROJECT_ROOT}/.env"

# All service groups in dependency order
SERVICES=(db idp xmpp proxy)

compose() {
    local service="$1"
    shift
    docker compose \
        --project-directory "${PROJECT_ROOT}" \
        --env-file "${ENV_FILE}" \
        -f "${COMPOSE_DIR}/${service}/docker-compose.yml" \
        "$@"
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

cmd_up() {
    create_networks
    create_volumes
    for svc in "${SERVICES[@]}"; do
        echo "Starting: ${svc}"
        compose "$svc" up -d
    done
    echo "..."
    echo "All services started. Check status with: $0 status"
}

cmd_down() {
    # Stop in reverse order
    for (( i=${#SERVICES[@]}-1; i>=0; i-- )); do
        local svc="${SERVICES[$i]}"
        echo "Stopping: ${svc}"
        compose "$svc" down
    done
}

cmd_restart() {
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
    for svc in "${SERVICES[@]}"; do
        echo "=== ${svc} ==="
        compose "$svc" ps
        echo ""
    done
}

case "${1:-up}" in
    up)      cmd_up ;;
    down)    cmd_down ;;
    restart) cmd_restart "${2:-}" ;;
    status)  cmd_status ;;
    *)
        echo "Usage: $0 [up|down|restart <service>|status]"
        exit 1
        ;;
esac
