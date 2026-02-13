#!/usr/bin/env python3

from __future__ import annotations

import shutil
from pathlib import Path

from lib.common import BootstrapError, load_env, run, set_env_value, setup_logger

logger = setup_logger("setup")


def run_cmd(cmd: list[str], cwd: Path | None = None) -> None:
    run(cmd=cmd, logger=logger, check=True, cwd=cwd)


def ensure_dirs(project_root: Path) -> None:
    for rel in [
        "prosody/config",
        "prosody/certs",
        "prosody/data",
        "scripts",
        "keycloak-config/import",
    ]:
        (project_root / rel).mkdir(parents=True, exist_ok=True)


def initialize_env(project_root: Path) -> Path:
    env_path = project_root / ".env"
    env_example = project_root / ".env.example"
    postgres_data = project_root / "postgres_data"

    if env_path.exists():
        logger.info("Found existing .env file")
        return env_path

    if postgres_data.exists() and any(postgres_data.iterdir()):
        raise BootstrapError(
            "Refusing to seed .env while postgres_data is non-empty."
            "Restore the original .env or reset postgres_data."
        )

    if not env_example.exists():
        raise BootstrapError("Missing .env.example")

    logger.info("No .env found")
    logger.info("1) Non-Production")
    logger.info("2) Production")
    env_choice = input("Select an option [1-2]: ").strip()

    shutil.copyfile(env_example, env_path)
    logger.info(f"Seeded .env from .env.example: {env_path}")

    if env_choice == "2":
        prod_domain = input("Enter your production domain: ").strip()
        if not prod_domain:
            raise BootstrapError("Domain cannot be empty")

        set_env_value(env_path, "DOMAIN", prod_domain)
        set_env_value(env_path, "PROSODY_ADMIN_JID", f"admin@{prod_domain}")
        logger.info(f"Configured production domain: {prod_domain}")
    else:
        logger.info("Using localhost defaults")

    return env_path


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
        run_cmd(
            ["hg", "clone", "https://hg.prosody.im/prosody-modules/", str(modules_dir)]
        )
        return

    run_cmd(["hg", "-R", str(modules_dir), "pull", "-u"])


def set_permissions(project_root: Path) -> None:
    prosody_dir = project_root / "prosody"
    if not prosody_dir.exists():
        return

    run_cmd(["chmod", "-R", "755", str(prosody_dir)])


def main() -> int:
    try:
        project_root = Path.cwd()
        logger.info(f"Project root: {project_root}")

        env_path = initialize_env(project_root)
        ensure_dirs(project_root)
        set_permissions(project_root)
        run_secure_script(project_root)

        env = load_env(env_path)
        current_domain = env.get("DOMAIN", "localhost")
        logger.info(f"Detected DOMAIN={current_domain}")

        generate_localhost_certs(project_root, current_domain)
        sync_prosody_modules(project_root)

        logger.info("Setup complete")
        logger.info("Next: ./scripts/bootstrap-keycloak.py")
        return 0
    except BootstrapError as exc:
        logger.info(str(exc))
        return 1
    except KeyboardInterrupt:
        logger.info("Interrupted")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
