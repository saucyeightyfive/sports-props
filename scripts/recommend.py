#!/usr/bin/env python3
"""Recommendations — candidates, priced and ranked.

The scanner says which triggers fired. This says whether any of them is worth
betting, and by how much. The difference matters: a fired trigger on a bad price
is not a recommendation, and a system that cannot say "real read, wrong price"
will talk you into the wrong price every week.

  python scripts/recommend.py --week 2
  python scripts/recommend.py --week 2 --show-rejected

HOW AN EDGE IS COMPUTED

  1. De-vig the market. Both sides of the same line, across your books, give an
     implied probability pair that sums to more than 1. Normalising it yields
     the market's own honest estimate -- the single best probability available
     to anyone without a model.
  2. Add the hypothesis's CLAIMED EDGE. This is the whole bet: a stated,
     falsifiable number saying how far the market is wrong and which way. It
     lives in hypotheses.yaml and is ratified by the user, never invented here.
  3. Price it against the BEST available number across books, which is often a
     different book than the one used to de-vig.
  4. Report expected value. Negative EV is reported, not hidden -- "the read is
     real and the price is not there" is a valid and frequent output.

WHAT THIS DOES NOT DO

  It does not stake. Sizing is zero for anything not PROVEN, no exceptions, and
  the console enforces that again at logging time. It does not invent an edge
  for a hypothesis that has not claimed one. It does not recommend anything
  from a hypothesis the scanner marked UNEVALUABLE.
"""
import argparse, json, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
from report import read_yaml
from scan import latest_snapshot, board_rows


# --------------------------------------------------------------------------- odds
def implied(american):
    a = float(american)
    return (-a) / ((-a) + 100) if a < 0 else 100 / (a + 100)


def to_american(p):
    if p <= 0.0001:
        return 99999
    if p >= 0.9999:
        return -99999
    return int(round(-100 * p / (1 - p))) if p >= 0.5 else int(round(100 * (1 - p) / p))


def decimal(american):
    a = float(american)
    return 1 + (100 / -a if a < 0 else a / 100)


def devig(rows, player, market, line):
    """Market's own probability for the OVER at this line, vig removed.

    Uses the tightest two-sided pair available: the book whose over/under sum
    is closest to 1 is the one carrying the least vig, and therefore the most
    honest estimate. Books with only one side posted are useless here.
    """
    pairs = {}
    for r in rows:
        if r["player"] != player or r["market"] != market or r["line"] != line:
            continue
        if r["price"] is None:
            continue
        pairs.setdefault(r["book"], {})[r["side"]] = r["price"]
    best = None
    for book, sides in pairs.items():
        if "over" not in sides or "under" not in sides:
            continue
        po, pu = implied(sides["over"]), implied(sides["under"])
        total = po + pu
        if best is None or total < best["hold"] + 1:
            best = {"book": book, "hold": total - 1,
                    "fair_over": po / total, "over": sides["over"],
                    "under": sides["under"]}
    return best


def best_available(rows, player, market, line, side):
    cands = [r for r in rows if r["player"] == player and r["market"] == market
             and r["line"] == line and r["side"] == side and r["price"] is not None]
    return max(cands, key=lambda r: r["price"]) if cands else None


