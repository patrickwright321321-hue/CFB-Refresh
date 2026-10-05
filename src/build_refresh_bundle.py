"""Build a safe local-input bundle for the frozen CFB production refresh.

This workflow has NO Google credentials and makes NO production writes.
It downloads only exact public 2026 SportsDataverse assets and emits:
- full 2026 schedule (for cutoff/neutral/bye logic)
- completed team box rows through the requested completed week
- raw-state/event PBP columns for completed games through that week

Published provider EPA/WPA/QBR/model expectation fields are never included.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import requests

URLS = {
    "schedule": "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-cfb-data/main/cfb/cfb_schedules/parquet/cfb_schedules_2026.parquet",
    "team_box": "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-cfb-data/main/cfb/team_box/parquet/team_box_2026.parquet",
    "pbp": "https://raw.githubusercontent.com/sportsdataverse/cfbfastR-cfb-data/main/cfb/pbp/parquet/play_by_play_2026.parquet",
}

PBP_ALLOW = {
    "game_id","season","week","id","game_play_number","sequenceNumber","type.text","period.number",
    "half","lead_half","start.TimeSecsRem","end.TimeSecsRem","start.down","end.down",
    "start.distance","end.distance","start.yardsToEndzone","end.yardsToEndzone",
    "start.pos_team.id","end.pos_team.id","start.def_pos_team.id","homeTeamId","awayTeamId",
    "pos_score_pts","start.pos_score_diff","start.pos_score_diff_start","pos_score_diff_start",
    "scrimmage_play","rush","pass","sack_vec","pass_attempt","completion","havoc","kneel_down",
    "spike","statYardage","passer_player_name","passer_player_id","scoring_play","td_play",
    "penalty","penalty_play","isPenalty","text_dupe","status_type_completed","homeScore","awayScore",
    "scoringPlay","scoringType.name","scoringType.abbreviation","start.homeScore","start.awayScore",
    "end.homeScore","end.awayScore","sack","spike_vec","qb_spike","scramble","qb_scramble",
}

REQUIRED_PBP = {
    "game_id","season","week","id","game_play_number","type.text","period.number",
    "start.TimeSecsRem","start.down","start.distance","start.yardsToEndzone","start.pos_team.id",
    "homeTeamId","awayTeamId","homeScore","awayScore","statYardage","scrimmage_play","rush","pass",
    "havoc","kneel_down","passer_player_name","passer_player_id",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def download(name: str, url: str, out: Path) -> dict:
    with requests.get(url, stream=True, timeout=180) as r:
        r.raise_for_status()
        with out.open("wb") as f:
            for chunk in r.iter_content(1024 * 1024):
                if chunk:
                    f.write(chunk)
    return {"name": name, "url": url, "bytes": out.stat().st_size, "sha256": sha256(out)}


def truthy(s: pd.Series) -> pd.Series:
    return s.astype(str).str.lower().isin(["true","1","1.0"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--completed-week", type=int, required=True)
    args = ap.parse_args()
    C = args.completed_week
    out = Path("test-output/week-source")
    out.mkdir(parents=True, exist_ok=True)

    src = out / "_downloads"
    src.mkdir(exist_ok=True)
    files = {k: src / f"{k}.parquet" for k in URLS}
    source_manifest = {k: download(k, u, files[k]) for k, u in URLS.items()}

    schedule = pd.read_parquet(files["schedule"])
    if "game_id" not in schedule or "week" not in schedule:
        raise SystemExit("Schedule schema missing game_id/week")
    schedule["game_id"] = pd.to_numeric(schedule["game_id"], errors="raise").astype("int64")
    schedule["week"] = pd.to_numeric(schedule["week"], errors="coerce")
    schedule.to_csv(out / "cfb_schedules_2026.csv.gz", index=False, compression="gzip")

    final_mask = schedule["week"].le(C)
    if "completed" in schedule:
        final_mask &= truthy(schedule["completed"])
    if "status" in schedule:
        final_mask &= schedule["status"].astype(str).eq("STATUS_FINAL")
    finals = schedule.loc[final_mask].copy()
    final_ids = set(finals["game_id"].astype("int64"))
    if not final_ids:
        raise SystemExit(f"No final games found through Week {C}")

    team_box = pd.read_parquet(files["team_box"])
    team_box["game_id"] = pd.to_numeric(team_box["game_id"], errors="coerce").astype("Int64")
    box = team_box[team_box["game_id"].isin(final_ids)].copy()
    box.to_csv(out / "team_box_2026.csv", index=False)

    pf = pq.ParquetFile(files["pbp"])
    schema_names = set(pf.schema.names)
    keep = [c for c in PBP_ALLOW if c in schema_names]
    missing = sorted(REQUIRED_PBP - set(keep))
    if missing:
        raise SystemExit("Required raw PBP columns missing: " + ", ".join(missing))

    chunks = []
    for batch in pf.iter_batches(columns=keep, batch_size=60000):
        d = batch.to_pandas()
        d["game_id"] = pd.to_numeric(d["game_id"], errors="coerce").astype("Int64")
        d = d[d["game_id"].isin(final_ids)]
        if not d.empty:
            chunks.append(d)
    if not chunks:
        raise SystemExit("No PBP rows found for completed games")
    pbp = pd.concat(chunks, ignore_index=True)
    if "status_type_completed" not in pbp:
        pbp["status_type_completed"] = True
    else:
        pbp["status_type_completed"] = True
    pbp.to_csv(out / "plays_v2_2026.csv.gz", index=False, compression="gzip")

    # A parquet copy is useful for play-ID / score-sequence audits.
    audit_cols = [c for c in ["game_id","id","homeScore","awayScore","week"] if c in pbp]
    pbp[audit_cols].to_parquet(out / "play_by_play_2026_audit.parquet", index=False)

    pbp_games = set(pd.to_numeric(pbp["game_id"], errors="coerce").dropna().astype("int64"))
    box_games = set(pd.to_numeric(box["game_id"], errors="coerce").dropna().astype("int64"))
    fbs_final = finals[finals.get("fbs_participant", True).astype(bool)] if "fbs_participant" in finals else finals
    report = {
        "season": 2026,
        "completed_week": C,
        "schedule_rows": len(schedule),
        "final_games_through_week": len(finals),
        "fbs_participant_finals_through_week": len(fbs_final),
        "team_box_rows": len(box),
        "team_box_games": len(box_games),
        "pbp_rows": len(pbp),
        "pbp_games": len(pbp_games),
        "schedule_games_missing_box": sorted(map(int, final_ids - box_games)),
        "schedule_games_missing_pbp": sorted(map(int, final_ids - pbp_games)),
        "pbp_columns": sorted(pbp.columns),
        "source_manifest": source_manifest,
        "policy": "raw-state/event columns only; provider EPA/WPA/QBR/model expectation fields excluded",
    }
    (out / "source_manifest.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

    # Do not fail because non-modeled finals may lack PBP/box; production validation
    # will determine the modeled-team required set from Team Data IDs.
    if len(pbp_games) == 0 or len(box_games) == 0:
        raise SystemExit("Source extraction produced empty core game coverage")


if __name__ == "__main__":
    main()
