#!/usr/bin/env python3

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from lib.common import BootstrapError, load_env, run, set_env_value, setup_logger

logger = setup_logger("setup")

ENV_FILES = ["stack.env", "db.env", "idp.env", "xmpp.env", "proxy.env"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initial project setup")
    parser.add_argument(
        "--domain",
        help="Set domain (e.g. 'localhost' or 'example.com'). Skips interactive prompt.",
    )
    return parser.parse_args()


def run_cmd(cmd: list[str], cwd: Path | None = None) -> None:
    run(cmd=cmd, logger=logger, check=True, cwd=cwd)


def ensure_dirs(project_root: Path) -> None:
    for rel in [
        "env",
        "env/encrypted",
        "prosody/config",
        "prosody/certs",
        "prosody/data",
        "scripts",
        "keycloak-config/import",
    ]:
        (project_root / rel).mkdir(parents=True, exist_ok=True)


def ensure_env_files(project_root: Path) -> Path:
    env_dir = project_root / "env"
    postgres_data = project_root / "postgres_data"

    if postgres_data.exists() and any(postgres_data.iterdir()) and not (env_dir / "db.env").exists():
        raise BootstrapError(
            "Refusing to create env/db.env while postgres_data is non-empty. "
            "Restore previous env files or reset postgres_data."
        )

    for name in ENV_FILES:
        dst = env_dir / name
        src = env_dir / f"{name}.example"
        if dst.exists():
            continue
        if not src.exists():
            raise BootstrapError(f"Missing template: {src}")
        shutil.copyfile(src, dst)
        logger.info(f"Created {dst} from template")

    return env_dir / "stack.env"


def configure_domain(project_root: Path, domain_override: str | None = None) -> None:
    env_dir = project_root / "env"
    stack_env = env_dir / "stack.env"
    xmpp_env = env_dir / "xmpp.env"
    proxy_env = env_dir / "proxy.env"
    idp_env = env_dir / "idp.env"

    stack = load_env(stack_env)

    # If --domain was passed, use it directly (non-interactive)
    if domain_override:
        target_domain = domain_override
    elif stack.get("DOMAIN", "localhost") != "localhost":
        # Already configured to something other than localhost
        return
    else:
        # Interactive prompt
        logger.info("1) Non-Production")
        logger.info("2) Production")
        env_choice = input("Select an option [1-2]: ").strip()

        if env_choice != "2":
            logger.info("Using localhost defaults")
            return

        target_domain = input("Enter your production domain: ").strip()
        if not target_domain:
            raise BootstrapError("Domain cannot be empty")

    set_env_value(stack_env, "DOMAIN", target_domain)
    set_env_value(xmpp_env, "DOMAIN", target_domain)
    set_env_value(xmpp_env, "PROSODY_ADMIN_JID", f"admin@{target_domain}")
    set_env_value(proxy_env, "DOMAIN", target_domain)
    set_env_value(idp_env, "KC_HOSTNAME", f"sso.{target_domain}")
    logger.info(f"Configured DOMAIN={target_domain}")


def run_secure_script(project_root: Path) -> None:
    secure_script = project_root / "scripts" / "secure.sh"
    if not secure_script.exists():
        logger.info("No scripts/secure.sh found, skipping")
        return
    run_cmd(["bash", str(secure_script)])


def generate_localhost_certs(project_root: Path, domain: str) -> None:
    if domain != "localhost":
        logger.info(f"DOMAIN={domain}, skipping localhost self-signed cert generation")
        return

    cert_dir = project_root / "prosody" / "certs"
    localhost_key = cert_dir / "localhost.key"
    localhost_crt = cert_dir / "localhost.crt"

    if localhost_key.exists() and localhost_crt.exists():
        logger.info("Localhost certs already exist, skipping")
        return

    run_cmd(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(localhost_key),
            "-out",
            str(localhost_crt),
            "-days",
            "365",
            "-subj",
            "/CN=localhost",
        ]
    )


def sync_prosody_modules(project_root: Path) -> None:
    modules_dir = project_root / "prosody" / "modules"

    if not (modules_dir / ".hg").exists():
        run_cmd(["hg", "clone", "https://hg.prosody.im/prosody-modules/", str(modules_dir)])
        return

    run_cmd(["hg", "-R", str(modules_dir), "pull", "-u"])


def set_permissions(project_root: Path) -> None:
    prosody_dir = project_root / "prosody"
    if prosody_dir.exists():
        run_cmd(["chmod", "-R", "755", str(prosody_dir)])


def main() -> int:
    try:
        args = parse_args()
        project_root = Path.cwd()
        logger.info(f"Project root: {project_root}")

        ensure_dirs(project_root)
        stack_env = ensure_env_files(project_root)
        configure_domain(project_root, domain_override=args.domain)
        set_permissions(project_root)
        run_secure_script(project_root)

        domain = load_env(stack_env).get("DOMAIN", "localhost")
        logger.info(f"Detected DOMAIN={domain}")

        generate_localhost_certs(project_root, domain)
        sync_prosody_modules(project_root)

        logger.info("Setup complete")
        return 0
    except BootstrapError as exc:
        logger.info(str(exc))
        return 1
    except KeyboardInterrupt:
        logger.info("Interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
