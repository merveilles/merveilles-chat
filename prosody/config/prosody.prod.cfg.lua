-- ===================================================================
-- PROSODY CONFIG - PRODUCTION (Let's Encrypt / OIDC)
-- ===================================================================

local domain = os.getenv("DOMAIN")
local admin_jid = os.getenv("PROSODY_ADMIN_JID")

admins = { admin_jid }
plugin_paths = { "/usr/lib/prosody/modules-community" }

-- Logging: Clean output for production
log = {
    { levels = { min = "info" }, to = "console" };
}

-- Network settings
interfaces = { "*" }

-- Enforce Encryption
c2s_require_encryption = true
allow_unencrypted_plain_auth = false

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
    
    -- messaging
    "pep";               -- OMEMO support
    "carbons";           -- Multi-device sync
    "mam";               -- Chat history (Postgres)
    "blocking";          -- User blocking
    "csi";               -- Mobile battery optimization
    
    -- Media/Auth
    "auth_oauth_external"; -- Keycloak Bridge
    "http_file_share";     -- File uploads
}

-- OIDC Bridge Settings
-- Uses the internal Docker network hostname 'chat-idp'
authentication = "oauth_external"
oauth_external_token_endpoint = "http://chat-idp:8080/realms/chat/protocol/openid-connect/token"
oauth_external_client_id = "prosody-backend"
oauth_external_client_secret = os.getenv("PROSODY_OAUTH_SECRET")
oauth_external_scope = "profile"

-- Database configuration
storage = "sql"
sql = {
    driver = "PostgreSQL";
    database = os.getenv("DB_NAME");
    username = os.getenv("DB_USER");
    password = os.getenv("DB_PASSWORD");
    host = "chat-db";
}

-- Virtual Host setup
-- The paths here must match your Docker volume mounts
VirtualHost (domain)
    ssl = {
        key = "/etc/prosody/certs/" .. domain .. ".key";
        certificate = "/etc/prosody/certs/" .. domain .. ".crt";
    }

Component ("conference." .. domain) "muc"
    name = "Community Chatrooms"
    restrict_room_creation = "local"