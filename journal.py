#!/usr/bin/env python3
"""The journal — decisions and reasoning, dated and kept.

The bet ledger records what was risked. The confidence ledger records what a
result taught. Neither records the conversation that produced the decision:
why a hypothesis was amended, what was argued and rejected, what you believed
at the time and turned out to be wrong about.

That third record is the one that makes a season legible in March. It is also
the one that never gets written unless writing it is one line of typing.

  python scripts/journal.py --add decision "Cut H4" "Weakest structure..."
  python scripts/journal.py --list
"""
import argparse, csv, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

COLS = ["entry_id", "ts", "season", "week", "kind", "subject", "body", "refs"]
KINDS = ["decision", "discussion", "observation", "amendment", "correction"]


def path():
    return C.LEDGER / "journal.csv"


def read():
    p = path()
    if not p.exists():
        return []
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def add(kind, subject, body, week=None, refs=""):
    rows = read()
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "entry_id": f"J{len(rows) + 1:04d}",
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "season": str(C.SEASON),
        "week": str(week or C.default_week()),
        "kind": kind,
        "subject": " ".join(str(subject).split()),
        "body": " ".join(str(body).split()),
        "refs": refs,
    }
    rows.append(row)
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--add", nargs=3, metavar=("KIND", "SUBJECT", "BODY"))
    ap.add_argument("--week", type=int)
    ap.add_argument("--refs", default="")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.add:
        kind, subject, body = a.add
        if kind not in KINDS:
            print(f"kind must be one of: {', '.join(KINDS)}")
            sys.exit(1)
        r = add(kind, subject, body, a.week, a.refs)
        print(f"logged {r['entry_id']} — {r['kind']}: {r['subject']}")
    else:
        rows = read()
        print(f"journal: {len(rows)} entr(ies)")
        for r in rows[-20:]:
            print(f"  {r['entry_id']}  wk{r['week']:>2}  {r['kind']:<12} {r['subject']}")


if __name__ == "__main__":
    main()
