#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_DIR="${ROOT_DIR}/env"
OUT_DIR="${ENV_DIR}/encrypted"

if ! command -v sops >/dev/null 2>&1; then
  echo "sops is required" >&2
  exit 1
fi

if [[ -z "${SOPS_AGE_RECIPIENTS:-}" ]]; then
  echo "set SOPS_AGE_RECIPIENTS (comma-separated age recipients)" >&2
  exit 1
fi

mkdir -p "${OUT_DIR}"

for src in "${ENV_DIR}"/*.env; do
  [[ -f "${src}" ]] || continue
  base="$(basename "${src}")"
  dst="${OUT_DIR}/${base}.enc"
  sops --encrypt --age "${SOPS_AGE_RECIPIENTS}" "${src}" > "${dst}"
  echo "encrypted ${src} -> ${dst}"
done
