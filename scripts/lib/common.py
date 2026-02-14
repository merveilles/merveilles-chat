from __future__ import annotations

import json
import logging
import secrets
import string
import subprocess
import sys
from pathlib import Path
from typing import Any


class BootstrapError(Exception):
    pass


def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("[%(levelname)s] %(message)s")
    handler.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(handler)

    logger.propagate = False
    return logger


def run(
    cmd: list[str],
    logger: logging.Logger,
    check: bool = True,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        logger.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            check=check,
            text=True,
            capture_output=True,
            cwd=str(cwd) if cwd else None,
        )
    except FileNotFoundError as exc:
        raise BootstrapError(f"Missing dependency: {cmd[0]}") from exc
    except subprocess.CalledProcessError as exc:
        out = (exc.stdout or "").strip()
        err = (exc.stderr or "").strip()
        message = err or out or f"Command failed ({exc.returncode}): {' '.join(cmd)}"
        raise BootstrapError(message) from exc

    out = (result.stdout or "").strip()
    err = (result.stderr or "").strip()
    if out:
        logger.info(f"stdout:\n{out}")
    if err:
        logger.info(f"stderr:\n{err}")

    return result


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env

    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key] = value
    return env


def set_env_value(path: Path, key: str, value: str) -> None:
    lines = path.read_text().splitlines() if path.exists() else []
    out: list[str] = []
    replaced = False

    for line in lines:
        if line.startswith(f"{key}="):
            out.append(f"{key}={value}")
            replaced = True
        else:
            out.append(line)

    if not replaced:
        out.append(f"{key}={value}")

    path.write_text("\n".join(out) + "\n")


def generate_secret(length: int = 48) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def parse_json(stdout: str) -> Any:
    try:
        return json.loads(stdout or "null")
    except json.JSONDecodeError as exc:
        raise BootstrapError("Unexpected JSON from Keycloak admin command") from exc


def parse_id(stdout: str) -> str:
    payload = parse_json(stdout)

    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        value = payload[0].get("id", "")
        return str(value) if value else ""

    if isinstance(payload, dict):
        value = payload.get("id", "")
        return str(value) if value else ""

    return ""


def bool_to_kc(value: bool) -> str:
    return "true" if value else "false"


def is_missing_secret(value: str) -> bool:
    placeholders = {
        "",
        "REPLACE_ME",
        "PASTE_FROM_KEYCLOAK_UI",
        "__PLACEHOLDER__",
    }
    return value.strip() in placeholders
