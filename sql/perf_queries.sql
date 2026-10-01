-- Questions timed before and after 03_indexes.sql (run.py runs each with EXPLAIN ANALYZE, 5 times, and keeps the median).

-- name: Look up a transponder address seen by an ADS-B receiver
SELECT n_number, model_code, year_mfr FROM faa.aircraft WHERE mode_s_hex = 'A004B3';

-- name: Valid registrations expiring in the next 90 days
SELECT count(*) FROM faa.aircraft WHERE status_code = 'V' AND expiration_date BETWEEN DATE '2026-10-01' AND DATE '2026-12-30';

-- name: Aircraft based in Tampa, Florida
SELECT count(*) FROM faa.aircraft WHERE state = 'FL' AND city = 'TAMPA';

-- name: Models whose name contains 172
SELECT code, manufacturer, model FROM faa.aircraft_model WHERE model ILIKE '%172%';

-- name: Every registered Cessna 172 (join through the model code)
SELECT count(*) FROM faa.aircraft a JOIN faa.aircraft_model m ON m.code = a.model_code
 WHERE m.manufacturer = 'CESSNA' AND m.model LIKE '172%';

-- name: Registration history of one N-number
SELECT count(*) FROM faa.deregistration WHERE n_number = '100';
