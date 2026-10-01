-- Step 6: what the registry says (results written as CSV by run.py with \copy).

-- name: fleet_by_type
SELECT aircraft_type, count(*) AS aircraft, round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY year_mfr)::int AS median_year_built,
       count(*) FILTER (WHERE year_mfr IS NULL) AS year_unknown
  FROM faa.v_aircraft GROUP BY 1 ORDER BY 2 DESC;

-- name: top_models
SELECT manufacturer, model, count(*) AS aircraft, percentile_cont(0.5) WITHIN GROUP (ORDER BY year_mfr)::int AS median_year_built
  FROM faa.v_aircraft GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 15;

-- name: piston_fleet_age
SELECT width_bucket(year_mfr, 1940, 2030, 9) AS bucket, min(year_mfr) AS from_year, max(year_mfr) AS to_year, count(*) AS aircraft
  FROM faa.v_aircraft WHERE aircraft_type = 'Fixed wing single engine' AND engine_type = 'Reciprocating' AND year_mfr IS NOT NULL
 GROUP BY 1 ORDER BY 1;

-- name: expiring_by_month
SELECT date_trunc('month', expiration_date)::date AS month, count(*) AS registrations_expiring
  FROM faa.aircraft WHERE status_code = 'V' AND expiration_date >= DATE '2026-10-01' AND expiration_date < DATE '2028-10-01'
 GROUP BY 1 ORDER BY 1;

-- name: electric_by_weight
SELECT coalesce(weight_class, 'not given') AS weight_class, count(*) AS aircraft
  FROM faa.v_aircraft WHERE engine_type = 'Electric' GROUP BY 1 ORDER BY 2 DESC;

-- name: top_states
SELECT state, count(*) AS aircraft, count(*) FILTER (WHERE is_valid) AS valid
  FROM faa.v_aircraft WHERE state IS NOT NULL GROUP BY 1 ORDER BY 2 DESC LIMIT 10;

-- name: exports_by_country
SELECT export_country, count(*) AS aircraft, min(extract(year FROM cancel_date))::int AS first_year, max(extract(year FROM cancel_date))::int AS last_year
  FROM faa.deregistration WHERE export_country IS NOT NULL AND cancel_date >= DATE '2016-01-01'
 GROUP BY 1 ORDER BY 2 DESC LIMIT 10;

-- name: dereg_by_year
SELECT extract(year FROM cancel_date)::int AS year, count(*) AS deregistered, count(*) FILTER (WHERE export_country IS NOT NULL) AS exported
  FROM faa.deregistration WHERE cancel_date >= DATE '2006-01-01' AND cancel_date < DATE '2026-01-01' GROUP BY 1 ORDER BY 1;
