-- PROSODY CONFIG - NON-PROD (LOCALHOST DEV)

-- Variables pulled from .env via Docker environment
local domain = os.getenv("DOMAIN") or "localhost"
local admin_jid = os.getenv("PROSODY_ADMIN_JID") or "admin@localhost"

admins = { admin_jid }
plugin_paths = { "/usr/lib/prosody/modules-community" }

-- Console output for Docker troubleshooting
log = {
    { levels = { min = "debug" }, to = "console" };
}

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

-- Authentication Settings
authentication = "oauth_external"
interfaces = { "*" }

-- Bypass encryption for local testing/debugging
c2s_require_encryption = false
allow_unencrypted_plain_auth = true

-- Keycloak connection/ODIC Bridge Settings
-- Uses the internal Docker network hostname 'chat-idp'
oauth_external_token_endpoint = "http://chat-idp:8080/realms/chat/protocol/openid-connect/token"
oauth_external_client_id = "prosody-backend"
oauth_external_client_secret = os.getenv("PROSODY_OAUTH_SECRET")
oauth_external_scope = "openid profile"

-- Database configuration
-- matches .env values randomized by secure.sh
storage = "sql" 
sql = {
    driver = "PostgreSQL"; 
    database = os.getenv("DB_NAME") or "keycloak";
    username = os.getenv("DB_USER") or "prosody_user";
    password = os.getenv("DB_PASSWORD");
    host = "chat-db";
    port = 5432;
}

-- Virtual Host setup
VirtualHost (domain)
    ssl = { 
        key = "/etc/prosody/certs/localhost.key"; 
        certificate = "/etc/prosody/certs/localhost.crt"; 
    }

Component ("conference." .. domain) "muc"
    name = "Dev Chatrooms"
    restrict_room_creation = "local"