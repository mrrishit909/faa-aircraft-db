-- Step 3: indexes for the questions people actually ask. run.py times each query before and after (EXPLAIN ANALYZE).
-- PostgreSQL indexes PRIMARY KEY and UNIQUE columns automatically, but NOT foreign-key columns.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX aircraft_model_code_idx   ON faa.aircraft (model_code);                                  -- joins to the model table
CREATE INDEX aircraft_state_city_idx   ON faa.aircraft (state, city);                                 -- "aircraft based in Tampa, FL"
CREATE INDEX aircraft_expiring_idx     ON faa.aircraft (expiration_date) WHERE status_code = 'V';     -- partial: valid registrations only
CREATE INDEX aircraft_model_name_trgm  ON faa.aircraft_model USING gin (model gin_trgm_ops);         -- "model contains 172"
CREATE INDEX deregistration_n_idx      ON faa.deregistration (n_number);                              -- an N-number's history
ANALYZE faa.aircraft, faa.aircraft_model, faa.deregistration;
