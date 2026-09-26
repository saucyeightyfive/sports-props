#!/usr/bin/env python3
"""Ledger writes from anywhere — log a pick, record a close, ratify a class.

The engine has produced recommendations for three weeks into an empty ledger,
because the only way to log one was app.py on a machine that could not run it.
A system whose write path is unreachable does not collect data; it produces
opinions and forgets them.

This is the write path with no local install: it runs in CI, driven from the
Actions tab, so logging a pick is a browser form.

  python scripts/ledger.py list
  python scripts/ledger.py log --pick 1 --stake 0
  python scripts/ledger.py log --pick all
  python scripts/ledger.py log --pick 1 --line 5.5 --price -115 --book fanduel
  python scripts/ledger.py close --row W3R001 --line 5.5 --price -130
  python scripts/ledger.py ratify --row W3R001 --held HELD --class FRONTIER
  python scripts/ledger.py show --week 3

--pick N takes the Nth recommendation from this week's recommendations file,
so the common case is one number. --pick all logs every one of them, which is
the right default while every hypothesis is SHADOW: a shadow row costs nothing
and a week not logged is a week that teaches nothing.

--line/--price override the captured board with what your book actually showed,
because the board is a reference and your book is the authority (CLAUDE.md).
"""
import argparse, csv, json, sys
from datetime import datetime, timezone, date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

CLASSES = ["CONFIRMED", "GAMBLED", "TEACHING", "FRONTIER"]
HELD = ["HELD", "FAILED", "UNCLEAR"]


def read(path, cols=None):
    p = Path(path)
    if not p.exists():
        return [], list(cols or [])
    with open(p, newline="") as f:
        r = csv.DictReader(f)
        return list(r), (r.fieldnames or list(cols or []))


def write(path, fields, rows):
    tmp = Path(path).with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def tier_of(hid):
    try:
        import yaml
        doc = yaml.safe_load(C.HYPOTHESES.read_text()) or {}
    except Exception:
        return "SHADOW"
    for h in (doc.get("hypotheses") or []):
        if h.get("id") == hid:
            return h.get("tier", "SHADOW")
    return "NONE" if hid == "NONE" else "SHADOW"


# --------------------------------------------------------------------------- log
def load_recs(week):
    recs_path = C.STATE / f"recommendations_wk{week:02d}.json"
    if not recs_path.exists():
        sys.exit(f"no recommendations for week {week}; run scan.py then recommend.py")
    doc = json.loads(recs_path.read_text())
    return doc.get("recommendations", []), doc


def show_recs(week, recs):
    print(f"week {week} has {len(recs)} recommendation(s):")
    for i, r in enumerate(recs, 1):
        print(f"  {i}. {r['player']:<20} {r['market']} {r['side']} {r['line']} "
              f"@ {r['best_price']:+d} ({r['best_book']})  EV {r['ev_pct']:+.2f}% "
              f"(hyp {r['ev_hypothesis_pct']:+.2f} / shop {r['ev_shopping_pct']:+.2f}) "
              f"{r['hypothesis']}  — {r['game']}")


def cmd_list(a):
    week = a.week or C.default_week()
    recs, doc = load_recs(week)
    if not recs:
        print(f"week {week} produced no recommendations. Nothing to log is a "
              f"valid output — do not reach for one.")
    else:
        show_recs(week, recs)
    for c in doc.get("correlated_games", []):
        print(f"\n  CORRELATION WARNING — {c['reads']} reads from {c['game']}. "
              f"Not independent evidence; never on one slip.")
    bets, _ = read(C.BETS)
    have = {(b.get("player"), b.get("prop_type"), b.get("side"), b.get("line_stake"))
            for b in bets if str(b.get("week")) == str(week)}
    if have:
        print(f"\n  already logged this week: {len(have)} row(s)")