# --------------------------------------------------------------------------- core
def price_candidate(c, rows, edge):
    """Return a recommendation dict, or a rejection with a stated reason."""
    market, line, side = c["market"], c["line"], c["side"]
    mk = devig(rows, c["player"], market, line)
    if not mk:
        return {"verdict": "NO PRICE", "reason":
                "no book posts both sides of this line, so the market's own "
                "estimate cannot be recovered and there is nothing to measure "
                "an edge against", **c}

    fair = mk["fair_over"] if side == "over" else 1 - mk["fair_over"]
    model = min(0.97, max(0.03, fair + edge["value"] / 100.0))

    b = best_available(rows, c["player"], market, line, side)
    if not b:
        return {"verdict": "NO PRICE", "reason": f"no {side} price posted", **c}

    dec = decimal(b["price"])
    ev = model * (dec - 1) - (1 - model)
    breakeven = 1 / dec

    rec = {**c,
           "book_devig": mk["book"], "hold": round(mk["hold"] * 100, 2),
           "fair_prob": round(fair * 100, 2),
           "fair_price": to_american(fair),
           "claimed_edge": edge["value"],
           "model_prob": round(model * 100, 2),
           "best_price": b["price"], "best_book": b["book"],
           "breakeven_prob": round(breakeven * 100, 2),
           "ev_pct": round(ev * 100, 2)}

    if ev <= 0:
        rec["verdict"] = "TOO THIN"
        rec["reason"] = (
            f"the read is real but the price is not. Even granting the full "
            f"{edge['value']} points this hypothesis claims, the model gets to "
            f"{rec['model_prob']}% and the price needs {rec['breakeven_prob']}% "
            f"to break even. Prop vig here is {rec['hold']}%.")
    else:
        rec["verdict"] = "RECOMMEND"
        rec["reason"] = (
            f"market fair is {rec['fair_prob']}%; the hypothesis claims "
            f"{edge['value']} points on top, giving {rec['model_prob']}%. "
            f"Best price {b['price']:+d} at {b['book']} breaks even at "
            f"{rec['breakeven_prob']}%, leaving {rec['ev_pct']}% expected value.")
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--show-rejected", action="store_true")
    a = ap.parse_args()

    print(f"== RECOMMEND — {C.LEAGUE} {C.SEASON} week {a.week} ==")

    cpath = C.STATE / f"candidates_wk{a.week:02d}.json"
    if not cpath.exists():
        print(f"  no scan for week {a.week}. Run scan.py first.")
        sys.exit(0)
    scan = json.loads(cpath.read_text())
    rows = board_rows(latest_snapshot(a.week, "props_open"))
    hyp = {h["id"]: h for h in (read_yaml(C.HYPOTHESES).get("hypotheses") or [])}

    recs, thin, noprice, skipped = [], [], [], []
    for r in scan["results"]:
        h = hyp.get(r["id"]) or {}
        edge = h.get("claimed_edge") or {}
        if r["verdict"] == "UNEVALUABLE":
            skipped.append((r["id"], "hypothesis could not be evaluated"))
            continue
        if edge.get("value") in (None, ""):
            if r["candidates"]:
                skipped.append((r["id"], "no claimed edge — nothing to rank by"))
            continue
        if edge.get("unit") != "probability_points":
            skipped.append((r["id"],
                            f"edge is in {edge.get('unit')}, measured on the "
                            f"ledger rather than priced here"))
            continue
        for c in r["candidates"]:
            out = price_candidate(c, rows, edge)
            {"RECOMMEND": recs, "TOO THIN": thin,
             "NO PRICE": noprice}[out["verdict"]].append(out)

    recs.sort(key=lambda r: -r["ev_pct"])

    if recs:
        print(f"\n  {len(recs)} RECOMMENDATION(S)\n")
        for r in recs:
            tier = (hyp.get(r["hypothesis"], {}).get("tier") or "SHADOW")
            stake = "0u (SHADOW — logged and graded, no money)" \
                if tier != "PROVEN" else "size per bankroll rule"
            print(f"  {r['hypothesis']}  {r['player']} ({r['team']}) — {r['game']}")
            print(f"     {r['market']} {r['side']} {r['line']} @ "
                  f"{r['best_price']:+d} ({r['best_book']})")
            print(f"     fair {r['fair_prob']}%  +{r['claimed_edge']} claimed  "
                  f"= {r['model_prob']}%  | breakeven {r['breakeven_prob']}%  "
                  f"| EV {r['ev_pct']:+.2f}%")
            print(f"     stake: {stake}\n")
    else:
        print("\n  No recommendation. That is a valid and frequent output.\n")

    if thin:
        print(f"  {len(thin)} READ(S) TOO THIN FOR THE PRICE")
        for r in thin:
            print(f"     {r['player']} {r['market']} {r['side']} {r['line']} — "
                  f"model {r['model_prob']}% vs breakeven {r['breakeven_prob']}% "
                  f"(vig {r['hold']}%)")
        print()
    if noprice and a.show_rejected:
        print(f"  {len(noprice)} with no usable two-sided market")
        for r in noprice:
            print(f"     {r['player']} {r['market']} {r['line']}")
        print()
    if skipped:
        print("  not priced:")
        for hid, why in skipped:
            print(f"     {hid} — {why}")

    out = {"league": C.LEAGUE, "season": C.SEASON, "week": a.week,
           "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "recommendations": recs, "too_thin": thin,
           "no_price": noprice, "skipped": skipped}
    path = C.STATE / f"recommendations_wk{a.week:02d}.json"
    path.write_text(json.dumps(out, indent=2))
    print(f"\n  wrote {path.relative_to(C.ROOT)}")
    print("\n  Nothing here is staked. Every recommendation is a proposal: audit "
          "it,\n  amend the line or price to what your book actually shows, or "
          "dismiss it\n  with a reason. The dismissal is signal too.")


if __name__ == "__main__":
    main()
