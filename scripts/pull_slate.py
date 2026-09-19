#!/usr/bin/env python3
"""Pull a week's slate: schedule, injuries, usage inputs, and open prop lines.

Writes immutable dated snapshots to data/raw/. Does NOT stake anything and does
NOT decide anything — collection only (see CLAUDE.md: automate collection, never
automate judgment).

  python scripts/pull_slate.py --week 1
"""
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C


def snapshot(name, payload, week):
    C.RAW.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = C.RAW / f"{C.SEASON}_wk{week:02d}_{name}_{ts}.json"
    path.write_text(json.dumps(payload, indent=2, default=str))
    print(f"  wrote {path.relative_to(C.ROOT)}")
    return path


def pull_nflverse(week):
    """Schedule + usage inputs (G4). Free via nflverse."""
    try:
        import nfl_data_py as nfl
    except Exception as e:
        # Deliberately broad. nfl_data_py imports pandas and numpy, and a
        # version mismatch there raises AttributeError or TypeError at import,
        # not ImportError. Collection is best-effort; a dependency skew should
        # cost a warning, never the whole capture run.
        print(f"  [skip] nfl_data_py unavailable: {type(e).__name__}: {e}")
        return None
    out = {}
    try:
        sched = nfl.import_schedules([C.SEASON])
        sched = sched[sched["week"] == week]
        out["schedule"] = sched.to_dict("records")
        print(f"  schedule: {len(out['schedule'])} games")
    except Exception as e:
        print(f"  [warn] schedule: {e}")
    try:
        inj = nfl.import_injuries([C.SEASON])
        inj = inj[inj["week"] == week]
        out["injuries"] = inj.to_dict("records")
        print(f"  injuries: {len(out['injuries'])} rows")
    except Exception as e:
        print(f"  [warn] injuries: {e}")
    try:
        # Usage inputs, not result stats (G4).
        snaps = nfl.import_snap_counts([C.SEASON])
        out["snap_counts"] = snaps[snaps["week"] < week].to_dict("records")
        print(f"  snap counts: {len(out['snap_counts'])} rows (weeks < {week})")
    except Exception as e:
        print(f"  [warn] snap counts: {e}")
    return out


def pull_props(week):
    """Open prop lines from The Odds API."""
    if not C.ODDS_API_KEY:
        print("  [skip] ODDS_API_KEY not set — see README")
        return None
    import urllib.request, urllib.parse, urllib.error
    events_url = (f"{C.ODDS_BASE}/sports/{C.SPORT}/events"
                  f"?apiKey={C.ODDS_API_KEY}")
    try:
        with urllib.request.urlopen(events_url, timeout=30) as r:
            events = json.loads(r.read())
    except urllib.error.URLError as e:
        print(f"  [warn] events fetch failed: {e}")
        return None
    print(f"  events: {len(events)}")
    out = []
    for ev in events:
        q = urllib.parse.urlencode({
            "apiKey": C.ODDS_API_KEY,
            "regions": "us",
            "markets": ",".join(C.PROP_MARKETS),
            "oddsFormat": "american",
            "bookmakers": ",".join(C.BOOKMAKERS),
        })
        url = f"{C.ODDS_BASE}/sports/{C.SPORT}/events/{ev['id']}/odds?{q}"
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                out.append(json.loads(r.read()))
        except urllib.error.URLError as e:
            print(f"  [warn] props for {ev.get('id')}: {e}")
    print(f"  prop boards: {len(out)}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, required=True)
    a = ap.parse_args()
    print(f"== SLATE PULL — {C.SEASON} week {a.week} ==")
    nv = pull_nflverse(a.week)
    if nv:
        snapshot("nflverse", nv, a.week)
    pr = pull_props(a.week)
    if pr:
        snapshot("props_open", pr, a.week)
    print("\nSnapshots are immutable. Next: analyze, verify underlying (G4),")
    print("decompose the expression (G3), then log candidate rows to bets.csv")
    print("with line_stake/price_stake/ts_stake filled in.")
    print("REMINDER: tag every read PROJECTED vs CONFIRMED — inactives post ~90m out.")


if __name__ == "__main__":
    main()
