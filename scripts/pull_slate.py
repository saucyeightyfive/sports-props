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
import gaps


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
        gaps.announce(gaps.record("props_open", week, "no_key"))
        return None
    import urllib.request, urllib.parse, urllib.error
    from datetime import datetime, timezone, timedelta

    events_url = (f"{C.ODDS_BASE}/sports/{C.SPORT}/events"
                  f"?apiKey={C.ODDS_API_KEY}")
    try:
        with urllib.request.urlopen(events_url, timeout=30) as r:
            events = json.loads(r.read())
            budget = r.headers.get("x-requests-remaining")
    except urllib.error.URLError as e:
        gaps.announce(gaps.record("props_open", week, "fetch_failed", str(e)))
        return None

    # The events list is free and returns every upcoming game, several weeks
    # deep. Paying for boards on games eight days out is paying for lines that
    # will have moved twice before we look at them.
    horizon = datetime.now(timezone.utc) + timedelta(days=C.PROPS_HORIZON_DAYS)
    def soon(ev):
        t = ev.get("commence_time")
        if not t:
            return True
        try:
            return datetime.fromisoformat(t.replace("Z", "+00:00")) <= horizon
        except ValueError:
            return True
    all_events, events = events, [e for e in events if soon(e)]
    print(f"  events: {len(all_events)} upcoming, {len(events)} within "
          f"{C.PROPS_HORIZON_DAYS}d")

    cost = len(events) * len(C.PROP_MARKETS)
    if budget is not None:
        print(f"  credits: {budget} remaining · this sweep costs ~{cost}")
        try:
            if int(budget) < cost:
                gaps.announce(gaps.record(
                    "props_open", week, "fetch_failed",
                    f"only {budget} credits left, sweep needs ~{cost} — "
                    f"not spending a partial board"))
                return None
        except ValueError:
            pass
    else:
        print(f"  this sweep costs ~{cost} credits")
    out, failed = [], []
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
            failed.append(f"{ev.get('id')}: {e}")
            if "401" in str(e) and len(failed) == 1:
                print("  [warn] 401 on a paid endpoint usually means the "
                      "monthly credit quota is spent, not a bad key")
            if len(failed) <= 3:
                print(f"  [warn] props for {ev.get('id')}: {e}")
            elif len(failed) == 4:
                print("  [warn] ... further per-event failures suppressed")
    print(f"  prop boards: {len(out)}")
    if not out:
        # The old code returned an empty list here and main() silently skipped
        # the write. A week with no board is not a week with no candidates, and
        # the record has to be able to tell them apart.
        gaps.announce(gaps.record(
            "props_open", week, "empty",
            f"{len(events)} event(s) listed, {len(failed)} call(s) failed, "
            f"0 boards returned"))
    else:
        gaps.resolve("props_open", week)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--force-props", action="store_true",
                    help="buy a fresh board even if a recent one exists")
    a = ap.parse_args()
    print(f"== SLATE PULL — {C.SEASON} week {a.week} ==")
    nv = pull_nflverse(a.week)
    if nv:
        snapshot("nflverse", nv, a.week)
        gaps.resolve("nflverse", a.week)
    else:
        gaps.announce(gaps.record("nflverse", a.week, "source_unavailable"))

    # A re-run should not silently re-buy a board. Six sweeps of week 2 cost
    # roughly a month of free-tier credits, and five of them were debugging.
    existing = sorted(C.RAW.glob(f"{C.SEASON}_wk{a.week:02d}_props_open_*.json"))
    fresh = None
    if existing and not a.force_props:
        import time
        age_h = (time.time() - existing[-1].stat().st_mtime) / 3600
        if age_h < C.PROPS_REFRESH_HOURS:
            fresh = existing[-1]
    if fresh:
        print(f"  [skip] board captured {age_h:.1f}h ago "
              f"({fresh.name}) — inside the {C.PROPS_REFRESH_HOURS}h refresh "
              f"window. Use --force-props to buy a new sweep.")
        pr = None
        gaps.resolve("props_open", a.week)
    else:
        pr = pull_props(a.week)
    if pr:
        snapshot("props_open", pr, a.week)

    open_gaps = gaps.for_week(a.week)
    if open_gaps:
        print(f"\n  {len(open_gaps)} OPEN COLLECTION GAP(S) for week {a.week}.")
        print("  The dashboard will show this in red until the data arrives.")
        print("  A green run with a gap in it is the failure this project")
        print("  exists to prevent — do not let it scroll past.")
    print("\nSnapshots are immutable. Next: analyze, verify underlying (G4),")
    print("decompose the expression (G3), then log candidate rows to bets.csv")
    print("with line_stake/price_stake/ts_stake filled in.")
    print("REMINDER: tag every read PROJECTED vs CONFIRMED — inactives post ~90m out.")


if __name__ == "__main__":
    main()
