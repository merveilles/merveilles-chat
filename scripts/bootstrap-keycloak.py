#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from lib.common import (
    BootstrapError,
    generate_secret,
    is_missing_secret,
    load_env,
    run,
    set_env_value,
    setup_logger,
)
from lib.keycloak_admin import BootstrapConfig, ClientDefinition, KeycloakAdmin, parse_clients_file

logger = setup_logger("bootstrap-keycloak")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap Keycloak realm, groups, roles, and clients from keycloak-config/clients.json"
    )
    parser.add_argument("--realm", help="Realm name override (defaults to KC_REALM from .env)")
    parser.add_argument("--client", help="Only bootstrap a specific client")
    parser.add_argument("--user", help="Optional username to create/update")
    parser.add_argument("--password", help="Password for --user")
    return parser.parse_args()


def load_config(env_file: Path, realm_override: str | None) -> tuple[BootstrapConfig, dict[str, str]]:
    env = load_env(env_file)

    admin_user = env.get("KC_ADMIN", "")
    admin_password = env.get("KC_ADMIN_PASSWORD", "")
    if not admin_user or not admin_password:
        raise BootstrapError("KC_ADMIN and KC_ADMIN_PASSWORD must be set in .env")

    realm = (realm_override or env.get("KC_REALM") or "merveilles").strip()
    if not realm:
        raise BootstrapError("Realm cannot be empty")

    cfg = BootstrapConfig(
        env_file=env_file,
        clients_file=env_file.parent / "keycloak-config" / "clients.json",
        container=env.get("KC_CONTAINER", "chat-idp"),
        server_url=env.get("KC_SERVER_URL", "http://localhost:8080"),
        realm=realm,
        admin_user=admin_user,
        admin_password=admin_password,
    )
    return cfg, env


def resolve_client_secrets(
    env_file: Path,
    env: dict[str, str],
    definitions: list[ClientDefinition],
) -> tuple[dict[str, str], list[str]]:
    generated: list[str] = []
    secrets_by_client: dict[str, str] = {}

    for definition in definitions:
        value = env.get(definition.secret_env_key, "")
        if is_missing_secret(value):
            value = generate_secret()
            set_env_value(env_file, definition.secret_env_key, value)
            env[definition.secret_env_key] = value
            generated.append(definition.secret_env_key)

        secrets_by_client[definition.name] = value

    return secrets_by_client, generated


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
        cfg, env = load_config(env_file, args.realm)
        clients = parse_clients_file(cfg.clients_file)

        if args.client and args.client not in clients:
            raise BootstrapError(f"Unknown client '{args.client}' in {cfg.clients_file}")

        selected_clients = [clients[args.client]] if args.client else list(clients.values())
        secrets_by_client, generated_keys = resolve_client_secrets(cfg.env_file, env, selected_clients)

        admin = KeycloakAdmin(cfg=cfg, logger=logger, run_cmd=run)
        admin.validate_runtime()
        admin.authenticate()
        admin.ensure_realm()

        for role_name in ["community-member", "community-admin"]:
            admin.ensure_role(role_name)
        for group_name in ["Members", "Admins"]:
            admin.ensure_group(group_name)

        admin.ensure_realm_defaults()

        for scope_name in ["community-profile", "xmpp-access", "forum-access"]:
            admin.ensure_client_scope(scope_name)
        for definition in selected_clients:
            admin.ensure_client(definition, secrets_by_client[definition.name])

        if args.user:
            admin.ensure_user(args.user, args.password)

    except BootstrapError as exc:
        logger.info(str(exc))
        return 1
    except KeyboardInterrupt:
        logger.info("Interrupted")
        return 130

    logger.info("Done")
    logger.info(f"Realm: {cfg.realm}")
    logger.info("Clients: " + ", ".join(client.name for client in selected_clients))
    if args.user:
        logger.info(f"User: {args.user}")
    if generated_keys:
        logger.info("Generated env keys: " + ", ".join(generated_keys))
        logger.info("Recreate chat-server to load updated env")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
