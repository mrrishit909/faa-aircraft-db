"""Step 7: charts, and an entity-relationship diagram drawn from the live database's own catalog.

    ./venv/bin/python charts.py   -> charts/01_er_diagram.png (Graphviz), 02_performance.png, 03_fleet_age.png,
                                     04_deregistrations.png, 05_top_models.png
"""
import json
import subprocess
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import run

HERE = Path(__file__).parent
R = HERE / "results"
INK, DIM, GRID, BG, BLUE, ORANGE, GRAY = "#f2f2f0", "#8a8a87", "#1d1d1d", "#0b0b0b", "#3987e5", "#d95926", "#9a9a96"
plt.rcParams.update({
    "figure.facecolor": BG, "axes.facecolor": BG, "savefig.facecolor": BG, "text.color": INK,
    "axes.edgecolor": "#3a3a3a", "axes.labelcolor": DIM, "xtick.color": DIM, "ytick.color": DIM,
    "axes.grid": True, "axes.axisbelow": True, "grid.color": GRID, "grid.linewidth": 1,
    "axes.spines.top": False, "axes.spines.right": False,
    "font.family": ["Helvetica Neue", "Arial", "DejaVu Sans"], "font.size": 11, "axes.titlesize": 13,
    "axes.titlelocation": "left", "axes.titlepad": 12,
})
CORE = ["aircraft", "aircraft_model", "engine_model", "deregistration"]


def save(fig, name):
    fig.tight_layout()
    fig.savefig(HERE / "charts" / name, dpi=150)
    plt.close(fig)


def er_diagram():
    cols = run.psql("-tA", "-F", "\t", "-c", """
        SELECT c.table_name, c.column_name, c.data_type,
               EXISTS (SELECT 1 FROM information_schema.key_column_usage k JOIN information_schema.table_constraints t
                         ON t.constraint_name = k.constraint_name AND t.table_schema = k.table_schema
                        WHERE k.table_schema = 'faa' AND k.table_name = c.table_name AND k.column_name = c.column_name
                          AND t.constraint_type = 'PRIMARY KEY')
          FROM information_schema.columns c WHERE c.table_schema = 'faa' AND c.table_name <> 'load_issue'
           AND c.table_name NOT LIKE 'v_%' AND c.table_name NOT LIKE 'mv_%' ORDER BY c.table_name, c.ordinal_position""")
    fks = run.psql("-tA", "-F", "\t", "-c", """
        SELECT tc.table_name, kcu.column_name, ccu.table_name FROM information_schema.table_constraints tc
          JOIN information_schema.key_column_usage kcu ON kcu.constraint_name = tc.constraint_name AND kcu.table_schema = tc.table_schema
          JOIN information_schema.constraint_column_usage ccu ON ccu.constraint_name = tc.constraint_name AND ccu.table_schema = tc.table_schema
         WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = 'faa'""")
    tables = {}
    for line in cols.strip().splitlines():
        t, c, typ, pk = line.split("\t")
        tables.setdefault(t, []).append((c, typ, pk == "t"))
    lines = ['digraph ER {', '  graph [bgcolor="#0b0b0b", rankdir=LR, nodesep=0.3, ranksep=0.9];',
             '  node [shape=plaintext, fontname="Helvetica", fontcolor="#f2f2f0"];',
             '  edge [color="#5c5c5a", arrowhead=crow, arrowtail=none, fontname="Helvetica", fontsize=9, fontcolor="#8a8a87"];']
    short = {"character varying": "varchar", "character": "char", "smallint": "smallint", "integer": "int", "bigint": "bigint",
             "boolean": "bool", "date": "date", "text": "text"}
    for t, cs in tables.items():
        core = t in CORE
        head = "#1f3b5c" if core else "#2a2a2a"
        rows = "".join(f'<tr><td align="left" port="{c}">{"<b>" if pk else ""}{c}{"</b>" if pk else ""}</td>'
                       f'<td align="left"><font color="#8a8a87">{short.get(typ, typ)}</font></td></tr>' for c, typ, pk in (cs if core else cs[:2]))
        more = "" if core else f'<tr><td colspan="2" align="left"><font color="#8a8a87">lookup ({len(cs)} columns)</font></td></tr>'
        lines.append(f'  {t} [label=<<table border="1" cellborder="0" cellspacing="0" cellpadding="3" color="#3a3a3a" bgcolor="#141414">'
                     f'<tr><td colspan="2" bgcolor="{head}"><b>{t}</b></td></tr>{rows}{more}</table>>];')
    for line in fks.strip().splitlines():
        t, c, ref = line.split("\t")
        lines.append(f'  {ref} -> {t} [label="{c}"];')
    lines.append("}")
    dot = HERE / "charts" / "er_diagram.dot"
    dot.write_text("\n".join(lines) + "\n")
    exe = Path(run.BIN) / "dot"
    subprocess.run([str(exe if exe.exists() else "dot"), "-Tpng", "-Gdpi=130", str(dot), "-o", str(HERE / "charts" / "01_er_diagram.png")], check=True)


