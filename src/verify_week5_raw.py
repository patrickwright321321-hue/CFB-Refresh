"""Verify Week-5 score-sequence anomalies against raw ESPN final JSON.

No Google credentials. No production writes. This reproduces the frozen scorer's
score-sequence quality screen, then verifies every flagged Week-5 game against
SportsDataverse's raw final ESPN JSON.
"""
import json
from pathlib import Path
import pandas as pd
import requests

S=requests.Session()
S.headers.update({"User-Agent":"CFB-Refresh-raw-verify/1.0"})
SCH_URL="https://raw.githubusercontent.com/sportsdataverse/cfbfastR-cfb-data/main/cfb/cfb_schedules/parquet/cfb_schedules_2026.parquet"
PBP_URL="https://raw.githubusercontent.com/sportsdataverse/cfbfastR-cfb-data/main/cfb/pbp/parquet/play_by_play_2026.parquet"
RAW_BASE="https://raw.githubusercontent.com/sportsdataverse/cfbfastR-cfb-raw/main/cfb/json/final"


def get_file(url,path):
    with S.get(url,stream=True,timeout=180) as r:
        r.raise_for_status()
        with open(path,"wb") as f:
            for ch in r.iter_content(1024*1024):
                if ch:f.write(ch)


def main():
    out=Path("test-output/raw-week5");out.mkdir(parents=True,exist_ok=True)
    get_file(SCH_URL,out/"schedule.parquet")
    get_file(PBP_URL,out/"pbp.parquet")
    sch=pd.read_parquet(out/"schedule.parquet")
    finals=sch[(pd.to_numeric(sch.week,errors="coerce")==5)&sch.status.astype(str).eq("STATUS_FINAL")&sch.completed.astype(str).str.lower().isin(["true","1","1.0"])].copy()
    ids=set(pd.to_numeric(finals.game_id,errors="raise").astype(int))
    pbp=pd.read_parquet(out/"pbp.parquet",columns=["game_id","id","game_play_number","type.text","homeScore","awayScore"])
    pbp["game_id"]=pd.to_numeric(pbp.game_id,errors="coerce").astype("Int64")
    d=pbp[pbp.game_id.isin(ids)].copy().sort_values(["game_id","game_play_number"]).reset_index(drop=True)
    gh=d.groupby("game_id",sort=False)
    hd=pd.to_numeric(d.homeScore,errors="coerce")-pd.to_numeric(gh.homeScore.shift(1),errors="coerce").fillna(0)
    ad=pd.to_numeric(d.awayScore,errors="coerce")-pd.to_numeric(gh.awayScore.shift(1),errors="coerce").fillna(0)
    typ=d["type.text"].fillna("")
    major=typ.str.contains("Touchdown",case=False)|typ.eq("Field Goal Good")|typ.eq("Safety")
    bad=(major&(hd-ad==0))|(hd<0)|(ad<0)|((hd>0)&(ad>0))
    flagged=sorted(set(d.loc[bad,"game_id"].dropna().astype(int)))
    checks=[]
    sched=finals.set_index("game_id")
    for gid in flagged:
        u=f"{RAW_BASE}/{gid}.json"
        r=S.get(u,timeout=120)
        rec={"game_id":gid,"raw_http":r.status_code}
        if r.status_code!=200:
            rec.update(ok=False,error=r.text[:200]);checks.append(rec);continue
        raw=r.json()
        comp=raw["header"]["competitions"][0]
        competitors=comp["competitors"]
        scores={c["homeAway"]:int(c["score"]) for c in competitors}
        team_ids={c["homeAway"]:int(c["team"]["id"]) for c in competitors}
        s=sched.loc[gid]
        header_final=bool(comp["status"]["type"]["completed"]) and scores=={"home":int(s.home_points),"away":int(s.away_points)}
        teams_match=team_ids=={"home":int(s.home_id),"away":int(s.away_id)}
        x=d[d.game_id.eq(gid)]
        raw_ids=[str(p["id"]) for p in raw.get("plays",[])]
        proc_ids=x.id.astype(str).tolist()
        ids_match=(len(raw_ids)==len(proc_ids)==len(set(raw_ids)) and set(raw_ids)==set(proc_ids))
        rec.update({
            "week":5,
            "home":s.home_team,"away":s.away_team,
            "official_final":{"home":int(s.home_points),"away":int(s.away_points)},
            "raw_plays":len(raw_ids),"processed_plays":len(proc_ids),
            "header_final_matches_schedule":header_final,
            "team_ids_match_schedule":teams_match,
            "processed_play_ids_match":ids_match,
            "score_sequence_discrepancy":True,
            "epa_policy":"exclude game EPA; retain complete event and official box statistics",
            "ok":bool(header_final and teams_match and ids_match)
        })
        checks.append(rec)
    report={
        "week":5,
        "week5_final_games":len(finals),
        "score_sequence_flagged_games":len(flagged),
        "flagged_game_ids":flagged,
        "checks":checks,
        "all_raw_checks_pass":bool(checks) and all(x.get("ok") for x in checks)
    }
    (out/"raw_checks.json").write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
    if flagged and not report["all_raw_checks_pass"]:
        raise SystemExit("One or more raw ESPN final checks failed")


if __name__=="__main__":main()
