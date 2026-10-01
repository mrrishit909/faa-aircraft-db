-- Step 2b: load. Raw text goes into a staging schema, then typed, validated rows go into faa.*.
-- Anything changed or dropped is logged in faa.load_issue first. Run from the project folder: psql -f sql/02_load.sql
DROP SCHEMA IF EXISTS stage CASCADE;
CREATE SCHEMA stage;
CREATE TABLE stage.master (n_number text, serial_number text, model_code text, engine_code text, year_mfr text, registrant_type text,
  city text, state text, region text, country text, last_action_date text, cert_issue_date text, certification text, aircraft_type text,
  engine_type text, status_code text, mode_s_hex text, fractional text, airworthiness_date text, expiration_date text, unique_id text,
  kit_mfr text, kit_model text);
CREATE TABLE stage.acftref (code text, manufacturer text, model text, aircraft_type text, engine_type text, category text,
  builder_cert text, engines text, seats text, weight_class text, cruise_mph text, tc_data_sheet text, tc_holder text);
CREATE TABLE stage.engine (code text, manufacturer text, model text, engine_type text, horsepower text, thrust_lb text);
CREATE TABLE stage.dereg (n_number text, serial_number text, model_code text, status_code text, year_mfr text, cancel_date text,
  export_country text, mode_s_hex text);
\copy stage.master  FROM 'data/clean/master.csv'  WITH (FORMAT csv, HEADER true)
\copy stage.acftref FROM 'data/clean/acftref.csv' WITH (FORMAT csv, HEADER true)
\copy stage.engine  FROM 'data/clean/engine.csv'  WITH (FORMAT csv, HEADER true)
\copy stage.dereg   FROM 'data/clean/dereg.csv'   WITH (FORMAT csv, HEADER true)

-- A date cast that returns NULL instead of aborting the whole load on one bad value.
CREATE OR REPLACE FUNCTION stage.try_date(x text) RETURNS date LANGUAGE plpgsql IMMUTABLE AS $$
BEGIN
  IF x IS NULL OR x = '' THEN RETURN NULL; END IF;
  RETURN to_date(x, 'YYYYMMDD');
EXCEPTION WHEN others THEN RETURN NULL;
END $$;

-- ---------- log what will change ----------
INSERT INTO faa.load_issue (table_name, record_key, column_name, bad_value, action)
SELECT 'engine_model', code, 'engine_type', engine_type, 'blank engine type: set to 9 (Unknown)' FROM stage.engine WHERE engine_type IS NULL
UNION ALL
SELECT 'aircraft', n_number, 'year_mfr', year_mfr, 'outside 1903-2026: set to NULL'
  FROM stage.master WHERE year_mfr <> '' AND year_mfr::int NOT BETWEEN 1903 AND 2026
UNION ALL
SELECT 'aircraft', n_number, 'certification', certification, 'class not in data dictionary: set to NULL'
  FROM stage.master WHERE certification <> '' AND left(certification, 1) NOT IN (SELECT code FROM faa.airworthiness_class)
UNION ALL
SELECT 'aircraft', n_number, c.col, c.val, 'not a valid date: set to NULL'
  FROM stage.master m CROSS JOIN LATERAL (VALUES ('cert_issue_date', m.cert_issue_date), ('airworthiness_date', m.airworthiness_date),
       ('expiration_date', m.expiration_date), ('last_action_date', m.last_action_date)) c(col, val)
 WHERE c.val <> '' AND stage.try_date(c.val) IS NULL
UNION ALL
SELECT 'aircraft', m.n_number, 'aircraft_type', m.aircraft_type || ' vs model ' || r.aircraft_type, 'differs from the model reference: kept as registered'
  FROM stage.master m JOIN stage.acftref r ON r.code = m.model_code WHERE m.aircraft_type <> r.aircraft_type
UNION ALL
SELECT 'deregistration', n_number, 'model_code', model_code, 'not in aircraft model reference: set to NULL'
  FROM stage.dereg WHERE model_code <> '' AND model_code NOT IN (SELECT code FROM stage.acftref)
UNION ALL
SELECT 'deregistration', n_number, 'year_mfr', year_mfr, 'outside 1903-2026: set to NULL'
  FROM stage.dereg WHERE year_mfr ~ '^[0-9]{4}$' AND year_mfr::int NOT BETWEEN 1903 AND 2026
UNION ALL
SELECT 'deregistration', n_number, 'status_code', status_code, 'not in data dictionary: set to NULL'
  FROM stage.dereg WHERE status_code <> '' AND status_code NOT IN (SELECT code FROM faa.status);

-- ---------- typed inserts ----------
INSERT INTO faa.engine_model
SELECT code, manufacturer, model, COALESCE(NULLIF(engine_type, '')::smallint, 9),
       NULLIF(horsepower::int, 0), NULLIF(thrust_lb::int, 0)            -- 0 means "not applicable to this engine type"
  FROM stage.engine;

INSERT INTO faa.aircraft_model
SELECT code, manufacturer, model, aircraft_type, engine_type::smallint, NULLIF(category, '')::smallint,
       NULLIF(builder_cert, '')::smallint, NULLIF(engines, '')::smallint, NULLIF(seats, '')::smallint, NULLIF(weight_class, ''),
       NULLIF(cruise_mph::int, 0), NULLIF(tc_data_sheet, ''), NULLIF(tc_holder, '')
  FROM stage.acftref;

INSERT INTO faa.aircraft
SELECT n_number, serial_number, model_code, NULLIF(engine_code, ''),
       CASE WHEN year_mfr <> '' AND year_mfr::int BETWEEN 1903 AND 2026 THEN year_mfr::smallint END,
       NULLIF(registrant_type, ''), NULLIF(city, ''), NULLIF(state, ''), NULLIF(region, ''), NULLIF(country, ''),
       stage.try_date(last_action_date), stage.try_date(cert_issue_date),
       CASE WHEN left(certification, 1) IN (SELECT code FROM faa.airworthiness_class) THEN left(certification, 1) END,
       NULLIF(substr(certification, 2), ''),
       aircraft_type, engine_type::smallint, status_code, NULLIF(mode_s_hex, ''), COALESCE(fractional = 'Y', false),   -- COPY reads an empty field as NULL
       stage.try_date(airworthiness_date), stage.try_date(expiration_date), unique_id::int, NULLIF(kit_mfr, ''), NULLIF(kit_model, '')
  FROM stage.master;

INSERT INTO faa.deregistration (n_number, serial_number, model_code, status_code, year_mfr, cancel_date, export_country, mode_s_hex)
SELECT n_number, NULLIF(serial_number, ''),
       CASE WHEN model_code IN (SELECT code FROM stage.acftref) THEN model_code END,
       CASE WHEN status_code IN (SELECT code FROM faa.status) THEN status_code END,
       CASE WHEN year_mfr ~ '^[0-9]{4}$' AND year_mfr::int BETWEEN 1903 AND 2026 THEN year_mfr::smallint END,
       stage.try_date(cancel_date), NULLIF(export_country, ''), NULLIF(mode_s_hex, '')
  FROM stage.dereg;

ANALYZE faa.engine_model, faa.aircraft_model, faa.aircraft, faa.deregistration;