def _log_one(r, a, week, bets, fields):
    """Build and append one bet row. Returns the row, or None if a duplicate."""
    line = str(a.line if a.line is not None else r["line"])
    side = r["side"]
    for b in bets:
        if (str(b.get("week")) == str(week) and b.get("player") == r["player"]
                and b.get("prop_type") == r["market"] and b.get("side") == side
                and b.get("line_stake") == line):
            print(f"  skip {r['player']} {r['market']} {side} {line} — already "
                  f"logged as {b['row_id']}. Corrections are appended with a "
                  f"note, never duplicated.")
            return None

    hid = r["hypothesis"]
    tier = tier_of(hid)
    stake = float(a.stake or 0)
    if stake > 0 and tier != "PROVEN":
        sys.exit(f"{hid} is {tier}. Only a PROVEN hypothesis takes money. Log it "
                 f"at 0 units and let it earn the tier — this is refused, not "
                 f"warned about, on purpose.")

    n = sum(1 for b in bets if str(b.get("week")) == str(week)) + 1
    row = {k: "" for k in fields}
    row.update({
        "row_id": f"W{week}R{n:03d}", "season": str(C.SEASON), "week": str(week),
        "date": date.today().isoformat(), "game": r["game"],
        "player": r["player"], "team": r["team"],
        "prop_type": r["market"], "side": side,
        # Your book is the authority; the captured board is a reference.
        "line_stake": line,
        "price_stake": str(a.price if a.price is not None else r["best_price"]),
        "book_stake": a.book or r["best_book"],
        "ts_stake": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hypothesis": hid, "tier_at_stake": tier,
        "status_at_stake": a.status,
        "stake_units": str(stake),
        "slip_id": a.slip or "",
        "expression_conditions": " | ".join(filter(None, [
            f"{r['player']} plays a normal snap count",
            (f"absorbs share vacated by {r['vacated_by']}"
             if r.get("vacated_by") else None),
            "targets convert at his established rate"])),
        "conjunction": "true",
        "thesis": a.thesis or (
            f"{r['player']} absorbs targets vacated by {r.get('vacated_by','?')} "
            f"({r.get('vacated_share',0):.0%} share, {r.get('vacated_status','')}). "
            f"Consensus fair {r['fair_prob']}%, model {r['model_prob']}% on "
            f"{hid}'s claimed {r['claimed_edge']} points. Of {r['ev_pct']}% EV, "
            f"{r['ev_hypothesis_pct']}% is the hypothesis and "
            f"{r['ev_shopping_pct']}% is the price."),
        "notes": a.note or "",
    })
    bets.append(row)
    print(f"logged {row['row_id']}: {row['player']} {row['prop_type']} "
          f"{row['side']} {row['line_stake']} @ {row['price_stake']} "
          f"({row['book_stake']}) · {hid} · "
          f"{'SHADOW 0u' if not stake else str(stake) + 'u'}")
    return row


def cmd_log(a):
    week = a.week or C.default_week()
    recs, doc = load_recs(week)
    if not recs:
        sys.exit(f"week {week} produced no recommendations. Nothing to log is a "
                 f"valid output — do not reach for one.")

    pick = str(a.pick).strip().lower()
    if pick == "all":
        chosen = list(recs)
        if a.line is not None or a.price is not None or a.book:
            sys.exit("--line/--price/--book override a single row's number and "
                     "cannot apply to --pick all. Log that one by its number.")
    else:
        try:
            i = int(pick)
        except ValueError:
            show_recs(week, recs)
            sys.exit(f"--pick must be 1..{len(recs)} or 'all'")
        if not (1 <= i <= len(recs)):
            show_recs(week, recs)
            sys.exit(f"--pick must be 1..{len(recs)} or 'all'")
        chosen = [recs[i - 1]]

    bets, fields = read(C.BETS)
    written = [r for r in (_log_one(c, a, week, bets, fields) for c in chosen) if r]
    if not written:
        print("nothing new to log.")
        return
    write(C.BETS, fields, bets)

    if not float(a.stake or 0):
        print("  Zero stake. Fully tracked and graded; no money. This is the "
              "point of a shadow row.")
    games = {}
    for r in written:
        games[r["game"]] = games.get(r["game"], 0) + 1
    for g, n in games.items():
        if n > 1:
            print(f"\n  CORRELATION WARNING — {n} rows logged from {g}. They are "
                  f"one read's worth of evidence, not {n}. Never on one slip.")