def main():
    (HERE / "charts").mkdir(exist_ok=True)
    er_diagram()

    perf = pd.DataFrame(json.loads((R / "performance.json").read_text()))
    labels = ["transponder lookup\n(UNIQUE = already indexed)", "valid, expiring\nin 90 days (partial index)", "aircraft in Tampa, FL\n(composite index)",
              "model name contains 172\n(trigram index)", "all Cessna 172s\n(index on the join key)", "one N-number's history\n(B-tree)"]
    y = np.arange(len(perf))
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.barh(y - 0.18, perf["before_ms"], height=0.34, color=GRAY, label="before")
    ax.barh(y + 0.18, perf["after_ms"], height=0.34, color=BLUE, label="after indexes")
    for i, r in perf.iterrows():
        ax.text(r["before_ms"] * 1.15, i - 0.18, f"{r['before_ms']:.2f} ms", va="center", color=DIM, fontsize=8)
        ax.text(r["after_ms"] * 1.15, i + 0.18, f"{r['after_ms']:.2f} ms", va="center", color=INK, fontsize=8)
    ax.set_xscale("log")
    ax.set_yticks(y, labels, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlim(0.01, 60)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("median execution time, 5 runs (log scale)")
    ax.legend(frameon=False, labelcolor=INK, loc="upper center", bbox_to_anchor=(0.5, -0.16), ncol=2)
    ax.set_title("Indexes turned 8-14 ms scans into sub-millisecond lookups, except the big join")
    save(fig, "02_performance.png")

    a = pd.read_csv(R / "piston_fleet_age.csv")
    fig, ax = plt.subplots(figsize=(10, 3.8))
    labels = ["before 1940"] + [f"{y}s" for y in range(1940, 2020, 10)] + ["2020-26"]
    ax.bar(labels, a["aircraft"], color=BLUE, width=0.65)
    for i, v in enumerate(a["aircraft"]):
        ax.text(i, v + 400, f"{v:,}", ha="center", color=INK, fontsize=9)
    ax.set_ylabel("registered aircraft")
    ax.grid(axis="x", visible=False)
    ax.set_title("America's single-engine piston planes by decade built: most date from the 1960s and 1970s")
    save(fig, "03_fleet_age.png")

    d = pd.read_csv(R / "dereg_by_year.csv")
    fig, ax = plt.subplots(figsize=(10, 3.8))
    ax.bar(d["year"], d["deregistered"] - d["exported"], color=GRAY, width=0.7, label="cancelled for other reasons")
    ax.bar(d["year"], d["exported"], bottom=d["deregistered"] - d["exported"], color=ORANGE, width=0.7, label="exported")
    ax.set_ylabel("aircraft deregistered")
    ax.legend(frameon=False, labelcolor=INK, loc="upper right")
    ax.grid(axis="x", visible=False)
    ax.set_xticks(range(2006, 2026, 2))
    ax.set_title("Deregistrations by year: spikes in 2013 and 2018; exports steady at 1,300-3,300 a year")
    save(fig, "04_deregistrations.png")

    t = pd.read_csv(R / "top_models.csv").iloc[::-1]
    drone = t["manufacturer"].str.contains("ZIPLINE|DJI")
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.barh(t["manufacturer"].str.title().str.replace(" Corp", "").str.replace(" Inc", "").str.replace(" International", "").str.replace("Dji", "DJI") + " " + t["model"],
            t["aircraft"], color=[ORANGE if x else BLUE for x in drone], height=0.65)
    for i, (v, yr) in enumerate(zip(t["aircraft"], t["median_year_built"])):
        ax.text(v + 40, i, f"{v:,}" + (f"  (median built {int(yr)})" if pd.notna(yr) else "  (drone; no build year given)"), va="center", color=INK, fontsize=8)
    ax.set_xlim(0, t["aircraft"].max() * 1.35)
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("registered aircraft")
    ax.set_title("Most-registered models: 1960s-70s Pipers and Cessnas, and now two drones")
    save(fig, "05_top_models.png")
    print("charts written")


if __name__ == "__main__":
    main()
