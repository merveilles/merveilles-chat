# Merveilles XMPP Stack
Prosody + Keycloak + Postgres

This is the Merveilles chat stack. It is a clean, reproducible XMPP setup built around:
- `prosodyim/prosody:0.12` for the XMPP server
- `keycloak/keycloak:26.5` for OIDC identity
- `postgres:18-alpine` for persistence

It runs in two clearly separated modes:
- Non-production: local development, localhost domain, self-signed or mkcert TLS
- Production: real domain, Let's Encrypt certs mounted from host, tighter defaults

## Prerequisites

Docker + Docker Compose
openssl
hg (Mercurial) for prosody-modules
Optional but recommended for local TLS: mkcert

## What's Implemented
There are fully separate Prosody configs per environment:

`prosody/config/prosody.np.cfg.lua`
`prosody/config/prosody.prod.cfg.lua`

Compose mounts the correct one directly to:
`/etc/prosody/prosody.cfg.lua`

So, only change the prosody.np and prosody.prod files please.

### Keycloak bootstrap is automated

`scripts/bootstrap-keycloak.py` will:

Ensure realm chat exists
Ensure client prosody-backend exists
Enable direct access grants
Sync the client secret from .env
Optionally create a test user

## Repository Layout
- `docker-compose.non-prod.yml` – development
- `docker-compose.production.yml` – production
- `prosody/config/prosody.np.cfg.lua` – non-prod Prosody config
- `prosody/config/prosody.prod.cfg.lua` – production Prosody config
- `scripts/setup.py` – initial setup (env seed, localhost certs, module sync)
- `scripts/secure.sh` – randomizes placeholder secrets in .env
- `scripts/bootstrap-keycloak.py` – Keycloak realm/client/user bootstrap
- `init-schemas.sql` – database initialization


## Quick Start – Non-Prod

Initial setup:
`./scripts/setup.py`
or
`python3 scripts/setup.py`

Start:
`docker compose -f docker-compose.non-prod.yml up`

Run the Keycloak bootstrap:
`./scripts/bootstrap-keycloak.py`
or
`python3 scripts/bootstrap-keycloak.py`

If `PROSODY_OAUTH_SECRET` is missing/placeholder, bootstrap will generate one and write it to `.env`.

Recreate Prosody so it picks up the OIDC secret:
`docker compose -f docker-compose.non-prod.yml up -d --force-recreate chat-server`

and if you want, create a test user:
`./scripts/bootstrap-keycloak.py --user jim --password 'change-me'`

Connect an XMPP client (I'm using Profanity)

To access the Keycloak UI go to: http://localhost:8080
```
JID/domain: jim@localhost
Server: localhost
Port: 5222
```
Important: do not use 127.0.0.1 as your XMPP domain. Prosody serves localhost unless you configure a real domain.

## Environment Variables
These are what should be in the environment vars:

DOMAIN
PROSODY_ADMIN_JID
PROSODY_OAUTH_SECRET
DB_NAME
DB_USER
DB_PASSWORD
KC_ADMIN
KC_ADMIN_PASSWORD

## Database Init Notes (Postgres 18)
The compose files mount Postgres data at:
`/var/lib/postgresql`

`init-schemas.sql` grants privileges against `current_database()` so it works with whatever `DB_NAME` is set in `.env`.

If init fails and Postgres gets stuck unhealthy on first boot, reset local data and retry:
- `docker compose -f docker-compose.non-prod.yml down`
- `mv postgres_data postgres_data.failed-init-backup`
- `mkdir -p postgres_data`
- `docker compose -f docker-compose.non-prod.yml up`

## Certificates and TLS (Non-Prod)
By default, setup.py generates self-signed localhost certs under:
`prosody/certs`

Some clients will reject self-signed certs unless explicitly trusted.

## Troubleshooting
`host-unknown` or `This server does not serve 127.0.0.1`:
Use JID/domain `user@localhost` and server `localhost` in non-prod.

`tlsv1 alert unknown ca`:
Your client does not trust the cert. Use mkcert/system trust, or temporary non-prod TLS disable mode in the client.

Keycloak `client_not_found`:
Client `prosody-backend` is missing in realm `chat`. Run bootstrap again.

Keycloak `resolve_required_actions` / `Account is not fully set up`:
User has pending policy constraints (required actions, temporary password, profile constraints). Re-apply user via bootstrap or fix in Keycloak UI.
