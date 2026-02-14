-- Unified Prosody configuration
-- All environment-specific behavior is driven by env vars.

local domain = os.getenv("DOMAIN") or "localhost"
local admin_jid = os.getenv("PROSODY_ADMIN_JID") or ("admin@" .. domain)
local kc_realm = os.getenv("KC_REALM") or "community"
local db_host = os.getenv("DB_HOST") or "chat-db"
local db_port = tonumber(os.getenv("DB_PORT")) or 5432
local log_level = os.getenv("PROSODY_LOG_LEVEL") or "info"
local require_encryption = os.getenv("PROSODY_REQUIRE_ENCRYPTION") ~= "false"

-- File share limits, can be overriden in env.
local file_size_limit = tonumber(os.getenv("PROSODY_FILE_SIZE_LIMIT")) or (16 * 1024 * 1024)
local file_expiry = tonumber(os.getenv("PROSODY_FILE_EXPIRY")) or (7 * 24 * 60 * 60)
local file_daily_quota = tonumber(os.getenv("PROSODY_FILE_DAILY_QUOTA")) or (100 * 1024 * 1024)
local file_global_quota = tonumber(os.getenv("PROSODY_FILE_GLOBAL_QUOTA")) or (10 * 1024 * 1024 * 1024)

admins = { admin_jid }
plugin_paths = { "/usr/lib/prosody/modules-community" }

log = {
    { levels = { min = log_level }, to = "console" };
}

interfaces = { "*" }
c2s_require_encryption = require_encryption
allow_unencrypted_plain_auth = not require_encryption

-- https://modules.prosody.im/
modules_enabled = {
    "roster";            -- Contact lists
    "saslauth";          -- Authentication handshake
    "tls";               -- Encryption
    "dialback";          -- S2S verification
    "disco";             -- Service discovery
    "private";           -- Legacy XML storage

    -- Identity/Profiles
    "vcard4";            -- Profiles/Avatars
    "version";           -- Server version
    "uptime";            -- Server uptime
    "time";              -- Time sync
    "ping";              -- Keep-alive
    "register";          -- Account mechanics

    -- Messaging
    "pep";               -- OMEMO support
    "carbons";           -- Multi-device sync
    "mam";               -- Chat history (Postgres)
    "blocking";          -- User blocking
    "csi";               -- Mobile battery optimization

    -- Media/Auth
    "auth_oauth_external"; -- Keycloak Bridge
    "http_file_share";     -- File uploads
}

-- https://prosody.im/doc/authentication
authentication = "oauth_external"
-- https://modules.prosody.im/mod_auth_oauth_external
oauth_external_token_endpoint = "http://chat-idp:8080/realms/" .. kc_realm .. "/protocol/openid-connect/token"
oauth_external_client_id = "prosody-backend"
oauth_external_client_secret = os.getenv("PROSODY_OAUTH_SECRET")
oauth_external_scope = "openid profile"

-- https://prosody.im/doc/modules/mod_http_file_share
http_file_share_size_limit = file_size_limit
http_file_share_expires_after = file_expiry
http_file_share_daily_quota = file_daily_quota
http_file_share_global_quota = file_global_quota

-- https://prosody.im/doc/modules/mod_storage_sql
storage = "sql"
sql = {
    driver = "PostgreSQL";
    database = os.getenv("DB_NAME") or "keycloak";
    username = os.getenv("DB_USER") or "prosody_user";
    password = os.getenv("DB_PASSWORD");
    host = db_host;
    port = db_port;
}

VirtualHost (domain)
    ssl = {
        key = "/etc/prosody/certs/" .. domain .. ".key";
        certificate = "/etc/prosody/certs/" .. domain .. ".crt";
    }

Component ("conference." .. domain) "muc"
    name = "Community Chatrooms"
    restrict_room_creation = "local"
