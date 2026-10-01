"""Step 1: download the FAA aircraft registry and write load-ready CSVs WITHOUT personal data.

    ./venv/bin/python prepare.py

Source: FAA Civil Aviation Registry, Releasable Aircraft Database (public domain, updated daily):
https://registry.faa.gov/database/ReleasableAircraft.zip, data dictionary https://registry.faa.gov/database/ardata.pdf
Data minimisation: registrant and co-owner names, street addresses, ZIP codes and county codes are never loaded.
Only city, state and country are kept, and only aggregates are published.
"""
import csv
import json
import ssl
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

HERE = Path(__file__).parent
RAW, CLEAN = HERE / "data" / "raw", HERE / "data" / "clean"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"}
KEEP = {
    "MASTER": {"N-NUMBER": "n_number", "SERIAL NUMBER": "serial_number", "MFR MDL CODE": "model_code", "ENG MFR MDL": "engine_code",
               "YEAR MFR": "year_mfr", "TYPE REGISTRANT": "registrant_type", "CITY": "city", "STATE": "state", "REGION": "region",
               "COUNTRY": "country", "LAST ACTION DATE": "last_action_date", "CERT ISSUE DATE": "cert_issue_date",
               "CERTIFICATION": "certification", "TYPE AIRCRAFT": "aircraft_type", "TYPE ENGINE": "engine_type",
               "STATUS CODE": "status_code", "MODE S CODE HEX": "mode_s_hex", "FRACT OWNER": "fractional",
               "AIR WORTH DATE": "airworthiness_date", "EXPIRATION DATE": "expiration_date", "UNIQUE ID": "unique_id",
               "KIT MFR": "kit_mfr", "KIT MODEL": "kit_model"},
    "ACFTREF": {"CODE": "code", "MFR": "manufacturer", "MODEL": "model", "TYPE-ACFT": "aircraft_type", "TYPE-ENG": "engine_type",
                "AC-CAT": "category", "BUILD-CERT-IND": "builder_cert", "NO-ENG": "engines", "NO-SEATS": "seats",
                "AC-WEIGHT": "weight_class", "SPEED": "cruise_mph", "TC-DATA-SHEET": "tc_data_sheet", "TC-DATA-HOLDER": "tc_holder"},
    "ENGINE": {"CODE": "code", "MFR": "manufacturer", "MODEL": "model", "TYPE": "engine_type", "HORSEPOWER": "horsepower", "THRUST": "thrust_lb"},
    "DEREG": {"N-NUMBER": "n_number", "SERIAL-NUMBER": "serial_number", "MFR-MDL-CODE": "model_code", "STATUS-CODE": "status_code",
              "YEAR-MFR": "year_mfr", "CANCEL-DATE": "cancel_date", "EXP-COUNTRY": "export_country", "MODE S CODE HEX": "mode_s_hex"},
}


def download():
    RAW.mkdir(parents=True, exist_ok=True)
    ctx = ssl.create_default_context(cafile="/etc/ssl/cert.pem")
    for name in ("ReleasableAircraft.zip", "ardata.pdf"):
        req = urllib.request.Request(f"https://registry.faa.gov/database/{name}", headers=UA)
        (RAW / name).write_bytes(urllib.request.urlopen(req, context=ctx, timeout=600).read())
    with zipfile.ZipFile(RAW / "ReleasableAircraft.zip") as z:
        for f in KEEP:
            z.extract(f"{f}.txt", RAW)


def clean(name):
    """Fields are space-padded to fixed widths and lines end in a comma. A comma typed inside a value (it happens in
    names) splits one field in two; such a row is repaired by merging the two pieces whose widths add up to the field's
    width. Returns the kept, trimmed columns and the number of rows repaired."""
    with open(RAW / f"{name}.txt", encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    header, body = [c.strip() for c in rows[0]], rows[1:]
    widths = [len(x) for x in body[0]]
    repaired = 0
    for k, r in enumerate(body):
        while len(r) > len(widths):
            i = next(i for i in range(len(r) - 1) if len(r[i]) != widths[i] and len(r[i]) + 1 + len(r[i + 1]) == widths[i])
            r = r[:i] + [r[i] + "," + r[i + 1]] + r[i + 2:]
            repaired += 1
        body[k] = r
    d = pd.DataFrame(body, columns=header + [""] * (len(widths) - len(header)))
    d = d[list(KEEP[name])].rename(columns=KEEP[name])
    return d.apply(lambda s: s.str.strip()), repaired


if __name__ == "__main__":
    if not (RAW / "MASTER.txt").exists():
        download()
    CLEAN.mkdir(parents=True, exist_ok=True)
    report = {}
    for name in KEEP:
        d, repaired = clean(name)
        d.to_csv(CLEAN / f"{name.lower()}.csv", index=False)
        report[name] = {"rows": len(d), "rows_repaired_stray_comma": repaired}
        print(name, len(d), "rows,", repaired, "repaired ->", f"data/clean/{name.lower()}.csv")
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "prepare_report.json").write_text(json.dumps(report, indent=2) + "\n")
