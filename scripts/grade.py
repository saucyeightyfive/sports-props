#!/usr/bin/env python3
"""Grade results, settle P&L, and measure margin vs fair (G1).

Two DIFFERENT lines are in play and conflating them corrupts the top-line
ledger:

  * settlement line = line_stake  -- the number you actually bet. Money is
    won or lost against this and nothing else.
  * fair line       = line_close  -- the market's best estimate. Hypotheses
    are judged on mean margin against this (G1).

If the line moves after you stake, those two disagree, and grading P&L against
the close manufactures wins and losses that never happened.

  python scripts/grade.py --week 1
  python scripts/grade.py --week 1 --manual ROW_ID=78.5 ROW_ID2=4
"""
import argparse, csv, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

STAT_MAP = {
    "player_pass_yds": "passing_yards",
    "player_pass_tds": "passing_tds",
    "player_rush_yds": "rushing_yards",
    "player_reception_yds": "receiving_yards",
    "player_receptions": "receptions",
}

# Markets that are yes/no rather than over/under. Line is implicitly 0.5.
BINARY_MARKETS = {"player_anytime_td"}
YES_SIDES = {"over", "yes"}


def settlement_line(row):
    """The line the money was risked at. Never the close."""
    if row.get("prop_type") in BINARY_MARKETS:
        return 0.5
    v = row.get("line_stake")
    if v in (None, ""):
        raise ValueError(f"{row.get('row_id')}: no line_stake — cannot settle")
    return float(v)


def fair_line(row):
    """Closing line when present (G1); otherwise the stake line, and the
    caller must treat the margin as unverified."""
    if row.get("prop_type") in BINARY_MARKETS:
        return 0.5
    v = row.get("line_close") or row.get("line_stake")
    return float(v) if v not in (None, "") else None


def _side_wins(actual, line, side):
    if actual == line:
        return None                      # push
    over = actual > line
    return over if side in YES_SIDES else (not over)


def settle(row, actual):
    """Returns (outcome, pnl_units). Graded against line_stake."""
    line = settlement_line(row)
    side = (row.get("side") or "").strip().lower()
    actual = float(actual)
    won = _side_wins(actual, line, side)
    if won is None:
        return "PUSH", 0.0
    stake = float(row.get("stake_units") or 0)
    if stake == 0:
        return ("WIN" if won else "LOSS"), 0.0   # shadow row: graded, no money
    pnl = C.payout_units(row["price_stake"], stake) if won else -stake
    return ("WIN" if won else "LOSS"), round(pnl, 4)


def margin_vs_fair(row, actual):
    """Signed margin in the direction of the bet, against the fair line (G1).

    Positive = the result beat the market's own estimate in the direction you
    took. Sign-correcting matters: an UNDER that lands 6 below fair is a +6
    read, not a -6 one, and averaging unsigned margins across sides is
    meaningless.
    """
    fair = fair_line(row)
    if fair is None:
        return None, False
    side = (row.get("side") or "").strip().lower()
    raw = float(actual) - fair
    signed = raw if side in YES_SIDES else -raw
    verified = bool(row.get("line_close"))   # false => graded against stake line
    return round(signed, 3), verified


def pull_actuals(week):
    try:
        import nfl_data_py as nfl
    except ImportError:
        print("  [skip] nfl_data_py not installed — manual values only")
        return {}
    try:
        wk = nfl.import_weekly_data([C.SEASON])
        wk = wk[wk["week"] == week]
    except Exception as e:
        print(f"  [warn] weekly data: {e}")
        return {}
    out = {}
    for rec in wk.to_dict("records"):
        name = rec.get("player_display_name") or rec.get("player_name")
        rec["_anytime_td"] = (float(rec.get("rushing_tds") or 0)
                              + float(rec.get("receiving_tds") or 0))
        out[name] = rec
    print(f"  actuals: {len(out)} players")
    return out


def resolve_actual(row, actuals, manual):
    if row["row_id"] in manual:
        return manual[row["row_id"]]
    rec = actuals.get(row["player"])
    if not rec:
        return None
    if row["prop_type"] in BINARY_MARKETS:
        return rec.get("_anytime_td")
    stat = STAT_MAP.get(row["prop_type"])
    if not stat or stat not in rec:
        return None
    return rec[stat]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--manual", nargs="*", default=[],
                    help="ROW_ID=ACTUAL pairs; overrides the pulled value")
    a = ap.parse_args()
    print(f"== GRADE — {C.SEASON} week {a.week} ==")

    with open(C.BETS, newline="") as f:
        rdr = csv.DictReader(f)
        fieldnames, rows = rdr.fieldnames, list(rdr)

    manual = dict(p.split("=", 1) for p in a.manual)
    # Manual is an OVERRIDE layered on the pull, not a replacement for it:
    # grading one row by hand must not silently strand every other row.
    actuals = pull_actuals(a.week)

    target = [r for r in rows if str(r["week"]) == str(a.week) and not r["outcome"]]
    print(f"  ungraded rows: {len(target)}")

    graded, unverified = 0, 0
    for r in target:
        actual = resolve_actual(r, actuals, manual)
        if actual is None:
            print(f"  [miss] no actual for {r['row_id']} {r['player']} "
                  f"({r['prop_type']})")
            continue
        try:
            outcome, pnl = settle(r, actual)
        except ValueError as e:
            print(f"  [skip] {e}")
            continue
        r["actual_result"] = str(actual)
        r["outcome"] = outcome
        r["pnl_units"] = str(pnl)
        m, verified = margin_vs_fair(r, actual)
        if m is not None:
            r["margin_vs_fair"] = str(m)
            if not verified:
                unverified += 1
        graded += 1
        flags = ""
        if not float(r.get("stake_units") or 0):
            flags += "  [shadow]"
        if not verified:
            flags += "  [margin vs STAKE line — no close captured]"
        print(f"  {r['row_id']:>10} {r['player'][:22]:<22} {r['prop_type'][:20]:<20} "
              f"{outcome:<5} margin {r.get('margin_vs_fair','—'):>7}{flags}")

    tmp = C.BETS.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader(); w.writerows(rows)
    tmp.replace(C.BETS)

    print(f"\n  graded {graded} row(s)")
    if unverified:
        print(f"  WARNING: {unverified} row(s) had no closing line. Their margin "
              f"is measured against the line you bet, which is not a fair line. "
              f"Do not let those rows inform a tier change (G1).")
    live = [r for r in rows if str(r["week"]) == str(a.week)
            and float(r.get("stake_units") or 0) > 0 and r["pnl_units"]]
    if live:
        print(f"  week P&L (live only): {sum(float(r['pnl_units']) for r in live):+.3f}u "
              f"on {len(live)} staked row(s)")
    else:
        print("  week P&L: 0.000u — no live stakes (all shadow)")
    print("\n  NEXT: propose classifications -> classifications.csv (status=PROPOSED),")
    print("  then wait for ratification. Claude never ratifies its own work.")


if __name__ == "__main__":
    main()
