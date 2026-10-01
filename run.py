"""Run every step against the project's private PostgreSQL (start it with ./run.sh).

    ./run.sh        # = start the cluster if needed, then ./venv/bin/python run.py

1. rebuild the database: schema + logged load      4. views, materialized view, roles
2. time six real questions (EXPLAIN ANALYZE)        5. insight queries -> results/*.csv
3. add indexes, time them again                     6. back up with pg_dump, restore into a fresh database, compare
"""
import json
import os
import re
import subprocess
import time
from pathlib import Path

HERE = Path(__file__).parent
BIN = Path(os.environ.get("PG", Path.home() / "micromamba" / "envs" / "analyst" / "bin"))
CONN = ["-h", str(HERE / "data"), "-p", "5433", "-U", "postgres"]
OUT = HERE / "results"


def psql(*args, db="registry", capture=True):
    r = subprocess.run([str(BIN / "psql"), *CONN, "-d", db, "-v", "ON_ERROR_STOP=1", "-q", "-X", *args],
                       cwd=HERE, capture_output=capture, text=True)
    if r.returncode:
        raise RuntimeError(r.stderr)
    return r.stdout


def blocks(path):
    """Split a .sql file into (name, statement) pairs at its '-- name:' lines."""
    text = (HERE / path).read_text()
    return [(m.group(1).strip(), m.group(2).strip().rstrip(";")) for m in re.finditer(r"-- name: ([^\n]+)\n(.*?)(?=\n-- name:|\Z)", text, re.S)]


def timed(sql, runs=5):
    psql("-c", sql)                                                    # warm the cache once
    times, plan = [], None
    for _ in range(runs):
        out = psql("-tA", "-c", f"EXPLAIN (ANALYZE, FORMAT JSON) {sql}")
        j = json.loads(out)[0]
        times.append(j["Execution Time"])
        plan = j["Plan"]
    scans = sorted({n["Node Type"] for n in walk(plan) if "Scan" in n["Node Type"]})
    return sorted(times)[len(times) // 2], scans


def walk(node):
    yield node
    for child in node.get("Plans", []):
        yield from walk(child)


def main():
    OUT.mkdir(exist_ok=True)
    psql("-c", "DROP DATABASE IF EXISTS registry", db="postgres")
    psql("-c", "CREATE DATABASE registry", db="postgres")
    t0 = time.time()
    psql("-f", "sql/01_schema.sql", "-f", "sql/02_load.sql")
    load_seconds = time.time() - t0

    queries = blocks("sql/perf_queries.sql")
    before = [timed(sql) for _, sql in queries]
    psql("-f", "sql/03_indexes.sql")
    after = [timed(sql) for _, sql in queries]
    perf = [{"question": name, "before_ms": b[0], "before_scans": b[1], "after_ms": a[0], "after_scans": a[1]}
            for (name, _), b, a in zip(queries, before, after)]
    (OUT / "performance.json").write_text(json.dumps(perf, indent=2) + "\n")

    psql("-f", "sql/04_views.sql", "-f", "sql/05_roles.sql")
    for name, sql in blocks("sql/06_insights.sql"):
        psql("-c", f"\\copy ({sql}) TO 'results/{name}.csv' WITH (FORMAT csv, HEADER true)")

    counts_sql = ("SELECT json_build_object('aircraft', (SELECT count(*) FROM faa.aircraft), 'aircraft_model', (SELECT count(*) FROM faa.aircraft_model),"
                  " 'engine_model', (SELECT count(*) FROM faa.engine_model), 'deregistration', (SELECT count(*) FROM faa.deregistration),"
                  " 'aircraft_md5', (SELECT md5(string_agg(a::text, '|' ORDER BY n_number)) FROM faa.aircraft a))")
    counts = json.loads(psql("-tA", "-c", counts_sql))
    issues = psql("-tA", "-F", "\t", "-c", "SELECT table_name, column_name, action, count(*) FROM faa.load_issue GROUP BY 1, 2, 3 ORDER BY 4 DESC")
    (OUT / "load_issues.csv").write_text("table,column,action,rows\n" + "".join(
        ",".join(f'"{x}"' if "," in x else x for x in line.split("\t")) + "\n" for line in issues.strip().splitlines()))

    (HERE / "backup").mkdir(exist_ok=True)
    dump = HERE / "backup" / "faa.dump"
    subprocess.run([str(BIN / "pg_dump"), *CONN, "-d", "registry", "-n", "faa", "-Fc", "-f", str(dump)], check=True)
    psql("-c", "DROP DATABASE IF EXISTS registry_restore", db="postgres")
    psql("-c", "CREATE DATABASE registry_restore", db="postgres")
    psql("-c", "CREATE EXTENSION IF NOT EXISTS pg_trgm", db="registry_restore")
    subprocess.run([str(BIN / "pg_restore"), *CONN, "-d", "registry_restore", "--no-owner", str(dump)], check=True)
    restored = json.loads(psql("-tA", "-c", counts_sql, db="registry_restore"))
    size = psql("-tA", "-c", "SELECT pg_size_pretty(pg_database_size('registry'))").strip()

    summary = {"rows": {k: v for k, v in counts.items() if k != "aircraft_md5"}, "load_seconds": round(load_seconds, 1), "database_size": size,
               "backup": {"dump_mb": round(dump.stat().st_size / 1e6, 1), "restored_counts_match": restored == counts}}
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=1))
    for p in perf:
        print(f"{p['before_ms']:9.2f} ms -> {p['after_ms']:8.2f} ms  {p['before_scans']} -> {p['after_scans']}  {p['question']}")
    print(issues)


if __name__ == "__main__":
    main()
