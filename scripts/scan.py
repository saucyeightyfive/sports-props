#!/usr/bin/env python3
"""The scanner — turns a prop board into candidates, or explains why it can't.

This is the only script that applies a hypothesis. It does NOT stake, size, or
decide anything: it reads the board and the usage, tests every trigger, and
writes what fired. Judgment stays with the user (CLAUDE.md).

  python scripts/scan.py --week 2
  python scripts/scan.py --week 2 --explain     # also show the near-misses

Three possible verdicts per hypothesis, and the third is the one that matters:

  FIRED        trigger conditions met; candidates listed
  NO CANDIDATES  evaluable, nothing met the bar — a dry week, correctly reported
  UNEVALUABLE  the trigger names an input we cannot compute. This is NOT a dry
               week. A hypothesis that cannot be evaluated is worse than one
               that fails, because it looks alive while producing nothing, and
               its zero rows read as "no opportunities yet" for a whole season.

Output goes to state/<league>/candidates_wk<N>.json, which the dashboard reads.
"""
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
import usage as U
from report import read_yaml


# --------------------------------------------------------------------------- io
def latest_snapshot(week, kind):
    files = sorted(C.RAW.glob(f"{C.SEASON}_wk{week:02d}_{kind}_*.json"))
    if not files:
        return None
    return json.loads(files[-1].read_text())


def board_rows(props):
    """Flatten the captured prop boards into one row per player/market/book."""
    rows = []
    for board in props or []:
        game = f"{board.get('away_team')} @ {board.get('home_team')}"
        for bk in board.get("bookmakers", []):
            for mk in bk.get("markets", []):
                for o in mk.get("outcomes", []):
                    rows.append({
                        "game": game,
                        "commence_time": board.get("commence_time"),
                        "book": bk.get("key"),
                        "market": mk.get("key"),
                        "player": o.get("description"),
                        "side": (o.get("name") or "").lower(),
                        "line": o.get("point"),
                        "price": o.get("price"),
                    })
    return rows


def best_price(rows, player, market, side):
    """Best available price across books for one player/market/side."""
    cands = [r for r in rows if r["player"] == player and r["market"] == market
             and r["side"] == side and r["price"] is not None]
    if not cands:
        return None
    return max(cands, key=lambda r: r["price"])



# --------------------------------------------------------------------------- names
# Play-by-play abbreviates ("A.St. Brown"); the prop board spells it out
# ("Amon-Ra St. Brown"). Joining on the raw string silently matches nothing,
# which looks exactly like a dry week -- the most dangerous kind of bug here.
# Abbreviation -> the nickname as it appears in the board's full team names.
# Matching on name alone put a Detroit receiver on a Dallas prop, because the
# board happened to carry only one "J. Williams". Requiring the team to agree
# turns that silent mismatch into a skip.
NICK = {
 "ARI":"Cardinals","ATL":"Falcons","BAL":"Ravens","BUF":"Bills","CAR":"Panthers",
 "CHI":"Bears","CIN":"Bengals","CLE":"Browns","DAL":"Cowboys","DEN":"Broncos",
 "DET":"Lions","GB":"Packers","HOU":"Texans","IND":"Colts","JAX":"Jaguars",
 "JAC":"Jaguars","KC":"Chiefs","LA":"Rams","LAR":"Rams","LAC":"Chargers",
 "LV":"Raiders","MIA":"Dolphins","MIN":"Vikings","NE":"Patriots","NO":"Saints",
 "NYG":"Giants","NYJ":"Jets","PHI":"Eagles","PIT":"Steelers","SEA":"Seahawks",
 "SF":"49ers","TB":"Buccaneers","TEN":"Titans","WAS":"Commanders","WSH":"Commanders",
}


