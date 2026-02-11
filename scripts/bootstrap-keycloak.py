#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import logging
import secrets
import shutil
import string
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("bootstrap-keycloak")
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("[%(levelname)s] %(message)s")
    handler.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(handler)

    logger.propagate = False
    return logger


logger = setup_logger()


class BootstrapError(Exception):
    pass


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    try:
        logger.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=check, text=True, capture_output=True)

        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()

        if out:
            logger.info(f"stdout:\n{out}")
        if err:
            logger.info(f"stderr:\n{err}")

        return result

    except FileNotFoundError as exc:
        raise BootstrapError(f"Missing dependency: {cmd[0]}") from exc
    except subprocess.CalledProcessError as exc:
        out = (exc.stdout or "").strip()
        err = (exc.stderr or "").strip()

        logger.info("Command failed")
        logger.info(f"exit code: {exc.returncode}")
        if out:
            logger.info(f"stdout:\n{out}")
        if err:
            logger.info(f"stderr:\n{err}")

        raise


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


def generate_secret(length: int = 32) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def parse_id(stdout: str) -> str:
    try:
        payload = json.loads(stdout or "[]")
    except json.JSONDecodeError as exc:
        raise BootstrapError("Unexpected JSON from kcadm while reading IDs") from exc

    if isinstance(payload, list) and payload and isinstance(payload[0], dict):
        value = payload[0].get("id", "")
        return str(value) if value else ""

    return ""


@dataclass
class BootstrapConfig:
    env_file: Path
    container: str
    server_url: str
    realm: str
    client_id: str
    admin_user: str
    admin_password: str


def validate_runtime(container: str) -> None:
    if shutil.which("docker") is None:
        raise BootstrapError("docker is required but was not found")

    ps = run(["docker", "ps", "--format", "{{.Names}}"])
    running = {line.strip() for line in (ps.stdout or "").splitlines() if line.strip()}
    if container not in running:
        raise BootstrapError(
            f"Container '{container}' is not running. Start your compose stack first."
        )

    logger.info(f"Found running Keycloak container: {container}")


def kcadm(
    cfg: BootstrapConfig, args: list[str], check: bool = True
) -> subprocess.CompletedProcess[str]:
    cmd = [
        "docker",
        "exec",
        cfg.container,
        "/opt/keycloak/bin/kcadm.sh",
        *args,
    ]
    return run(cmd, check=check)


def authenticate(cfg: BootstrapConfig) -> None:
    logger.info("Authenticating to Keycloak admin API")
    result = kcadm(
        cfg,
        [
            "config",
            "credentials",
            "--server",
            cfg.server_url,
            "--realm",
            "master",
            "--user",
            cfg.admin_user,
            "--password",
            cfg.admin_password,
        ],
        check=False,
    )
    if result.returncode != 0:
        message = (
            (result.stderr or "").strip()
            or (result.stdout or "").strip()
            or "Keycloak auth failed"
        )
        raise BootstrapError(message)


def get_id(cfg: BootstrapConfig, resource: str, query_key: str, query_val: str) -> str:
    result = kcadm(
        cfg,
        [
            "get",
            resource,
            "-r",
            cfg.realm,
            "-q",
            f"{query_key}={query_val}",
            "--fields",
            "id",
            "--format",
            "json",
        ],
    )
    return parse_id(result.stdout or "")


def ensure_realm(cfg: BootstrapConfig) -> None:
    logger.info(f"Checking realm: {cfg.realm}")
    exists = kcadm(cfg, ["get", f"realms/{cfg.realm}"], check=False)

    if exists.returncode != 0:
        logger.info(f"Creating realm '{cfg.realm}'")
        kcadm(
            cfg,
            [
                "create",
                "realms",
                "-s",
                f"realm={cfg.realm}",
                "-s",
                "enabled=true",
            ],
        )
    else:
        logger.info(f"Realm '{cfg.realm}' already exists")

    logger.info("Updating realm defaults")
    kcadm(
        cfg,
        [
            "update",
            f"realms/{cfg.realm}",
            "-s",
            "enabled=true",
            "-s",
            "verifyEmail=false",
            "-s",
            "loginWithEmailAllowed=true",
        ],
    )


def ensure_client(cfg: BootstrapConfig, secret: str) -> None:
    logger.info(f"Checking client: {cfg.client_id}")
    client_uuid = get_id(cfg, "clients", "clientId", cfg.client_id)

    if not client_uuid:
        logger.info(f"Creating client '{cfg.client_id}'")
        kcadm(
            cfg,
            [
                "create",
                "clients",
                "-r",
                cfg.realm,
                "-s",
                f"clientId={cfg.client_id}",
                "-s",
                "protocol=openid-connect",
                "-s",
                "enabled=true",
                "-s",
                "publicClient=false",
                "-s",
                "directAccessGrantsEnabled=true",
                "-s",
                "standardFlowEnabled=false",
                "-s",
                "serviceAccountsEnabled=false",
            ],
        )
        client_uuid = get_id(cfg, "clients", "clientId", cfg.client_id)

    if not client_uuid:
        raise BootstrapError(f"Unable to resolve client UUID for '{cfg.client_id}'")

    logger.info("Syncing client configuration and secret to env value")
    kcadm(
        cfg,
        [
            "update",
            f"clients/{client_uuid}",
            "-r",
            cfg.realm,
            "-s",
            "protocol=openid-connect",
            "-s",
            "enabled=true",
            "-s",
            "publicClient=false",
            "-s",
            "directAccessGrantsEnabled=true",
            "-s",
            "standardFlowEnabled=false",
            "-s",
            "serviceAccountsEnabled=false",
            "-s",
            f"secret={secret}",
        ],
    )


