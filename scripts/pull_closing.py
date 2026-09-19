#!/usr/bin/env python3
"""Capture closing lines and compute CLV for every open row. (G2)

This is the highest-value script in the repo. CLV is the primary early signal:
with NFL sample sizes it reveals edge long before W/L can. Run it in the final
window before kickoff, or schedule it.

  python scripts/pull_closing.py --week 1
  python scripts/pull_closing.py --week 1 --manual ROW_ID=-118 ROW_ID2=+104
"""
import argparse, csv, json, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C


def load_bets():
    with open(C.BETS, newline="") as f:
        return list(csv.DictReader(f)), None


def write_bets(rows):
    with open(C.BETS, newline="") as f:
        fieldnames = csv.DictReader(f).fieldnames
    tmp = C.BETS.with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
    tmp.replace(C.BETS)


def apply_close(row, price_close, line_close=None, book=None):
    """Fill closing fields and compute CLV. Never overwrites an existing close."""
    if row.get("price_close"):
        return False
    row["price_close"] = str(price_close)
    if line_close is not None:
        row["line_close"] = str(line_close)
    if book:
        row["book_close"] = book
    row["ts_close"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        row["clv_cents"] = str(C.clv_cents(row["price_stake"], price_close))
        row["clv_pct"] = str(C.clv_pct(row["price_stake"], price_close))
    except Exception as e:
        print(f"  [warn] CLV calc failed for {row['row_id']}: {e}")
    return True


def fetch_closing(week):
    """Pull current lines from the API; treat the last pre-kickoff pull as close."""
    if not C.ODDS_API_KEY:
        print("  [skip] ODDS_API_KEY not set — use --manual, see README")
        return {}
    import urllib.request, urllib.parse, urllib.error
    try:
        url = f"{C.ODDS_BASE}/sports/{C.SPORT}/events?apiKey={C.ODDS_API_KEY}"
        with urllib.request.urlopen(url, timeout=30) as r:
            events = json.loads(r.read())
    except urllib.error.URLError as e:
        print(f"  [warn] {e}")
        return {}
    board = {}
    for ev in events:
        q = urllib.parse.urlencode({
            "apiKey": C.ODDS_API_KEY, "regions": "us",
            "markets": ",".join(C.PROP_MARKETS), "oddsFormat": "american",
            "bookmakers": ",".join(C.BOOKMAKERS),
        })
        u = f"{C.ODDS_BASE}/sports/{C.SPORT}/events/{ev['id']}/odds?{q}"
        try:
            with urllib.request.urlopen(u, timeout=30) as r:
                data = json.loads(r.read())
        except urllib.error.URLError:
            continue
        for bm in data.get("bookmakers", []):
            for mk in bm.get("markets", []):
                for oc in mk.get("outcomes", []):
                    key = (oc.get("description", ""), mk["key"], oc.get("name", ""))
                    board[key] = (oc.get("price"), oc.get("point"), bm["key"])
    # snapshot for audit
    C.RAW.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    (C.RAW / f"{C.SEASON}_wk{week:02d}_props_close_{ts}.json").write_text(
        json.dumps({str(k): v for k, v in board.items()}, indent=2))
    print(f"  closing board: {len(board)} outcomes")
    return board


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, required=True)
    ap.add_argument("--manual", nargs="*", default=[],
                    help="ROW_ID=PRICE pairs when no API key")
    a = ap.parse_args()
    print(f"== CLOSING CAPTURE — {C.SEASON} week {a.week} ==")

    rows, _ = load_bets()
    target = [r for r in rows if str(r["week"]) == str(a.week)
              and r["ts_stake"] and not r["price_close"]]
    print(f"  rows awaiting a close: {len(target)}")
    if not target:
        print("  nothing to do")
        return

    manual = {}
    for pair in a.manual:
        k, v = pair.split("=")
        manual[k] = v

    board = fetch_closing(a.week) if not manual else {}
    filled = 0
    for r in target:
        if r["row_id"] in manual:
            filled += apply_close(r, manual[r["row_id"]], book="manual")
            continue
        key = (r["player"], r["prop_type"], r["side"])
        if key in board:
            price, point, bm = board[key]
            filled += apply_close(r, price, point, bm)
        else:
            print(f"  [miss] no close found for {r['row_id']} {r['player']} "
                  f"{r['prop_type']} {r['side']}")

    write_bets(rows)
    print(f"\n  closed {filled} row(s)")
    got = [r for r in rows if r.get("clv_cents")]
    if got:
        vals = [float(r["clv_cents"]) for r in got if r["clv_cents"]]
        if vals:
            print(f"  mean CLV across ledger: {sum(vals)/len(vals):+.2f} cents "
                  f"(n={len(vals)})")
            print("  NOTE: mean CLV is the primary early signal. Positive and")
            print("  persistent = real edge, even at a middling hit rate.")


if __name__ == "__main__":
    main()
