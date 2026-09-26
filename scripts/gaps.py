#!/usr/bin/env python3
"""Collection gaps — recorded, not shrugged off.

Missed weeks were the root cause of every data gap in the predecessor project,
and on 2026-09-26 this repo reproduced the failure exactly: the Week 3 prop
board came back empty, pull_slate wrote no file, the run exited zero and went
green, and the hole sat unnoticed for two days while the dashboard reported
"Board lines: 0" in small grey text.

A gap is now a row in the ledger. It appears as a red banner on the dashboard
for the affected week and it never disappears on its own -- the record shows
what was collected AND what was missed, because a week with no board is not the
same as a week with no candidates, and a system that cannot tell those apart
will read its own blind spots as dry weeks.

  from gaps import record, read_all
  record("props_open", week, "empty", "all 29 event calls returned nothing")
"""
import csv
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C

COLS = ["gap_id", "ts", "season", "week", "kind", "reason", "detail", "resolved"]

# reason -> what the user should actually do about it
REMEDY = {
    "no_key": "ODDS_API_KEY is not set in the workflow secrets.",
    "fetch_failed": "The odds provider could not be reached or refused the "
                    "request — most often an exhausted quota on the free tier.",
    "empty": "The provider answered but returned nothing usable. Check the "
             "account's remaining request credits.",
    "source_unavailable": "The upstream data source could not be loaded.",
}


def path():
    return C.LEDGER / "gaps.csv"


def read_all():
    p = path()
    if not p.exists():
        return []
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def for_week(week):
    return [g for g in read_all()
            if str(g.get("week")) == str(week) and g.get("resolved") != "yes"]


def record(kind, week, reason, detail=""):
    """Append a gap. Idempotent per (week, kind, reason) so a retrying schedule
    does not pile up duplicate rows for one outage."""
    rows = read_all()
    for g in rows:
        if (str(g.get("week")) == str(week) and g.get("kind") == kind
                and g.get("reason") == reason and g.get("resolved") != "yes"):
            return g
    row = {
        "gap_id": f"G{len(rows) + 1:04d}",
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "season": str(C.SEASON),
        "week": str(week),
        "kind": kind,
        "reason": reason,
        "detail": " ".join(str(detail).split())[:300],
        "resolved": "",
    }
    rows.append(row)
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return row


def resolve(kind, week):
    """Mark a gap closed once the same collection succeeds later. Closing is
    recorded rather than deleted: the week still had a window where the data
    did not exist, and a late capture is not the same as an on-time one."""
    rows = read_all()
    hit = False
    for g in rows:
        if (str(g.get("week")) == str(week) and g.get("kind") == kind
                and g.get("resolved") != "yes"):
            g["resolved"] = "yes"
            g["detail"] = (g.get("detail", "") +
                           f" | resolved {datetime.now(timezone.utc):%Y-%m-%dT%H:%MZ}")[:300]
            hit = True
    if hit:
        with open(path(), "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS, extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
    return hit


def announce(row):
    """Print in a shape GitHub Actions surfaces as an annotation."""
    print(f"::error::COLLECTION GAP — {C.LEAGUE} week {row['week']}: "
          f"{row['kind']} ({row['reason']}). {REMEDY.get(row['reason'], '')}")
    print(f"  !! collection gap recorded: {row['gap_id']} "
          f"{row['kind']}/{row['reason']}")
    print(f"  !! {REMEDY.get(row['reason'], '')}")
    if row.get("detail"):
        print(f"  !! {row['detail']}")


if __name__ == "__main__":
    gs = read_all()
    print(f"gaps: {len(gs)}")
    for g in gs:
        mark = "closed" if g.get("resolved") == "yes" else "OPEN"
        print(f"  {g['gap_id']}  wk{g['week']:>2}  {mark:<6} "
              f"{g['kind']}/{g['reason']}  {g['detail'][:60]}")