def ensure_user(cfg: BootstrapConfig, username: str, password: str) -> None:
    logger.info(f"Checking user: {username}")
    user_id = get_id(cfg, "users", "username", username)

    if not user_id:
        logger.info(f"Creating user '{username}'")
        kcadm(
            cfg,
            [
                "create",
                "users",
                "-r",
                cfg.realm,
                "-s",
                f"username={username}",
                "-s",
                "enabled=true",
            ],
        )
        user_id = get_id(cfg, "users", "username", username)

    if not user_id:
        raise BootstrapError(f"Unable to resolve user ID for '{username}'")

    user_email = username if "@" in username else f"{username}@localhost"
    logger.info(f"Updating user '{username}' policies")
    kcadm(
        cfg,
        [
            "update",
            f"users/{user_id}",
            "-r",
            cfg.realm,
            "-s",
            "enabled=true",
            "-s",
            f"email={user_email}",
            "-s",
            "emailVerified=true",
            "-s",
            "requiredActions=[]",
        ],
    )

    logger.info(f"Setting password for '{username}'")
    kcadm(
        cfg,
        [
            "set-password",
            "-r",
            cfg.realm,
            "--username",
            username,
            "--new-password",
            password,
            "--temporary",
            "false",
        ],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstraps Keycloak for Prosody OIDC: realm, client, and optionally creates a user."
    )
    parser.add_argument("--user", help="Optional username to create/update")
    parser.add_argument("--password", help="Password for --user")
    return parser.parse_args()


def load_config(env_file: Path) -> tuple[BootstrapConfig, str, bool]:
    env = load_env(env_file)

    admin_user = env.get("KC_ADMIN", "")
    admin_password = env.get("KC_ADMIN_PASSWORD", "")
    if not admin_user or not admin_password:
        raise BootstrapError("KC_ADMIN and KC_ADMIN_PASSWORD must be set in .env")

    secret = env.get("PROSODY_OAUTH_SECRET", "")
    secret_generated = False

    if not secret or secret == "PASTE_FROM_KEYCLOAK_UI":
        logger.info("No PROSODY_OAUTH_SECRET set. Generating one and writing to .env")
        secret = generate_secret()
        set_env_value(env_file, "PROSODY_OAUTH_SECRET", secret)
        secret_generated = True
    else:
        logger.info("Found existing PROSODY_OAUTH_SECRET in .env")

    cfg = BootstrapConfig(
        env_file=env_file,
        container=env.get("KC_CONTAINER", "chat-idp"),
        server_url=env.get("KC_SERVER_URL", "http://localhost:8080"),
        realm=env.get("KC_REALM", "chat"),
        client_id=env.get("KC_CLIENT_ID", "prosody-backend"),
        admin_user=admin_user,
        admin_password=admin_password,
    )

    logger.info(
        f"Config: container={cfg.container} server={cfg.server_url} realm={cfg.realm} client={cfg.client_id}"
    )
    return cfg, secret, secret_generated


def main() -> int:
    args = parse_args()

    if args.user and not args.password:
        logger.info("--password is required when --user is provided")
        return 1

    env_file = Path(__file__).resolve().parent.parent / ".env"
    if not env_file.exists():
        logger.info(f"Missing .env file at {env_file}")
        return 1

    try:
        cfg, secret, secret_generated = load_config(env_file)
        validate_runtime(cfg.container)

        authenticate(cfg)
        ensure_realm(cfg)
        ensure_client(cfg, secret)

        if args.user:
            ensure_user(cfg, args.user, args.password or "")

    except BootstrapError as exc:
        logger.info(str(exc))
        return 1
    except subprocess.CalledProcessError as exc:
        message = (exc.stderr or "").strip() or (exc.stdout or "").strip() or str(exc)
        logger.info(message)
        return 1
    except KeyboardInterrupt:
        logger.info("Interrupted.")
        return 130
    except Exception as err:
        logger.info(f"Unexpected error: {err}")
        return 1

    logger.info("Done.")
    logger.info(f"Realm: {cfg.realm}")
    logger.info(f"Client: {cfg.client_id}")
    if args.user:
        logger.info(f"User: {args.user}")
    if secret_generated:
        logger.info("Generated and saved PROSODY_OAUTH_SECRET in .env")
        logger.info("Recreate chat-server to load updated env:")
        logger.info(
            "docker compose -f docker-compose.non-prod.yml up -d --force-recreate chat-server"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
