"""Download and normalize the exact SportsDataverse assets needed for weekly refresh."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import requests

ASSETS = {
    "schedule_2026": "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-cfb-data/main/cfb/cfb_schedules/parquet/cfb_schedules_2026.parquet",
    "schedule_2025": "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-cfb-data/main/cfb/cfb_schedules/parquet/cfb_schedules_2025.parquet",
    "pbp_2026": "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-cfb-data/main/cfb/pbp/parquet/play_by_play_2026.parquet",
    "team_box_2026": "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-cfb-data/main/cfb/team_box/parquet/team_box_2026.parquet",
    "raw_schedule_2026": "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-cfb-raw/main/cfb/schedules/csv/cfb_schedule_2026.csv",
}

OUT = Path("source-bundle")
OUT.mkdir(exist_ok=True)

manifest = {}
s = requests.Session()
s.headers.update({"User-Agent": "CFB-Refresh-source-bundle/1.2"})

for name, url in ASSETS.items():
    r = s.get(url, timeout=120)
    r.raise_for_status()
    suffix = ".parquet" if url.endswith(".parquet") else ".csv"
    path = OUT / f"{name}{suffix}"
    path.write_bytes(r.content)
    manifest[name] = {
        "url": url,
        "bytes": len(r.content),
        "sha256": hashlib.sha256(r.content).hexdigest(),
        "file": path.name,
    }

for year in (2025, 2026):
    p = OUT / f"schedule_{year}.parquet"
    d = pd.read_parquet(p)
    c = OUT / f"schedule_{year}.csv.gz"
    d.to_csv(c, index=False, compression="gzip")
    manifest[f"schedule_{year}_csv"] = {
        "rows": len(d),
        "file": c.name,
        "bytes": c.stat().st_size,
        "sha256": hashlib.sha256(c.read_bytes()).hexdigest(),
    }

(OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
print(json.dumps(manifest, indent=2))
