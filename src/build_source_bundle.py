"""Download the exact 2026 SportsDataverse assets needed for the weekly refresh.

Runs in GitHub Actions only. Does not touch Google Sheets or model formulas.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import requests

ASSETS = {
    "schedule": "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-cfb-data/main/cfb/cfb_schedules/parquet/cfb_schedules_2026.parquet",\n    "schedule_2025": "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-cfb-data/main/cfb/cfb_schedules/parquet/cfb_schedules_2025.parquet",
    "pbp": "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-cfb-data/main/cfb/pbp/parquet/play_by_play_2026.parquet",
    "team_box": "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-cfb-data/main/cfb/team_box/parquet/team_box_2026.parquet",
    "raw_schedule": "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-cfb-raw/main/cfb/schedules/csv/cfb_schedule_2026.csv",
}

OUT = Path("source-bundle")
OUT.mkdir(exist_ok=True)

manifest = {}
s = requests.Session()
s.headers.update({"User-Agent": "CFB-Refresh-source-bundle/1.0"})

for name, url in ASSETS.items():
    r = s.get(url, timeout=120)
    r.raise_for_status()
    suffix = ".parquet" if url.endswith(".parquet") else ".csv"
    path = OUT / f"{name}_2026{suffix}"
    path.write_bytes(r.content)
    manifest[name] = {
        "url": url,
        "bytes": len(r.content),
        "sha256": hashlib.sha256(r.content).hexdigest(),
        "file": path.name,
    }

(OUT / "manifest.json").write_text(json.dumps(manifest, indent=2))
print(json.dumps(manifest, indent=2))
