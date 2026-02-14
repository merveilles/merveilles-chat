#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_DIR="${ROOT_DIR}/env"
IN_DIR="${ENV_DIR}/encrypted"

if ! command -v sops >/dev/null 2>&1; then
  echo "sops is required" >&2
  exit 1
fi

if [[ ! -d "${IN_DIR}" ]]; then
  echo "missing ${IN_DIR}" >&2
  exit 1
fi

for src in "${IN_DIR}"/*.enc; do
  [[ -f "${src}" ]] || continue
  base="$(basename "${src}" .enc)"
  dst="${ENV_DIR}/${base}"
  sops --decrypt "${src}" > "${dst}"
  echo "decrypted ${src} -> ${dst}"
done
