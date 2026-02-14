# Merveilles XMPP Stack

Prosody + Keycloak + Postgres.

This repo runs a chat stack with:
- `prosodyim/prosody:0.12`
- `keycloak/keycloak:26.5`
- `postgres:18-alpine`
- `nginx:1-alpine` as the edge proxy

## What's here now

The old top-level compose files are gone.

Compose is split by service:
- `compose/db/docker-compose.yml`
- `compose/idp/docker-compose.yml`
- `compose/xmpp/docker-compose.yml`
- `compose/proxy/docker-compose.yml`

Prosody config is now one file:
- `prosody/config/prosody.cfg.lua`

Behavior is driven by env values (`env/*.env`), not by seperate prosody configs anymore

## Prereqs

- Docker + Docker Compose
- `openssl`
- `python3`
- `hg` (needed only if you sync community prosody modules)

## Env Files

Copy examples once:

```bash
cp env/stack.env.example env/stack.env
cp env/db.env.example env/db.env
cp env/idp.env.example env/idp.env
cp env/xmpp.env.example env/xmpp.env
cp env/proxy.env.example env/proxy.env
```

Then fill secrets:

```bash
bash scripts/secure.sh
```

## Quick Start (Dev)

One command path:

```bash
bash scripts/deploy.sh dev
```

This runs setup, validation, compose up, health checks, and Keycloak bootstrap.

Useful checks:

```bash
bash scripts/compose-up.sh status
curl -k https://sso.localhost/realms/community/.well-known/openid-configuration
```

Create a test user:

```bash
python3 scripts/bootstrap-keycloak.py --user testuser --password changeme
```

XMPP client values:

```text
JID/domain: testuser@localhost
Server: localhost
Port: 5222
```

Use `localhost`, not `127.0.0.1`, for XMPP domain/JID.

## Production

```bash
bash scripts/deploy.sh prod example.com
```

If cert issuance fails during deploy, fix DNS/ports and run:

```bash
bash scripts/init-certs.sh
```

Renewal helper:

```bash
bash scripts/renew-certs.sh
```

## Scripts

- `scripts/deploy.sh` full deploy flow
- `scripts/compose-up.sh` up/down/restart/status
- `scripts/setup.py` create dirs/env files, set domain, cert setup
- `scripts/validate.sh` env/config sanity checks
- `scripts/bootstrap-keycloak.py` realm/clients/user setup
- `scripts/init-certs.sh` first cert request
- `scripts/sync-certs.sh` copy LE certs into Prosody cert volume
- `scripts/renew-certs.sh` renew + reload + sync

## Troubleshooting

`host-unknown` or `server does not serve 127.0.0.1`:
- use JID/domain `user@localhost` and server `localhost`

`tlsv1 alert unknown ca`:
- your client does not trust the cert yet

Keycloak `client_not_found`:
- run `python3 scripts/bootstrap-keycloak.py` again

Health checks timeout:
- run `bash scripts/compose-up.sh status`
- then `docker logs chat-idp` / `docker logs chat-server`
