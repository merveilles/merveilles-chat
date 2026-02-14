# Env files

Each service has its own env file:

- `env/stack.env`
- `env/db.env`
- `env/idp.env`
- `env/xmpp.env`
- `env/proxy.env`

If they don't exist yet:

```bash
cp env/stack.env.example env/stack.env
cp env/db.env.example env/db.env
cp env/idp.env.example env/idp.env
cp env/xmpp.env.example env/xmpp.env
cp env/proxy.env.example env/proxy.env
```

## SOPS

Do not commit raw `env/*.env` files.

Decrypt:

```bash
./scripts/env-decrypt.sh
```

Edit locally, then encrypt again:

```bash
export SOPS_AGE_RECIPIENTS='age1...'
./scripts/env-encrypt.sh
```

Encrypted files go to `env/encrypted/*.enc`.