# ------------------------------------------------------------------------- close
def cmd_close(a):
    bets, fields = read(C.BETS)
    row = next((b for b in bets if b["row_id"] == a.row), None)
    if not row:
        sys.exit(f"no row {a.row}")
    if row.get("price_close"):
        sys.exit(f"{a.row} already closed at {row['price_close']}. Corrections "
                 f"are appended with a note, never edited in place.")
    row["price_close"] = str(a.price)
    if a.line is not None:
        row["line_close"] = str(a.line)
    row["book_close"] = a.book or "manual"
    row["ts_close"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    row["clv_cents"] = str(C.clv_cents(row["price_stake"], a.price))
    row["clv_pct"] = str(C.clv_pct(row["price_stake"], a.price))
    write(C.BETS, fields, bets)
    print(f"{a.row} closed at {a.price} — CLV {row['clv_cents']}")


# ------------------------------------------------------------------------ ratify
def cmd_ratify(a):
    bets, bf = read(C.BETS)
    row = next((b for b in bets if b["row_id"] == a.row), None)
    if not row:
        sys.exit(f"no row {a.row}")
    if a.held:
        row["mechanism_held"] = a.held
        write(C.BETS, bf, bets)
        print(f"{a.row}: thesis marked {a.held}")
    if not a.klass:
        return
    if not row.get("outcome"):
        sys.exit(f"{a.row} is not graded yet — run grade.py first. A class "
                 f"before a result is a guess.")
    cls, cf = read(C.CLASSIFICATIONS)
    cf = cf or ["class_id", "date_proposed", "season", "week", "row_id",
                "hypothesis", "proposed_class", "rationale", "status",
                "date_ratified", "ratified_class", "user_note"]
    cls.append({
        "class_id": f"C{len(cls) + 1:04d}",
        "date_proposed": date.today().isoformat(),
        "season": str(C.SEASON), "week": row.get("week"),
        "row_id": a.row, "hypothesis": row.get("hypothesis"),
        "proposed_class": a.klass, "rationale": a.note or "",
        "status": "RATIFIED", "date_ratified": date.today().isoformat(),
        "ratified_class": a.klass, "user_note": a.note or "",
    })
    write(C.CLASSIFICATIONS, cf, cls)
    print(f"{a.row} ratified {a.klass}")


# -------------------------------------------------------------------------- show
def cmd_show(a):
    week = a.week or C.default_week()
    bets, _ = read(C.BETS)
    rows = [b for b in bets if str(b.get("week")) == str(week)]
    print(f"week {week}: {len(rows)} row(s)")
    for b in rows:
        print(f"  {b['row_id']}  {b['player']:<20} {b['prop_type']} {b['side']} "
              f"{b['line_stake']} @ {b['price_stake']}  "
              f"close={b.get('price_close') or '—'}  clv={b.get('clv_cents') or '—'}  "
              f"{b.get('outcome') or 'ungraded'}  {b['hypothesis']}")
    live = [b for b in bets if float(b.get("stake_units") or 0) > 0]
    pnl = sum(float(b.get("pnl_units") or 0) for b in live)
    clvs = [float(b["clv_cents"]) for b in bets if b.get("clv_cents")]
    mclv = f"{sum(clvs)/len(clvs):+.2f} over {len(clvs)} closed row(s)" if clvs \
        else "no closes captured yet — run pull_closing.py before kickoff"
    print(f"\n  all-time: {len(bets)} row(s), {len(live)} staked, "
          f"P&L {pnl:+.2f}u, mean CLV {mclv}")
    if not live:
        print("  P&L is 0.00u because every row is shadow. That is correct until "
              "a\n  hypothesis is PROVEN — what accumulates now is CLV and margin,\n"
              "  not money.")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("list")
    p.add_argument("--week", type=int)
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("log")
    p.add_argument("--pick", required=True,
                   help="recommendation number, or 'all'")
    p.add_argument("--week", type=int)
    p.add_argument("--line", type=float)
    p.add_argument("--price", type=int)
    p.add_argument("--book")
    p.add_argument("--stake", type=float, default=0)
    p.add_argument("--status", default="PROJECTED",
                   choices=["PROJECTED", "CONFIRMED"])
    p.add_argument("--slip")
    p.add_argument("--thesis")
    p.add_argument("--note")
    p.set_defaults(fn=cmd_log)

    p = sub.add_parser("close")
    p.add_argument("--row", required=True)
    p.add_argument("--price", type=int, required=True)
    p.add_argument("--line", type=float)
    p.add_argument("--book")
    p.set_defaults(fn=cmd_close)

    p = sub.add_parser("ratify")
    p.add_argument("--row", required=True)
    p.add_argument("--held", choices=HELD)
    p.add_argument("--class", dest="klass", choices=CLASSES)
    p.add_argument("--note")
    p.set_defaults(fn=cmd_ratify)

    p = sub.add_parser("show")
    p.add_argument("--week", type=int)
    p.set_defaults(fn=cmd_show)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
