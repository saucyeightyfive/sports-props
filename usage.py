#!/usr/bin/env python3
"""Usage inputs, derived — the G4 layer.

G4 says reads must rest on usage inputs, not result stats. This module is where
those inputs come from, and it is deliberately explicit about which ones do not
exist, because a hypothesis that cannot be evaluated is worse than one that
fails: it looks alive while producing nothing.

WHAT IS AVAILABLE, free, for the current season:
  snap share        snap_counts.offense_pct           (nflverse)
  target share      derived from play-by-play          (nflverse)
  aDOT              derived from play-by-play          (nflverse)
  air yards share   derived from play-by-play          (nflverse)
  rush share        derived from play-by-play          (nflverse)
  team pass rate    derived from play-by-play          (nflverse)

WHAT IS NOT:
  route participation   routes run is not published in any free nflverse feed.
  targets per route run needs routes. Both require a paid charting source
                        (PFF, FTN premium). Until one is funded, any hypothesis
                        whose trigger names them cannot fire — see scan.py,
                        which reports that rather than silently substituting a
                        proxy.

The substitution is the thing to resist. Snap share is not route participation:
a back who plays 80% of snaps may run routes on 20% of dropbacks. Swapping one
for the other would keep the hypothesis "running" while testing a different
claim entirely, and the record would look valid.
"""
import sys, warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

warnings.filterwarnings("ignore")

PBP_URL = ("https://github.com/nflverse/nflverse-data/releases/download/"
           "pbp/play_by_play_{season}.parquet")

# Inputs a trigger may reference, and whether we can actually produce them.
AVAILABLE = {
    "snap share", "target share", "targets", "adot", "air yards",
    "air yards share", "rush share", "rush attempts", "team pass rate",
    "team pass attempts", "injury status",
}
UNAVAILABLE = {
    "route participation": "routes run is not in any free nflverse feed",
    "routes run": "not published free; needs PFF or FTN premium",
    "targets per route run": "needs routes run",
    "tprr": "needs routes run",
    "pressure rate": "not published free; needs PFF",
    "proe": "needs a pass-rate-over-expected model, not yet built",
}


def _pbp(season=None):
    import pandas as pd
    season = season or C.SEASON
    return pd.read_parquet(PBP_URL.format(season=season), engine="auto")


def usage_table(through_week):
    """Per-player usage for every completed week strictly before through_week.

    Returns a list of dicts. Empty list if the data cannot be reached — the
    caller decides what that means; this never invents a row.
    """
    try:
        import pandas as pd
        p = _pbp()
    except Exception as e:
        print(f"  [warn] play-by-play unavailable: {type(e).__name__}: {e}")
        return []

    p = p[p["week"] < through_week]
    if p.empty:
        return []

    passes = p[(p["play_type"] == "pass") & p["receiver_player_name"].notna()]
    rushes = p[(p["play_type"] == "run") & p["rusher_player_name"].notna()]

    team_tgts = passes.groupby(["posteam", "week"]).size().rename("team_targets")
    team_air = passes.groupby(["posteam", "week"])["air_yards"].sum().rename("team_air")
    team_rush = rushes.groupby(["posteam", "week"]).size().rename("team_rushes")
    team_plays = p[p["play_type"].isin(["pass", "run"])] \
        .groupby(["posteam", "week"]).size().rename("team_plays")
    team_pass = passes.groupby(["posteam", "week"]).size().rename("team_pass")

    rec = passes.groupby(["posteam", "week", "receiver_player_name"]).agg(
        targets=("play_type", "size"),
        receptions=("complete_pass", "sum"),
        air_yards=("air_yards", "sum"),
        adot=("air_yards", "mean")).reset_index()
    rec = rec.join(team_tgts, on=["posteam", "week"]) \
             .join(team_air, on=["posteam", "week"])
    rec["target_share"] = rec["targets"] / rec["team_targets"]
    rec["air_yards_share"] = rec["air_yards"] / rec["team_air"].replace(0, float("nan"))
    rec = rec.rename(columns={"receiver_player_name": "player"})

    run = rushes.groupby(["posteam", "week", "rusher_player_name"]).agg(
        rush_attempts=("play_type", "size")).reset_index()
    run = run.join(team_rush, on=["posteam", "week"])
    run["rush_share"] = run["rush_attempts"] / run["team_rushes"]
    run = run.rename(columns={"rusher_player_name": "player"})

    merged = rec.merge(run, on=["posteam", "week", "player"], how="outer")
    merged = merged.join(team_plays, on=["posteam", "week"]) \
                   .join(team_pass, on=["posteam", "week"])
    merged["team_pass_rate"] = merged["team_pass"] / merged["team_plays"]
    merged = merged.rename(columns={"posteam": "team"})
    return merged.fillna(0).to_dict("records")


def snap_share(snapshot):
    """Snap share from a captured nflverse snapshot (offense_pct, 0-1)."""
    rows = (snapshot or {}).get("snap_counts") or []
    out = []
    for r in rows:
        pct = r.get("offense_pct")
        if pct in (None, ""):
            continue
        pct = float(pct)
        out.append({"player": r.get("player"), "team": r.get("team"),
                    "position": r.get("position"), "week": r.get("week"),
                    "snap_share": pct if pct <= 1 else pct / 100.0})
    return out


def trigger_inputs(trigger_lines):
    """Split a hypothesis's trigger text into inputs we can compute and inputs
    we cannot. Text matching is crude on purpose — it should over-report a
    blocker rather than let an unevaluable trigger through."""
    blob = " ".join(str(t).lower() for t in (trigger_lines or []))
    blocked = {k: why for k, why in UNAVAILABLE.items() if k in blob}
    usable = {k for k in AVAILABLE if k in blob}
    return usable, blocked


if __name__ == "__main__":
    import argparse, json
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, required=True)
    a = ap.parse_args()
    rows = usage_table(a.week)
    print(f"usage rows through week {a.week - 1}: {len(rows)}")
    for r in sorted(rows, key=lambda x: -x.get("targets", 0))[:10]:
        print(f"  {r['player']:<18} {r['team']:<4} wk{int(r['week'])} "
              f"tgt={int(r.get('targets',0)):<3} "
              f"share={r.get('target_share',0):.3f} "
              f"aDOT={r.get('adot',0):.1f}")
