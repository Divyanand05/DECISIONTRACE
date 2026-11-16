-- =============================================================================
-- Run this script as the postgres superuser in pgAdmin Query Tool
-- (or psql -U postgres -f scripts/setup_database.sql)
--
-- Creates the dtuser role and decisiontrace database.
-- =============================================================================

-- 1. Create the application role
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'dtuser') THEN
        CREATE ROLE dtuser WITH LOGIN PASSWORD 'dtpassword';
        RAISE NOTICE 'Role dtuser created.';
    ELSE
        -- Update password in case it changed
        ALTER ROLE dtuser WITH PASSWORD 'dtpassword';
        RAISE NOTICE 'Role dtuser already exists — password reset.';
    END IF;
END
$$;

-- 2. Create the database (must run outside a transaction block in pgAdmin)
-- If it already exists this will error; that is safe to ignore.
SELECT 'Run the next line manually if the database does not exist yet:' AS instruction;
SELECT 'CREATE DATABASE decisiontrace OWNER dtuser;' AS sql_to_run;

-- 3. Grant connect
GRANT CONNECT ON DATABASE decisiontrace TO dtuser;
