-- Step 4: readable views for analysts, and a materialized summary refreshed after each load.
CREATE OR REPLACE VIEW faa.v_aircraft AS
SELECT a.n_number, m.manufacturer, m.model, t.label AS aircraft_type, e.label AS engine_type, a.year_mfr, a.state, a.city,
       r.label AS registrant_type, s.label AS status, s.is_valid, a.cert_issue_date, a.expiration_date, w.label AS weight_class,
       m.seats, m.engines, a.mode_s_hex
  FROM faa.aircraft a
  JOIN faa.aircraft_model m ON m.code = a.model_code
  JOIN faa.aircraft_type t ON t.code = a.aircraft_type
  JOIN faa.engine_type e ON e.code = a.engine_type
  JOIN faa.status s ON s.code = a.status_code
  LEFT JOIN faa.registrant_type r ON r.code = a.registrant_type
  LEFT JOIN faa.weight_class w ON w.code = m.weight_class;

CREATE OR REPLACE VIEW faa.v_expiring_90_days AS
SELECT n_number, manufacturer, model, state, expiration_date
  FROM faa.v_aircraft
 WHERE status = 'Valid registration' AND expiration_date BETWEEN current_date AND current_date + 90;

DROP MATERIALIZED VIEW IF EXISTS faa.mv_fleet_summary;
CREATE MATERIALIZED VIEW faa.mv_fleet_summary AS
SELECT aircraft_type, engine_type, count(*) AS aircraft,
       count(*) FILTER (WHERE is_valid) AS valid,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY year_mfr) AS median_year_built
  FROM faa.v_aircraft
 GROUP BY aircraft_type, engine_type;
CREATE UNIQUE INDEX ON faa.mv_fleet_summary (aircraft_type, engine_type);       -- lets it REFRESH CONCURRENTLY
