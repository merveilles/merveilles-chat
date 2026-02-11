#!/usr/bin/env python3

from __future__ import annotations

import logging
import shutil
import subprocess
import sys
from pathlib import Path


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("setup")
    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("[%(levelname)s] %(message)s")
    handler.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(handler)

    logger.propagate = False
    return logger


logger = setup_logger()


def run(cmd: list[str], cwd: Path | None = None) -> None:
    try:
        logger.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            check=True,
            text=True,
            capture_output=True,
            cwd=str(cwd) if cwd else None,
        )
        out = (result.stdout or "").strip()
        err = (result.stderr or "").strip()

        if out:
            logger.info(f"stdout:\n{out}")
        if err:
            logger.info(f"stderr:\n{err}")

    except FileNotFoundError as exc:
        logger.info(f"Missing deps: {cmd[0]}")
        raise
    except subprocess.CalledProcessError as exc:
        out = (exc.stdout or "").strip()
        err = (exc.stderr or "").strip()
        logger.info("failed")
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


def ensure_dirs(project_root: Path) -> None:
    rel_paths = ["prosody/config", "prosody/certs", "prosody/data", "scripts"]
    for rel in rel_paths:
        target = project_root / rel
        target.mkdir(parents=True, exist_ok=True)


def initialize_env(project_root: Path) -> Path:
    env_path = project_root / ".env"
    env_example = project_root / ".env.example"
    postgres_data = project_root / "postgres_data"

    if env_path.exists():
        logger.info("Found existing .env file...")
        return env_path

    # do not generate a new .env against an existing DB state.
    if postgres_data.exists() and any(postgres_data.iterdir()):
        logger.info("Refusing to seed a new .env because postgres_data already exists.")
        logger.info(
            "This usually means Keycloak/Postgres state already has credentials from a previous .env."
        )
        logger.info("Recovery options:")
        logger.info("1. Restore the original .env used to initialize this database")
        logger.info("2. Reset local DB state (non-prod):")
        logger.info("mv postgres_data postgres_data.backup && mkdir -p postgres_data")
        raise RuntimeError("Cannot create .env while postgres_data is non-empty")

    if not env_example.exists():
        logger.info("Missing .env.example, cannot initialize .env")
        raise FileNotFoundError(str(env_example))

    logger.info("No .env found. What environment are we using?")
    logger.info("1) Non-Production")
    logger.info("2) Production")
    env_choice = input("Select an option [1-2]: ").strip()

    shutil.copyfile(env_example, env_path)
    logger.info(f"Seeded .env from .env.example: {env_path}")

    if env_choice == "2":
        prod_domain = input("Enter your production domain: ").strip()
        if not prod_domain:
            logger.info("Domain cannot be empty")
            raise ValueError("Domain cannot be empty")

        set_env_value(env_path, "DOMAIN", prod_domain)
        set_env_value(env_path, "PROSODY_ADMIN_JID", f"admin@{prod_domain}")
        logger.info(f"Configured production domain: {prod_domain}")
    else:
        logger.info("Staying with localhost for development.")

    return env_path


def run_secure_script(project_root: Path) -> None:
    secure_script = project_root / "scripts" / "secure.sh"
    if not secure_script.exists():
        logger.info("No scripts/secure.sh found. Skipping")
        return

    logger.info("Running secure.sh")
    run(["bash", str(secure_script)])


def generate_localhost_certs(project_root: Path, domain: str) -> None:
    prosody_cert_dir = project_root / "prosody" / "certs"
    localhost_key = prosody_cert_dir / "localhost.key"
    localhost_crt = prosody_cert_dir / "localhost.crt"

    if domain != "localhost":
        logger.info(f"Production environment detected ({domain}).")
        logger.info("Skipping self-signed certs. Make sure Certbot volumes are mapped.")
        return

    if localhost_key.exists() and localhost_crt.exists():
        logger.info("Localhost certs already exist. Skipping.")
        return

    logger.info("Generating self-signed certificates for localhost")
    run(
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
    modules_hg = modules_dir / ".hg"

    if not modules_hg.exists():
        logger.info("prosody-modules not found. Cloning community modules.")
        run(
            [
                "hg",
                "clone",
                "https://hg.prosody.im/prosody-modules/",
                str(modules_dir),
            ]
        )
        return

    logger.info("prosody-modules already present. Grabbing updates.")
    run(["hg", "-R", str(modules_dir), "pull", "-u"])


def set_permissions(project_root: Path) -> None:
    prosody_dir = project_root / "prosody"
    if not prosody_dir.exists():
        logger.info("Prosody directory does not exist yet. Skipping.")
        return

    logger.info(
        "Setting permissions under prosody/ (this is mostly to avoid container volume weirdness)"
    )
    run(["chmod", "-R", "755", str(prosody_dir)])


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

        logger.info("------------------------------------------")
        logger.info("Setup Complete")
        logger.info(f"Domain: {current_domain}")
        logger.info("Start containers, then bootstrap Keycloak with:")
        logger.info("./scripts/bootstrap-keycloak.py")
        logger.info("Optional: create a test user:")
        logger.info("./scripts/bootstrap-keycloak.py --user jim --password 'change-me'")
        return 0
    except Exception as err:
        logger.info(f"Setup failed: {err}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
