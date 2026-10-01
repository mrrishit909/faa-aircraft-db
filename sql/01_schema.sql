-- Step 2a: schema. Lookup tables hold the FAA data dictionary's codes (ardata.pdf, 8 May 2025), so every code in the
-- registry is checked by a foreign key instead of trusted.
DROP SCHEMA IF EXISTS faa CASCADE;
CREATE SCHEMA faa;

CREATE TABLE faa.registrant_type (code text PRIMARY KEY, label text NOT NULL);
INSERT INTO faa.registrant_type VALUES ('1','Individual'),('2','Partnership'),('3','Corporation'),('4','Co-owned'),
  ('5','Government'),('7','LLC'),('8','Non-citizen corporation'),('9','Non-citizen co-owned');

CREATE TABLE faa.aircraft_type (code text PRIMARY KEY, label text NOT NULL);
INSERT INTO faa.aircraft_type VALUES ('1','Glider'),('2','Balloon'),('3','Blimp/dirigible'),('4','Fixed wing single engine'),
  ('5','Fixed wing multi engine'),('6','Rotorcraft'),('7','Weight-shift-control'),('8','Powered parachute'),('9','Gyroplane'),
  ('H','Hybrid lift'),('O','Other');

CREATE TABLE faa.engine_type (code smallint PRIMARY KEY, label text NOT NULL);
INSERT INTO faa.engine_type VALUES (0,'None'),(1,'Reciprocating'),(2,'Turbo-prop'),(3,'Turbo-shaft'),(4,'Turbo-jet'),
  (5,'Turbo-fan'),(6,'Ramjet'),(7,'2 cycle'),(8,'4 cycle'),(9,'Unknown'),(10,'Electric'),(11,'Rotary');

CREATE TABLE faa.airworthiness_class (code text PRIMARY KEY, label text NOT NULL);
INSERT INTO faa.airworthiness_class VALUES ('1','Standard'),('2','Limited'),('3','Restricted'),('4','Experimental'),
  ('5','Provisional'),('6','Multiple'),('7','Primary'),('8','Special flight permit'),('9','Light sport');

CREATE TABLE faa.region (code text PRIMARY KEY, label text NOT NULL);
INSERT INTO faa.region VALUES ('1','Eastern'),('2','Southwestern'),('3','Central'),('4','Western-Pacific'),('5','Alaskan'),
  ('7','Southern'),('8','European'),('C','Great Lakes'),('E','New England'),('S','Northwest Mountain');

CREATE TABLE faa.weight_class (code text PRIMARY KEY, label text NOT NULL);
INSERT INTO faa.weight_class VALUES ('CLASS 1','Up to 12,499 lb'),('CLASS 2','12,500-19,999 lb'),('CLASS 3','20,000 lb and over'),
  ('CLASS 4','UAV up to 55 lb');

CREATE TABLE faa.status (code text PRIMARY KEY, label text NOT NULL, is_valid boolean NOT NULL);
INSERT INTO faa.status VALUES
  ('A','Triennial form mailed, not returned',false),('D','Expired dealer',false),('E','Revoked by enforcement action',false),
  ('M','Valid - assigned to manufacturer (dealer certificate)',true),('N','Non-citizen corporation, flight hour reports missing',false),
  ('R','Registration pending',false),('S','Second triennial form mailed, not returned',false),('T','Valid - trainee',true),
  ('V','Valid registration',true),('W','Ineffective or invalid',false),('X','Enforcement letter',false),('Z','Permanent reserved',false),
  ('1','Triennial form returned undeliverable',false),('2','N-number assigned, not registered',false),
  ('3','N-number assigned (non type certificated), not registered',false),('4','N-number assigned (import), not registered',false),
  ('5','Reserved N-number',false),('6','Administratively canceled',false),('7','Sale reported',false),
  ('8','Second triennial mailing, no response',false),('9','Registration revoked',false),('10','Assigned, pending cancellation',false),
  ('11','Assigned (amateur), pending cancellation',false),('12','Assigned (import), pending cancellation',false),
  ('13','Registration expired',false),('14','First re-registration notice',false),('15','Second re-registration notice',false),
  ('16','Expired, pending cancellation',false),('17','Sale reported, pending cancellation',false),('18','Sale reported, canceled',false),
  ('19','Registration pending, pending cancellation',false),('20','Registration pending, canceled',false),
  ('21','Revoked, pending cancellation',false),('22','Revoked, canceled',false),('23','Expired dealer, pending cancellation',false),
  ('24','Third re-registration notice',false),('25','First renewal notice',false),('26','Second renewal notice',false),
  ('27','Registration expired',false),('28','Third renewal notice',false),('29','Expired, pending cancellation',false);

