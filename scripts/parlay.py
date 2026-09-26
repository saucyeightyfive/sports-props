#!/usr/bin/env python3
"""Parlay construction — the second ledger.

The props engine tests hypotheses one leg at a time. This combines its output
into slips. They share a stack and share nothing else: parlay results live in
slips.csv and NEVER touch a hypothesis's record. A hypothesis judged on parlay
outcomes would be judged on other legs' luck.

  python scripts/parlay.py --week 2
  python scripts/parlay.py --week 2 --legs 3 --max 5

WHAT THIS IS HONEST ABOUT

  Compounded vig. Each leg pays the house its cut, so a three-leg slip is taxed
  roughly three times. The engine prints the number rather than burying it: if
  the combined price is +615 and fair is +763, you are giving up 17 cents on
  the dollar and should know that before, not after.

  Correlation. Two legs from one game are not two bets. A quarterback's yards
  and his WR1's yards are close to the same wager wearing two hats, and
  multiplying their probabilities as if independent overstates the slip's
  chances badly. Same-game pairs are refused by default.

  Independence. Even across games the multiplication assumes independence,
  which is approximately true for player props in different stadiums and not
  exactly true (weather systems, league-wide scoring environments). Treat the
  combined probability as an upper bound.

WHAT IT WILL NOT DO

  It will not build a slip out of legs the props engine did not recommend. A
  parlay of hunches is a parlay of hunches at longer odds. If the week produced
  no qualifying single props, the correct output is no slip.
"""
import argparse, itertools, json, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C


def decimal(american):
    a = float(american)
    return 1 + (100 / -a if a < 0 else a / 100)


def to_american(p):
    if p <= 0.0001:
        return 99999
    if p >= 0.9999:
        return -99999
    return int(round(-100 * p / (1 - p))) if p >= 0.5 else int(round(100 * (1 - p) / p))


def same_game(a, b):
    return a.get("game") == b.get("game")


def build(recs, n_legs, allow_same_game=False):
    out = []
    for combo in itertools.combinations(recs, n_legs):
        conflicts = [(x["player"], y["player"]) for x, y in
                     itertools.combinations(combo, 2) if same_game(x, y)]
        if conflicts and not allow_same_game:
            continue

        dec = 1.0
        model = 1.0
        fair = 1.0
        for leg in combo:
            dec *= decimal(leg["best_price"])
            model *= leg["model_prob"] / 100.0
            fair *= leg["fair_prob"] / 100.0

        offered_prob = 1 / dec
        ev = model * dec - 1
        # What the same slip would be worth with no claimed edge at all -- i.e.
        # purely the market's own view. The gap between this and ev is the whole
        # bet; if it is small, the slip is mostly paying vig.
        ev_market_only = fair * dec - 1

        out.append({
            "legs": [{k: leg[k] for k in
                      ("hypothesis", "player", "team", "game", "market",
                       "side", "line", "best_price", "best_book",
                       "fair_prob", "model_prob", "ev_pct")} for leg in combo],
            "n_legs": n_legs,
            "same_game": bool(conflicts),
            "offered_price": to_american(offered_prob),
            "offered_prob": round(offered_prob * 100, 2),
            "model_prob": round(model * 100, 2),
            "fair_prob": round(fair * 100, 2),
            "fair_price": to_american(model),
            "market_only_price": to_american(fair),
            "ev_pct": round(ev * 100, 2),
            "ev_market_only_pct": round(ev_market_only * 100, 2),
            "vig_cost_pct": round((ev - ev_market_only) * 100, 2),
        })
    out.sort(key=lambda s: -s["ev_pct"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--legs", type=int, default=0,
                    help="0 = try 2 and 3")
    ap.add_argument("--max", type=int, default=5, help="slips to keep")
    ap.add_argument("--allow-same-game", action="store_true",
                    help="permit correlated legs; the output says so loudly")
    a = ap.parse_args()

    print(f"== PARLAY — {C.LEAGUE} {C.SEASON} week {a.week} ==")

    rpath = C.STATE / f"recommendations_wk{a.week:02d}.json"
    if not rpath.exists():
        print("  no recommendations file. Run scan.py then recommend.py first.")
        sys.exit(0)
    recs = json.loads(rpath.read_text()).get("recommendations", [])
    print(f"  qualifying single props: {len(recs)}")

    if len(recs) < 2:
        print("\n  Not enough legs for a slip.")
        print("  A parlay built from fewer than two qualifying props is not a")
        print("  parlay, and padding it with legs the engine did not recommend")
        print("  is how a disciplined system becomes a lottery ticket.")
        out = {"league": C.LEAGUE, "season": C.SEASON, "week": a.week,
               "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
               "qualifying_legs": len(recs), "slips": [],
               "note": "fewer than two qualifying single props"}
        p = C.STATE / f"parlays_wk{a.week:02d}.json"
        p.write_text(json.dumps(out, indent=2))
        print(f"\n  wrote {p.relative_to(C.ROOT)}")
        sys.exit(0)

    sizes = [a.legs] if a.legs else [2, 3]
    slips = []
    for n in sizes:
        if n <= len(recs):
            slips += build(recs, n, a.allow_same_game)
    slips = slips[: a.max]

    for s in slips:
        print(f"\n  {s['n_legs']}-leg · {s['offered_price']:+d} "
              f"· EV {s['ev_pct']:+.2f}%"
              + ("  [SAME GAME — correlated]" if s["same_game"] else ""))
        for leg in s["legs"]:
            print(f"     {leg['player']:<20} {leg['market']} {leg['side']} "
                  f"{leg['line']} @ {leg['best_price']:+d} ({leg['best_book']})")
        print(f"     fair {s['fair_price']:+d} · your price "
              f"{s['offered_price']:+d} · vig costs "
              f"{abs(s['vig_cost_pct']):.2f}% of the edge")
        if s["ev_pct"] <= 0:
            print("     NEGATIVE EV — the legs are good and the combination is not.")

    out = {"league": C.LEAGUE, "season": C.SEASON, "week": a.week,
           "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "qualifying_legs": len(recs), "slips": slips}
    p = C.STATE / f"parlays_wk{a.week:02d}.json"
    p.write_text(json.dumps(out, indent=2))
    print(f"\n  wrote {p.relative_to(C.ROOT)}")
    print("\n  Slips are proposals. Nothing is staked, and a slip's result is")
    print("  recorded in slips.csv only — it never credits or debits a")
    print("  hypothesis, because a hypothesis cannot be judged on another")
    print("  leg's luck.")


if __name__ == "__main__":
    main()