def _norm(s):
    s = (s or "").lower().replace(".", " ").replace("'", "").replace("-", " ")
    for suf in (" jr", " sr", " ii", " iii", " iv", " v"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    return " ".join(s.split())


def name_key(full):
    """('a', 'st brown') from either spelling."""
    parts = _norm(full).split()
    if not parts:
        return None
    return (parts[0][0], " ".join(parts[1:])) if len(parts) > 1 else (parts[0][0], parts[0])


def board_name_index(rows):
    idx = {}
    for r in rows:
        k = name_key(r["player"])
        if k:
            idx.setdefault(k, set()).add(r["player"])
    return idx


def resolve(pbp_name, team, rows, bidx):
    """Map an abbreviated name to the board's spelling, and require the team to
    agree. Ambiguity or a team mismatch -> no match: a wrong player is far
    worse than a missed one."""
    k = name_key(pbp_name)
    if not k:
        return None, "unparseable name"
    hits = bidx.get(k)
    if not hits:
        return None, "not on the board"
    if len(hits) != 1:
        return None, f"ambiguous ({len(hits)} board names share this key)"
    board_name = next(iter(hits))
    nick = NICK.get((team or "").upper())
    if not nick:
        return None, f"unknown team abbreviation {team!r}"
    games = {r["game"] for r in rows if r["player"] == board_name}
    if not any(nick in g for g in games):
        return None, f"team mismatch — usage says {team}, board has {list(games)[:1]}"
    return board_name, None


# --------------------------------------------------------------------------- usage
def player_index(usage_rows, snap_rows):
    """Per-player usage, most recent week plus the prior-3 average."""
    by = {}
    for r in usage_rows:
        name = r.get("player")
        if not name:
            continue
        by.setdefault(name, []).append(r)
    snaps = {}
    for s in snap_rows:
        snaps.setdefault(s["player"], []).append(s)

    out = {}
    for name, rs in by.items():
        rs = sorted(rs, key=lambda x: x.get("week", 0))
        last = rs[-1]
        prior = rs[:-1][-3:]

        def avg(k):
            vals = [float(p.get(k) or 0) for p in prior]
            return sum(vals) / len(vals) if vals else None

        sn = sorted(snaps.get(name, []), key=lambda x: x.get("week", 0))
        out[name] = {
            "team": last.get("team"),
            "weeks_seen": len(rs),
            "target_share": float(last.get("target_share") or 0),
            "target_share_prior": avg("target_share"),
            "targets": float(last.get("targets") or 0),
            "adot": float(last.get("adot") or 0),
            "air_yards_share": float(last.get("air_yards_share") or 0),
            "rush_share": float(last.get("rush_share") or 0),
            "rush_attempts": float(last.get("rush_attempts") or 0),
            "team_pass_rate": float(last.get("team_pass_rate") or 0),
            "snap_share": (sn[-1]["snap_share"] if sn else None),
        }
    return out


# --------------------------------------------------------------------------- rules
def _share_rise(idx, rows, bidx, hid, market, min_share, min_rise):
    """Shared shape: current target share above a floor, and risen against the
    player's own prior-3 average."""
    cands, notes = [], []
    for name, u in idx.items():
        if u["weeks_seen"] < 2 or u["target_share_prior"] is None:
            continue
        rise = u["target_share"] - u["target_share_prior"]
        if u["target_share"] < min_share or rise < min_rise:
            continue
        board_name, why = resolve(name, u["team"], rows, bidx)
        if not board_name:
            notes.append(f"{name} ({u['team']}): usage qualifies but {why}")
            continue
        b = best_price(rows, board_name, market, "over")
        if not b:
            notes.append(f"{board_name}: usage qualifies, no {market} line posted")
            continue
        cands.append({
            "hypothesis": hid, "player": board_name, "team": u["team"],
            "game": b["game"], "market": market, "side": "over",
            "line": b["line"], "price": b["price"], "book": b["book"],
            "target_share": round(u["target_share"], 3),
            "target_share_prior": round(u["target_share_prior"], 3),
            "rise": round(rise, 3), "adot": round(u["adot"], 1),
            "snap_share": (round(u["snap_share"], 3) if u["snap_share"] else None),
            "weeks_seen": u["weeks_seen"],
        })
    cands.sort(key=lambda c: -c["rise"])
    return cands, notes


def evaluate(h, idx, rows, bidx, week):
    """Return (verdict, candidates, notes) for one hypothesis.

    Each hypothesis gets its OWN rule. An earlier version ran one generic rule
    for all of them, so three hypotheses returned identical candidates -- which
    is not a scanner, it is one read wearing three hats, and it would have
    triple-counted the same evidence across three separate gates.
    """
    hid = h.get("id")
    usable, blocked = U.trigger_inputs(h.get("trigger"))
    if blocked:
        return "UNEVALUABLE", [], [
            f"trigger names '{k}' — {why}" for k, why in blocked.items()]
    if not idx:
        return "UNEVALUABLE", [], ["no current-season usage data available yet"]

    if hid == "H2":
        # Second-order absorption: a share that jumped hard, which is what a
        # vacated role looks like in the data we can actually see. The full
        # trigger also wants alignment overlap, which needs route data.
        cands, notes = _share_rise(idx, rows, bidx, hid,
                                   "player_receptions", 0.18, 0.08)
        notes.insert(0, "Partial: alignment overlap not verifiable without "
                        "route data. Treat these as leads to check by hand, "
                        "not as a satisfied trigger.")
        return ("FIRED" if cands else "NO CANDIDATES"), cands, notes

    if hid == "H3":
        # News latency needs two board snapshots to measure whether a line
        # moved after the news. One snapshot cannot show movement.
        # Count BOTH board kinds. pull_closing writes props_close_*, and an
        # earlier version of this check globbed only props_open_* -- so the
        # Sunday capture existed and H3 reported "1 captured" forever. The
        # open-vs-close pair is the right comparison anyway: it is exactly the
        # movement between stake-time and the number that settles CLV.
        opens = sorted(C.RAW.glob(f"{C.SEASON}_wk{week:02d}_props_open_*.json"))
        closes = sorted(C.RAW.glob(f"{C.SEASON}_wk{week:02d}_props_close_*.json"))
        snaps = opens + closes
        if len(snaps) < 2:
            return "UNEVALUABLE", [], [
                f"needs two prop-board snapshots to measure line movement; "
                f"{len(opens)} open + {len(closes)} close captured for week {week}",
                "the Thursday slate pull and the Sunday closing pull are the "
                "intended pair"]
        return "NO CANDIDATES", [], ["movement comparison not yet implemented"]

    if hid == "H5":
        # Meta-test. It never fires on its own; it mirrors whatever H1/H2 log.
        return "NO CANDIDATES", [], [
            "rides on H1/H2 rows — pairs are created when a parent row is "
            "logged, not scanned for independently"]

    return "UNEVALUABLE", [], [
        f"no scanner rule written for {hid} yet"]


# --------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--explain", action="store_true")
    a = ap.parse_args()

    print(f"== SCAN — {C.LEAGUE} {C.SEASON} week {a.week} ==")

    props = latest_snapshot(a.week, "props_open")
    nflv = latest_snapshot(a.week, "nflverse")
    rows = board_rows(props)
    print(f"  board: {len(rows)} lines across "
          f"{len({r['player'] for r in rows})} players")

    bidx = board_name_index(rows)
    idx = player_index(U.usage_table(a.week), U.snap_share(nflv))
    print(f"  usage: {len(idx)} players with current-season data")

    hyp = read_yaml(C.HYPOTHESES)
    results, total = [], 0
    for h in (hyp.get("hypotheses") or []):
        verdict, cands, notes = evaluate(h, idx, rows, bidx, a.week)
        total += len(cands)
        results.append({"id": h.get("id"), "name": h.get("name"),
                        "tier": h.get("tier"), "verdict": verdict,
                        "candidates": cands, "notes": notes})
        mark = {"FIRED": "*", "NO CANDIDATES": "-", "UNEVALUABLE": "!"}[verdict]
        print(f"  {mark} {h.get('id')} {verdict}"
              + (f" — {len(cands)} candidate(s)" if cands else ""))
        if a.explain or verdict == "UNEVALUABLE":
            for n in notes[:6]:
                print(f"      {n}")

    out = {"league": C.LEAGUE, "season": C.SEASON, "week": a.week,
           "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "board_lines": len(rows), "players_with_usage": len(idx),
           "results": results}
    path = C.STATE / f"candidates_wk{a.week:02d}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2))
    print(f"\n  wrote {path.relative_to(C.ROOT)}")

    unevaluable = [r["id"] for r in results if r["verdict"] == "UNEVALUABLE"]
    if unevaluable:
        print(f"\n  {len(unevaluable)} hypothesis(es) cannot be evaluated: "
              f"{', '.join(unevaluable)}")
        print("  That is a data problem, not a dry week. Amend the trigger to "
              "an input\n  we can compute, fund the source, or retire it — but "
              "do not let it sit\n  at zero rows all season looking alive.")
    if total == 0 and not unevaluable:
        print("\n  No qualifying play. That is a valid and frequent output.")
    print("\n  Nothing here is staked. Candidates are proposals; logging one is "
          "a\n  decision only you make.")


if __name__ == "__main__":
    main()