CREATE TABLE faa.engine_model (
  code        char(5) PRIMARY KEY,
  manufacturer text NOT NULL,
  model       text NOT NULL,
  engine_type smallint NOT NULL REFERENCES faa.engine_type,
  horsepower  integer CHECK (horsepower >= 0),
  thrust_lb   integer CHECK (thrust_lb >= 0)
);

CREATE TABLE faa.aircraft_model (
  code          char(7) PRIMARY KEY,
  manufacturer  text NOT NULL,
  model         text NOT NULL,
  aircraft_type text NOT NULL REFERENCES faa.aircraft_type,
  engine_type   smallint NOT NULL REFERENCES faa.engine_type,
  category      smallint CHECK (category IN (1, 2, 3)),            -- land, sea, amphibian
  builder_cert  smallint CHECK (builder_cert IN (0, 1, 2)),        -- type certificated, not, light sport
  engines       smallint CHECK (engines BETWEEN 0 AND 99),       -- electric multi-rotor designs list up to 80 motors
  seats         smallint CHECK (seats BETWEEN 0 AND 1000),
  weight_class  text REFERENCES faa.weight_class,
  cruise_mph    smallint CHECK (cruise_mph >= 0),
  tc_data_sheet text,
  tc_holder     text
);

CREATE TABLE faa.aircraft (
  n_number            varchar(5) PRIMARY KEY CHECK (n_number ~ '^[1-9][0-9A-HJ-NP-Z]{0,4}$'),   -- no letters I or O
  serial_number       text NOT NULL,
  model_code          char(7) NOT NULL REFERENCES faa.aircraft_model,
  engine_code         char(5) REFERENCES faa.engine_model,
  year_mfr            smallint CHECK (year_mfr BETWEEN 1903 AND 2026),
  registrant_type     text REFERENCES faa.registrant_type,
  city                text,
  state               char(2),
  region              text REFERENCES faa.region,
  country             char(2),
  last_action_date    date NOT NULL,
  cert_issue_date     date,
  airworthiness_class text REFERENCES faa.airworthiness_class,
  approved_operations text,
  aircraft_type       text NOT NULL REFERENCES faa.aircraft_type,
  engine_type         smallint NOT NULL REFERENCES faa.engine_type,
  status_code         text NOT NULL REFERENCES faa.status,
  mode_s_hex          char(6) UNIQUE CHECK (mode_s_hex ~ '^[0-9A-F]{6}$'),      -- the transponder address ADS-B receivers see
  fractional          boolean NOT NULL DEFAULT false,
  airworthiness_date  date,
  expiration_date     date,
  unique_id           integer NOT NULL UNIQUE,
  kit_mfr             text,
  kit_model           text,
  CHECK (expiration_date IS NULL OR cert_issue_date IS NULL OR expiration_date >= cert_issue_date)
);

-- An N-number can be registered and cancelled many times over the decades, so history needs its own key.
CREATE TABLE faa.deregistration (
  dereg_id       bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  n_number       varchar(5) NOT NULL,
  serial_number  text,
  model_code     char(7) REFERENCES faa.aircraft_model,
  status_code    text REFERENCES faa.status,
  year_mfr       smallint CHECK (year_mfr BETWEEN 1903 AND 2026),
  cancel_date    date,
  export_country text,
  mode_s_hex     char(6)
);

-- Every value the load had to change or drop is written here, so nothing is silently lost.
CREATE TABLE faa.load_issue (
  issue_id   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  table_name text NOT NULL,
  record_key text NOT NULL,
  column_name text NOT NULL,
  bad_value  text,
  action     text NOT NULL
);
