#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
    -- Create isolated schemas
    CREATE SCHEMA IF NOT EXISTS keycloak_schema;
    CREATE SCHEMA IF NOT EXISTS prosody_schema;

    -- Create service accounts if missing
    DO \$\$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${KC_DB_USER}') THEN
            CREATE ROLE ${KC_DB_USER} LOGIN PASSWORD '${KC_DB_PASSWORD}';
        END IF;

        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${PROSODY_DB_USER}') THEN
            CREATE ROLE ${PROSODY_DB_USER} LOGIN PASSWORD '${PROSODY_DB_PASSWORD}';
        END IF;
    END
    \$\$;

    -- Assign ownership
    ALTER SCHEMA keycloak_schema OWNER TO ${KC_DB_USER};
    ALTER SCHEMA prosody_schema OWNER TO ${PROSODY_DB_USER};

    -- Global DB permissions
    DO \$\$
    DECLARE
        db_name text := current_database();
    BEGIN
        EXECUTE format('GRANT ALL PRIVILEGES ON DATABASE %I TO ${KC_DB_USER}', db_name);
        EXECUTE format('GRANT ALL PRIVILEGES ON DATABASE %I TO ${PROSODY_DB_USER}', db_name);
    END
    \$\$;

    -- Set default search path per user
    ALTER ROLE ${KC_DB_USER} SET search_path TO keycloak_schema;
    ALTER ROLE ${PROSODY_DB_USER} SET search_path TO prosody_schema;
EOSQL
