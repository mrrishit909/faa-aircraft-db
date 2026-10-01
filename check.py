"""The project's check: run after ./run.sh. Fails loudly if a constraint, a permission, the load accounting or the
backup stops working.

    ./venv/bin/python check.py

1. no rows lost: every staging row is in its table; logged issues match an independent pandas count of the CSVs
2. constraints bite: five bad inserts must each be rejected by the right rule (all inside rolled-back transactions)
3. least privilege: the analyst role can read the views but cannot delete, and cannot see raw staging data
4. no personal data columns exist; the backup restored with identical counts; indexes made the selective queries faster
"""
import json
import subprocess
from pathlib import Path

import pandas as pd

import run

HERE = Path(__file__).parent


def q(sql, db="registry"):
    return run.psql("-tA", "-c", sql, db=db).strip()


def rejected(sql, expect, role=None):
    """Run inside BEGIN ... ROLLBACK; psql must fail with the expected error text, so nothing is ever kept."""
    pre = f"SET ROLE {role}; " if role else ""
    r = subprocess.run([str(run.BIN / "psql"), *run.CONN, "-d", "registry", "-v", "ON_ERROR_STOP=1", "-X", "-q",
                        "-c", f"BEGIN; {pre}{sql}; ROLLBACK;"], capture_output=True, text=True)
    assert r.returncode != 0 and expect in r.stderr, (sql, r.stderr)


def main():
    for table, stage in [("aircraft", "master"), ("aircraft_model", "acftref"), ("engine_model", "engine"), ("deregistration", "dereg")]:
        assert q(f"SELECT count(*) FROM faa.{table}") == q(f"SELECT count(*) FROM stage.{stage}"), table

    m = pd.read_csv(HERE / "data" / "clean" / "master.csv", dtype=str, keep_default_na=False)
    d = pd.read_csv(HERE / "data" / "clean" / "dereg.csv", dtype=str, keep_default_na=False)
    a = pd.read_csv(HERE / "data" / "clean" / "acftref.csv", dtype=str, keep_default_na=False)
    issues = pd.read_csv(HERE / "results" / "load_issues.csv").set_index(["table", "column"])["rows"]
    yr = pd.to_numeric(m["year_mfr"].replace("", None))
    assert issues["aircraft", "year_mfr"] == ((yr < 1903) | (yr > 2026)).sum()
    assert issues["deregistration", "model_code"] == ((d["model_code"] != "") & ~d["model_code"].isin(a["code"])).sum()
    assert issues["deregistration", "status_code"] == d["status_code"].isin(["B", "C"]).sum()
    assert issues["aircraft", "certification"] == ((m["certification"] != "") & ~m["certification"].str[0].isin(list("123456789"))).sum()

    good = q("SELECT row_to_json(a) FROM faa.aircraft a WHERE n_number = '100'")
    assert q("SELECT count(*) FROM faa.aircraft WHERE n_number IN ('9ZZZZ', '9ZZZY', '9ZZZX', '9ZZZW')") == "0"   # test keys unused
    base = ("INSERT INTO faa.aircraft (n_number, serial_number, model_code, last_action_date, aircraft_type, engine_type, status_code,"
            " unique_id, mode_s_hex, year_mfr, cert_issue_date, expiration_date) VALUES ")
    rejected(base + "('0ABC', 'X', '7100510', '2026-01-01', '4', 1, 'V', 99999991, NULL, NULL, NULL, NULL)", "aircraft_n_number_check")
    rejected(base + "('9ZZZZ', 'X', 'NOSUCH1', '2026-01-01', '4', 1, 'V', 99999992, NULL, NULL, NULL, NULL)", "aircraft_model_code_fkey")
    rejected(base + "('9ZZZY', 'X', '7100510', '2026-01-01', '4', 1, 'V', 99999993, 'A004B3', NULL, NULL, NULL)", "aircraft_mode_s_hex_key")
    rejected(base + "('9ZZZX', 'X', '7100510', '2026-01-01', '4', 1, 'V', 99999994, NULL, 1850, NULL, NULL)", "aircraft_year_mfr_check")
    rejected(base + "('9ZZZW', 'X', '7100510', '2026-01-01', '4', 1, 'V', 99999995, NULL, NULL, '2026-01-01', '2020-01-01')", "aircraft_check")
    assert q("SELECT row_to_json(a) FROM faa.aircraft a WHERE n_number = '100'") == good

    assert int(q("SET ROLE registry_analyst; SELECT count(*) FROM faa.v_aircraft")) == int(q("SELECT count(*) FROM faa.aircraft"))
    rejected("DELETE FROM faa.aircraft WHERE n_number = '100'", "permission denied", role="registry_analyst")
    rejected("SELECT count(*) FROM stage.master", "permission denied", role="registry_analyst")
    assert q("SELECT count(*) FROM faa.aircraft a WHERE NOT EXISTS (SELECT 1 FROM faa.aircraft_model m WHERE m.code = a.model_code)") == "0"

    cols = set(q("SELECT string_agg(column_name, ',') FROM information_schema.columns WHERE table_schema IN ('faa', 'stage')").split(","))
    personal = {"name", "registrant_name", "street", "street2", "zip_code", "zip", "county", "other_names_1"}
    assert not cols & personal and not any(c.startswith(("street", "other_name")) for c in cols), "personal-data columns must not exist"
    assert "registrant_name" not in m.columns and "street" not in m.columns
    s = json.loads((HERE / "results" / "summary.json").read_text())
    assert s["backup"]["restored_counts_match"]
    perf = json.loads((HERE / "results" / "performance.json").read_text())
    for p in perf[1:]:
        assert p["after_ms"] < p["before_ms"] and "Seq Scan" not in p["after_scans"], p["question"]
    print(f"OK: no rows lost ({s['rows']['aircraft']:,} aircraft); logged issues match pandas; 5 bad inserts rejected by the right "
          f"constraint; analyst can read but not delete or see staging; no personal-data columns; backup restored identically; "
          f"indexes used for {len(perf) - 1} of {len(perf)} questions (the first was already indexed by its UNIQUE constraint)")


if __name__ == "__main__":
    main()
