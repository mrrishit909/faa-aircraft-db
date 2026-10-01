-- Step 5: least privilege. Analysts read; only the loader writes; nobody else sees the schema.
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'registry_analyst') THEN CREATE ROLE registry_analyst NOLOGIN; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'registry_loader')  THEN CREATE ROLE registry_loader  NOLOGIN; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analyst1') THEN CREATE ROLE analyst1 LOGIN IN ROLE registry_analyst; END IF;
END $$;
REVOKE ALL ON SCHEMA faa FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA faa FROM PUBLIC;
GRANT USAGE ON SCHEMA faa TO registry_analyst, registry_loader;
GRANT SELECT ON ALL TABLES IN SCHEMA faa TO registry_analyst;                 -- tables, views and the materialized view
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA faa TO registry_loader;
REVOKE ALL ON SCHEMA stage FROM PUBLIC;                                       -- raw staging data stays with the owner
