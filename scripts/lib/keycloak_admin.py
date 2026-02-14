from __future__ import annotations

import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .common import BootstrapError, bool_to_kc, parse_id, parse_json

RunFn = Callable[[list[str], logging.Logger, bool], subprocess.CompletedProcess[str]]


@dataclass
class BootstrapConfig:
    env_file: Path
    clients_file: Path
    container: str
    server_url: str
    realm: str
    admin_user: str
    admin_password: str


@dataclass
class ClientDefinition:
    name: str
    direct_access_grants: bool
    standard_flow: bool
    secret_env_key: str
    service_accounts: bool


class KeycloakAdmin:
    def __init__(self, cfg: BootstrapConfig, logger: logging.Logger, run_cmd: RunFn):
        self.cfg = cfg
        self.logger = logger
        self._run = run_cmd

    def run(self, cmd: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
        return self._run(cmd, self.logger, check)

    def validate_runtime(self) -> None:
        if shutil.which("docker") is None:
            raise BootstrapError("docker is required but was not found")

        ps = self.run(["docker", "ps", "--format", "{{.Names}}"])
        running = {line.strip() for line in (ps.stdout or "").splitlines() if line.strip()}
        if self.cfg.container not in running:
            raise BootstrapError(
                f"Container '{self.cfg.container}' is not running. Start your compose stack first."
            )

        self.logger.info(f"Found running Keycloak container: {self.cfg.container}")

    def kcadm(self, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
        cmd = [
            "docker",
            "exec",
            self.cfg.container,
            "/opt/keycloak/bin/kcadm.sh",
            *args,
        ]
        return self.run(cmd, check)

    def authenticate(self) -> None:
        self.logger.info("Authenticating to Keycloak admin API")
        result = self.kcadm(
            [
                "config",
                "credentials",
                "--server",
                self.cfg.server_url,
                "--realm",
                "master",
                "--user",
                self.cfg.admin_user,
                "--password",
                self.cfg.admin_password,
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

    def get_id(self, resource: str, query_key: str, query_val: str) -> str:
        result = self.kcadm(
            [
                "get",
                resource,
                "-r",
                self.cfg.realm,
                "-q",
                f"{query_key}={query_val}",
                "--fields",
                "id",
                "--format",
                "json",
            ],
        )
        return parse_id(result.stdout or "")

    def ensure_realm(self) -> None:
        self.logger.info(f"Checking realm: {self.cfg.realm}")
        exists = self.kcadm(["get", f"realms/{self.cfg.realm}"], check=False)

        if exists.returncode != 0:
            self.logger.info(f"Creating realm '{self.cfg.realm}'")
            self.kcadm(
                [
                    "create",
                    "realms",
                    "-s",
                    f"realm={self.cfg.realm}",
                    "-s",
                    "enabled=true",
                ],
            )
        else:
            self.logger.info(f"Realm '{self.cfg.realm}' already exists")

        self.logger.info("Updating realm defaults")
        self.kcadm(
            [
                "update",
                f"realms/{self.cfg.realm}",
                "-s",
                "enabled=true",
                "-s",
                "verifyEmail=false",
                "-s",
                "loginWithEmailAllowed=true",
            ],
        )

    def ensure_realm_defaults(self) -> None:
        self.logger.info("Applying realm default groups")
        self.kcadm(
            [
                "update",
                f"realms/{self.cfg.realm}",
                "-s",
                'defaultGroups=["/Members"]',
            ],
        )

    def ensure_role(self, role_name: str) -> None:
        result = self.kcadm(["get", f"roles/{role_name}", "-r", self.cfg.realm], check=False)
        if result.returncode == 0:
            self.logger.info(f"Role '{role_name}' already exists")
            return

        self.logger.info(f"Creating role '{role_name}'")
        self.kcadm(
            [
                "create",
                "roles",
                "-r",
                self.cfg.realm,
                "-s",
                f"name={role_name}",
                "-s",
                "composite=false",
            ],
        )

    def ensure_group(self, group_name: str) -> None:
        result = self.kcadm(
            [
                "get",
                "groups",
                "-r",
                self.cfg.realm,
                "-q",
                f"search={group_name}",
                "--format",
                "json",
            ],
        )
        payload = parse_json(result.stdout or "[]")

        if isinstance(payload, list):
            for entry in payload:
                if isinstance(entry, dict) and entry.get("name") == group_name:
                    self.logger.info(f"Group '{group_name}' already exists")
                    return

        self.logger.info(f"Creating group '{group_name}'")
        self.kcadm(
            ["create", "groups", "-r", self.cfg.realm, "-s", f"name={group_name}"],
        )

    def ensure_client_scope(self, scope_name: str) -> None:
        result = self.kcadm(
            [
                "get",
                "client-scopes",
                "-r",
                self.cfg.realm,
                "-q",
                f"name={scope_name}",
                "--format",
                "json",
            ],
        )

        payload = parse_json(result.stdout or "[]")
        if isinstance(payload, list):
            for entry in payload:
                if isinstance(entry, dict) and entry.get("name") == scope_name:
                    self.logger.info(f"Client scope '{scope_name}' already exists")
                    return

        self.logger.info(f"Creating client scope '{scope_name}'")
        self.kcadm(
            [
                "create",
                "client-scopes",
                "-r",
                self.cfg.realm,
                "-s",
                f"name={scope_name}",
                "-s",
                "protocol=openid-connect",
            ],
        )

    def ensure_client(self, definition: ClientDefinition, secret: str) -> None:
        self.logger.info(f"Checking client: {definition.name}")
        client_uuid = self.get_id("clients", "clientId", definition.name)

        if not client_uuid:
            self.logger.info(f"Creating client '{definition.name}'")
            self.kcadm(
                [
                    "create",
                    "clients",
                    "-r",
                    self.cfg.realm,
                    "-s",
                    f"clientId={definition.name}",
                    "-s",
                    "protocol=openid-connect",
                    "-s",
                    "enabled=true",
                    "-s",
                    "publicClient=false",
                    "-s",
                    f"directAccessGrantsEnabled={bool_to_kc(definition.direct_access_grants)}",
                    "-s",
                    f"standardFlowEnabled={bool_to_kc(definition.standard_flow)}",
                    "-s",
                    f"serviceAccountsEnabled={bool_to_kc(definition.service_accounts)}",
                ],
            )
            client_uuid = self.get_id("clients", "clientId", definition.name)

        if not client_uuid:
            raise BootstrapError(f"Unable to resolve client UUID for '{definition.name}'")

        self.logger.info(f"Syncing client configuration for '{definition.name}'")
        args = [
            "update",
            f"clients/{client_uuid}",
            "-r",
            self.cfg.realm,
            "-s",
            "protocol=openid-connect",
            "-s",
            "enabled=true",
            "-s",
            "publicClient=false",
            "-s",
            f"directAccessGrantsEnabled={bool_to_kc(definition.direct_access_grants)}",
            "-s",
            f"standardFlowEnabled={bool_to_kc(definition.standard_flow)}",
            "-s",
            f"serviceAccountsEnabled={bool_to_kc(definition.service_accounts)}",
        ]

        if secret:
            args.extend(["-s", f"secret={secret}"])

        self.kcadm(args)

    def ensure_user(self, username: str, password: str) -> None:
        self.logger.info(f"Checking user: {username}")
        user_id = self.get_id("users", "username", username)

        if not user_id:
            self.logger.info(f"Creating user '{username}'")
            self.kcadm(
                [
                    "create",
                    "users",
                    "-r",
                    self.cfg.realm,
                    "-s",
                    f"username={username}",
                    "-s",
                    "enabled=true",
                ],
            )
            user_id = self.get_id("users", "username", username)

        if not user_id:
            raise BootstrapError(f"Unable to resolve user ID for '{username}'")

        user_email = username if "@" in username else f"{username}@localhost"
        self.logger.info(f"Updating user '{username}' policies")
        self.kcadm(
            [
                "update",
                f"users/{user_id}",
                "-r",
                self.cfg.realm,
                "-s",
                "enabled=true",
                "-s",
                f"email={user_email}",
                "-s",
                "emailVerified=true",
                "-s",
                "requiredActions=[]",
                "-s",
                'groups=["/Members"]',
            ],
        )

        self.logger.info(f"Setting password for '{username}'")
        self.kcadm(
            [
                "set-password",
                "-r",
                self.cfg.realm,
                "--username",
                username,
                "--new-password",
                password,
                "--temporary",
                "false",
            ],
        )


def parse_clients_file(path: Path) -> dict[str, ClientDefinition]:
    if not path.exists():
        raise BootstrapError(f"Missing client definition file: {path}")

    raw = parse_json(path.read_text())
    if not isinstance(raw, dict):
        raise BootstrapError("clients.json must be a JSON object keyed by client name")

    clients: dict[str, ClientDefinition] = {}
    for client_name, cfg in raw.items():
        if not isinstance(client_name, str) or not client_name:
            raise BootstrapError("clients.json contains an invalid client name")
        if not isinstance(cfg, dict):
            raise BootstrapError(f"clients.json entry '{client_name}' must be an object")

        secret_env_key = str(cfg.get("secretEnvKey", "")).strip()
        if not secret_env_key:
            raise BootstrapError(f"clients.json entry '{client_name}' requires secretEnvKey")

        clients[client_name] = ClientDefinition(
            name=client_name,
            direct_access_grants=bool(cfg.get("directAccessGrants", False)),
            standard_flow=bool(cfg.get("standardFlow", True)),
            secret_env_key=secret_env_key,
            service_accounts=bool(cfg.get("serviceAccounts", False)),
        )

    return clients
