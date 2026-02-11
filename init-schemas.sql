-- Create the isolated workspaces
CREATE SCHEMA IF NOT EXISTS keycloak_schema;
CREATE SCHEMA IF NOT EXISTS prosody_schema;

-- Create service accounts if missing
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'keycloak_user') THEN
        CREATE ROLE keycloak_user LOGIN PASSWORD 'keycloak_pass';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'prosody_user') THEN
        CREATE ROLE prosody_user LOGIN PASSWORD 'prosody_pass';
    END IF;
END
$$;

-- Assign Ownership 
ALTER SCHEMA keycloak_schema OWNER TO keycloak_user;
ALTER SCHEMA prosody_schema OWNER TO prosody_user;

-- Global DB Permissions
DO $$
DECLARE
    db_name text := current_database();
BEGIN
    EXECUTE format('GRANT ALL PRIVILEGES ON DATABASE %I TO keycloak_user', db_name);
    EXECUTE format('GRANT ALL PRIVILEGES ON DATABASE %I TO prosody_user', db_name);
END
$$;

-- Set the Default "Home" for each user
-- So that using 'SELECT * FROM table' looks in the right schema automatically
ALTER ROLE keycloak_user SET search_path TO keycloak_schema;
ALTER ROLE prosody_user SET search_path TO prosody_schema;
