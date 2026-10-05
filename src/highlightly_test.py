"""Isolated source-coverage test for the 2026 CFB weekly refresh.

NO Google Sheets writes. NO production-model calculations are changed.

This test deliberately avoids recursive GitHub tree scans.  The upstream
SportsDataverse raw repository is large enough that the recursive tree API can
return transient 5xx responses.  We only verify the exact season assets needed
by the refresh, then use Highlightly as a secondary/recovery coverage check.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.parse import quote

import requests

PENDING = [
    "App State","Ball St.","Baylor","Central Mich.","Charlotte","Coastal Carolina","Delaware",
    "Ga. Southern","Jacksonville St.","Liberty","Louisiana","Louisiana Tech","Marshall",
    "Massachusetts","Middle Tenn.","Missouri St.","Nevada","North Dakota St.","Ohio",
    "Sacramento St.","Sam Houston","South Alabama","South Fla.","Temple","Toledo","Tulsa",
    "UAB","ULM","Wyoming"
]
ALIASES = {
    "App State":["App State","Appalachian State"],"Ball St.":["Ball State"],"Central Mich.":["Central Michigan"],
    "Ga. Southern":["Georgia Southern"],"Jacksonville St.":["Jacksonville State"],
    "Louisiana":["Louisiana","Louisiana Ragin' Cajuns"],"Middle Tenn.":["Middle Tennessee"],
    "Missouri St.":["Missouri State"],"North Dakota St.":["North Dakota State"],
    "Sacramento St.":["Sacramento State"],"Sam Houston":["Sam Houston","Sam Houston State"],
    "South Alabama":["South Alabama"],"South Fla.":["South Florida","USF"],
    "ULM":["UL Monroe","Louisiana-Monroe","ULM"],"Massachusetts":["UMass","Massachusetts"],
}

BASE = "https://american-football.highlightly.net"
GH_CONTENT = "https://api.github.com/repos/{repo}/contents/{path}?ref={branch}"
S = requests.Session()
S.headers.update({
    "User-Agent": "CFB-Refresh-coverage-test/2.0",
    "Accept": "application/vnd.github+json",
})

SOURCE_ASSETS = {
    "processed_schedule": (
        "sportsdataverse/cfbfastR-cfb-data",
        "cfb/cfb_schedules/parquet/cfb_schedules_2026.parquet",
    ),
    "processed_pbp": (
        "sportsdataverse/cfbfastR-cfb-data",
        "cfb/pbp/parquet/play_by_play_2026.parquet",
    ),
    "processed_team_box": (
        "sportsdataverse/cfbfastR-cfb-data",
        "cfb/team_box/parquet/team_box_2026.parquet",
    ),
    "raw_schedule": (
        "sportsdataverse/cfbfastR-cfb-raw",
        "cfb/schedules/csv/cfb_schedule_2026.csv",
    ),
}


def norm(x):
    return re.sub(r"[^a-z0-9]+", "", str(x).lower())


def names(team):
    return [team] + ALIASES.get(team, [])


def gh_asset(repo, path, branch="main"):
    """Check one exact GitHub contents path; never enumerate the full repo."""
    url = GH_CONTENT.format(repo=repo, path=quote(path, safe="/"), branch=branch)
    try:
        r = S.get(url, timeout=30)
        if r.status_code == 404 and branch == "main":
            return gh_asset(repo, path, "master")
        if r.status_code != 200:
            return {
                "available": False,
                "http": r.status_code,
                "repo": repo,
                "path": path,
                "error": r.text[:300],
            }
        payload = r.json()
        return {
            "available": payload.get("type") == "file",
            "http": r.status_code,
            "repo": repo,
            "path": path,
            "sha": payload.get("sha"),
            "size": payload.get("size"),
            "download_url": payload.get("download_url"),
        }
    except requests.RequestException as exc:
        return {
            "available": False,
            "http": None,
            "repo": repo,
            "path": path,
            "error": repr(exc),
        }


def highlightly():
    key = os.environ["HIGHLIGHTLY_API_KEY"]
    h = {"x-rapidapi-key": key}
    r = S.get(
        f"{BASE}/matches",
        headers=h,
        params={"league": "NCAA", "season": 2026, "limit": 100, "offset": 0},
        timeout=30,
    )
    r.raise_for_status()
    payload = r.json()
    data = payload.get("data", payload if isinstance(payload, list) else [])
    total = (payload.get("pagination", {}) or {}).get("total") if isinstance(payload, dict) else None
    off = 100
    while total and off < total and off < 1000:
        rr = S.get(
            f"{BASE}/matches",
            headers=h,
            params={"league": "NCAA", "season": 2026, "limit": 100, "offset": off},
            timeout=30,
        )
        rr.raise_for_status()
        pp = rr.json()
        data += pp.get("data", [])
        off += 100
    return h, data


def team_label(obj):
    vals = []
    for k in ("name", "displayName", "abbreviation"):
        if isinstance(obj, dict) and obj.get(k):
            vals.append(str(obj[k]))
    return vals


def match_has(match, team):
    wanted = {norm(n) for n in names(team)}
    vals = []
    for side in ("homeTeam", "awayTeam"):
        vals += team_label(match.get(side, {}))
    return any(norm(v) in wanted for v in vals)


def finished(match):
    return str(match.get("state") or match.get("status") or "").lower() == "finished"


def inspect_detail(headers, mid):
    r = S.get(f"{BASE}/matches/{mid}", headers=headers, timeout=30)
    if r.status_code != 200:
        return {"detail_http": r.status_code}
    d = r.json()
    if isinstance(d, list):
        d = d[0] if d else {}
    ev = d.get("events") or []
    sample = ev[0] if ev else {}
    keys = set(sample.keys()) if isinstance(sample, dict) else set()
    required_groups = {
        "down": {"down"},
        "distance": {"distance", "yardsToGo", "yardsToFirstDown"},
        "field_position": {"yardLine", "yardsToEndzone", "yardsToEndZone"},
        "clock": {"clock", "time", "displayClock"},
        "period": {"period", "quarter"},
        "possession": {"possession", "team", "teamId"},
        "play_text": {"text", "description", "playText", "type"},
    }
    return {
        "detail_http": 200,
        "events": len(ev),
        "event_field_groups": {g: bool(keys & ks) for g, ks in required_groups.items()},
        "sample_event_keys": sorted(keys),
    }


def main():
    Path("test-output").mkdir(exist_ok=True)

    assets = {
        name: gh_asset(repo, path)
        for name, (repo, path) in SOURCE_ASSETS.items()
    }
    source_ready = all(v.get("available") for v in assets.values())

    headers, matches = highlightly()

    report = {
        "season": 2026,
        "pending_count": len(PENDING),
        "source_strategy": "targeted exact 2026 assets; no recursive GitHub tree scan",
        "cfbfastR": {
            "source_ready": source_ready,
            "assets": assets,
        },
        "highlightly": {
            "ncaa_2026_matches_returned": len(matches),
        },
        "teams": {},
    }

    detail_ids = []
    for team in PENDING:
        hm = [m for m in matches if match_has(m, team)]
        fin = [m for m in hm if finished(m)]
        rec = {
            "highlightly_matches": len(hm),
            "highlightly_finished": len(fin),
        }
        if fin:
            latest = sorted(fin, key=lambda x: str(x.get("date", "")))[-1]
            rec["latest_finished"] = {
                "id": latest.get("id"),
                "date": latest.get("date"),
                "home": (latest.get("homeTeam") or {}).get("displayName"),
                "away": (latest.get("awayTeam") or {}).get("displayName"),
            }
            if latest.get("id") and len(detail_ids) < 12:
                detail_ids.append((team, latest.get("id")))
        report["teams"][team] = rec

    report["highlightly"]["detail_samples"] = {
        team: inspect_detail(headers, mid) for team, mid in detail_ids
    }

    out = Path("test-output/coverage.json")
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))

    if not source_ready:
        missing = [k for k, v in assets.items() if not v.get("available")]
        raise SystemExit("Required 2026 source assets unavailable: " + ", ".join(missing))


if __name__ == "__main__":
    main()
