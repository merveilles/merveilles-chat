#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from lib.common import BootstrapError, load_env, run, setup_logger
from lib.keycloak_admin import BootstrapConfig, KeycloakAdmin, parse_clients_file

logger = setup_logger("bootstrap-keycloak")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="set up keycloak realm, roles, groups, and clients")
    parser.add_argument("--realm", help="override realm name (default: KC_REALM from env/stack.env)")
    parser.add_argument("--client", help="only set up one client")
    parser.add_argument("--user", help="optional user to create/update")
    parser.add_argument("--password", help="password for --user")
    return parser.parse_args()


def load_config(project_root: Path, realm_override: str | None) -> tuple[BootstrapConfig, dict[str, str]]:
    stack_env = project_root / "env" / "stack.env"
    idp_env = project_root / "env" / "idp.env"
    xmpp_env = project_root / "env" / "xmpp.env"

    for path in [stack_env, idp_env, xmpp_env]:
        if not path.exists():
            raise BootstrapError(f"Missing env file: {path}")

    merged: dict[str, str] = {}
    for path in [stack_env, idp_env, xmpp_env]:
        merged.update(load_env(path))

    admin_user = merged.get("KC_BOOTSTRAP_ADMIN_USERNAME", "")
    admin_password = merged.get("KC_BOOTSTRAP_ADMIN_PASSWORD", "")
    if not admin_user or not admin_password:
        raise BootstrapError("KC_BOOTSTRAP_ADMIN_USERNAME and KC_BOOTSTRAP_ADMIN_PASSWORD are required")

    realm = (realm_override or merged.get("KC_REALM") or "community").strip()
    if not realm:
        raise BootstrapError("Realm cannot be empty")

    cfg = BootstrapConfig(
        env_file=xmpp_env,
        clients_file=project_root / "keycloak-config" / "clients.json",
        container=merged.get("KC_CONTAINER", "chat-idp"),
        server_url=merged.get("KC_SERVER_URL", "http://localhost:8080"),
        realm=realm,
        admin_user=admin_user,
        admin_password=admin_password,
    )
    return cfg, merged


def resolve_client_secrets(env: dict[str, str], definitions: list) -> dict[str, str]:
    secrets_by_client: dict[str, str] = {}

    for definition in definitions:
        value = env.get(definition.secret_env_key, "").strip()
        if not value or value == "REPLACE_ME":
            raise BootstrapError(
                f"Missing secret for client '{definition.name}' in env key {definition.secret_env_key}"
            )
        secrets_by_client[definition.name] = value

    return secrets_by_client


def main() -> int:
    args = parse_args()

    if args.user and not args.password:
        logger.info("--password is required with --user")
        return 1

    project_root = Path(__file__).resolve().parent.parent

    try:
        cfg, env = load_config(project_root, args.realm)
        clients = parse_clients_file(cfg.clients_file)

        if args.client and args.client not in clients:
            raise BootstrapError(f"Unknown client '{args.client}' in {cfg.clients_file}")

        selected_clients = [clients[args.client]] if args.client else list(clients.values())
        secrets_by_client = resolve_client_secrets(env, selected_clients)

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
        logger.info("interrupted")
        return 130

    logger.info("done")
    logger.info(f"realm: {cfg.realm}")
    logger.info("clients: " + ", ".join(client.name for client in selected_clients))
    if args.user:
        logger.info(f"user: {args.user}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
