#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DB_ENV="${ROOT_DIR}/env/db.env"
IDP_ENV="${ROOT_DIR}/env/idp.env"
XMPP_ENV="${ROOT_DIR}/env/xmpp.env"

for file in "${DB_ENV}" "${IDP_ENV}" "${XMPP_ENV}"; do
  if [[ ! -f "${file}" ]]; then
    echo "missing ${file}" >&2
    echo "copy env/*.env.example files first" >&2
    exit 1
  fi
done

generate_secret() {
  openssl rand -base64 24 | tr -d '/+='
}

set_value() {
  local file="$1"
  local key="$2"
  local value="$3"
  sed -i "s|^${key}=.*$|${key}=${value}|" "${file}"
}

read_value() {
  local file="$1"
  local key="$2"
  awk -F= -v k="${key}" '$1==k {print $2}' "${file}"
}

if [[ "$(read_value "${DB_ENV}" "POSTGRES_PASSWORD")" == "REPLACE_ME" ]]; then
  set_value "${DB_ENV}" "POSTGRES_PASSWORD" "$(generate_secret)"
fi

kc_db_password="$(read_value "${DB_ENV}" "KC_DB_PASSWORD")"
if [[ "${kc_db_password}" == "REPLACE_ME" ]]; then
  kc_db_password="$(generate_secret)"
fi
set_value "${DB_ENV}" "KC_DB_PASSWORD" "${kc_db_password}"
set_value "${IDP_ENV}" "KC_DB_PASSWORD" "${kc_db_password}"

prosody_db_password="$(read_value "${DB_ENV}" "PROSODY_DB_PASSWORD")"
if [[ "${prosody_db_password}" == "REPLACE_ME" ]]; then
  prosody_db_password="$(generate_secret)"
fi
set_value "${DB_ENV}" "PROSODY_DB_PASSWORD" "${prosody_db_password}"
set_value "${XMPP_ENV}" "DB_PASSWORD" "${prosody_db_password}"

if [[ "$(read_value "${IDP_ENV}" "KC_BOOTSTRAP_ADMIN_PASSWORD")" == "REPLACE_ME" ]]; then
  set_value "${IDP_ENV}" "KC_BOOTSTRAP_ADMIN_PASSWORD" "$(generate_secret)"
fi

if [[ "$(read_value "${XMPP_ENV}" "PROSODY_OAUTH_SECRET")" == "REPLACE_ME" ]]; then
  set_value "${XMPP_ENV}" "PROSODY_OAUTH_SECRET" "$(generate_secret)"
fi

echo "updated secrets in env/{db,idp,xmpp}.env"
