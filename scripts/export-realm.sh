#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${ROOT_DIR}/keycloak-config/import"
STACK_ENV="${ROOT_DIR}/env/stack.env"

if [[ ! -f "${STACK_ENV}" ]]; then
  echo "missing env file: ${STACK_ENV}" >&2
  exit 1
fi

# shellcheck disable=SC1090
source "${STACK_ENV}"

KC_CONTAINER="${KC_CONTAINER:-chat-idp}"
KC_REALM="${KC_REALM:-community}"
CONTAINER_EXPORT_DIR="/tmp/realm-export"
TMP_JSON="$(mktemp)"
trap 'rm -f "${TMP_JSON}"' EXIT

mkdir -p "${OUT_DIR}"

docker exec "${KC_CONTAINER}" /opt/keycloak/bin/kc.sh export \
  --realm "${KC_REALM}" \
  --dir "${CONTAINER_EXPORT_DIR}" \
  --users realm_file

docker cp "${KC_CONTAINER}:${CONTAINER_EXPORT_DIR}/${KC_REALM}-realm.json" "${TMP_JSON}"
docker exec "${KC_CONTAINER}" rm -rf "${CONTAINER_EXPORT_DIR}"

python3 "${ROOT_DIR}/scripts/redact-realm.py" \
  "${TMP_JSON}" \
  "${OUT_DIR}/${KC_REALM}-realm.json"

echo "realm export written to ${OUT_DIR}/${KC_REALM}-realm.json"
