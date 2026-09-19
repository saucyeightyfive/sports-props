# NFL Props — empirical inference engine

A disciplined system for testing NFL player-prop hypotheses. Starts with **zero
hypotheses and a zero record**; it inherits a method, not a book.

`CLAUDE.md` is the constitution — Claude Code reads it every session, so there is
no prompt to paste. Read it before changing anything.

## Setup

```bash
git init && git add -A && git commit -m "scaffold"
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export ODDS_API_KEY=...        # https://the-odds-api.com
export NFL_SEASON=2026
```

`nfl_data_py` (schedules, injuries, snap counts, weekly stats) is free.
The Odds API free tier covers live lines; **historical/closing endpoints are
paid** — that tier is what makes CLV reliable, and CLV is the point.

## Weekly loop

```bash
python scripts/pull_slate.py   --week 1   # Thu: slate, injuries, usage, open props
# analyze -> verify underlying (G4) -> decompose (G3) -> log rows to bets.csv
python scripts/pull_closing.py --week 1   # Sun pre-kickoff: closing lines -> CLV
python scripts/grade.py        --week 1   # Tue: results -> margin vs fair
python scripts/report.py       --week 1   # dashboard
```

No API key? Both closing capture and grading accept manual values:

```bash
python scripts/pull_closing.py --week 1 --manual W1R001=-118 W1R002=+104
python scripts/grade.py        --week 1 --manual W1R001=78.5 W1R002=4
```

## The dashboard

```bash
python scripts/report.py --week 1            # build from real ledger data
python scripts/report.py --week 1 --demo     # preview the layout with fake rows
python scripts/validate_html.py dashboards/nfl_2026_wk01.html
```

Seven tabs: **WEEK** (this week's rows + the discipline guard), **PERFORMANCE**
(CLV-led stat cards, weekly log), **CONFIDENCE** (what's awaiting your
ratification, per-hypothesis state), **POST-HOC** (last week graded vs fair),
**HYPOTHESES** (registry cards), **TRACKING** (CLV by hypothesis, mechanism
observations), **METHODOLOGY** (rules + amendment log).

`report.py` **self-validates and refuses to ship a broken build** — four
structural checks (tag balance, tabs match content divs, jumplinks resolve, no
undefined badge classes). A non-zero exit means the file isn't fit to open.

Front-end files:

```
web/theme.css           design system — edit here to restyle everything
scripts/components.py   badge / table / alert / panel / tabs builders
scripts/report.py       assembles the seven tabs from the ledgers
scripts/validate_html.py  the four checks
```

To restyle, change the `:root` tokens in `web/theme.css`; every component reads
from them. To add a tab, write a `tab_*()` function and register it in `build()`
— the validator will catch a mismatch between the button and the content div.

## Logging a row

Append to `state/ledger/bets.csv`. At stake-time fill: `row_id, season, week,
date, game, player, team, opponent, position, prop_type, side, line_stake,
price_stake, book_stake, ts_stake, hypothesis, tier_at_stake,
expression_conditions, conjunction, status_at_stake, stake_units`.

`stake_units = 0` means a shadow row: fully tracked and graded, no money. Every
new hypothesis lives here until it earns otherwise.

The rest (`line_close, price_close, clv_*, actual_result, margin_vs_fair,
outcome, pnl_units`) is filled by the scripts.

## Why the ledger is CSV in git

Every change to the record is a commit, so it is provable that no number was
retro-adjusted. For a system whose whole ethos is "don't let the record flatter
you," that audit trail beats query speed. Never rewrite history in
`state/ledger/` — append corrections with a note.

## Automation boundary

Scheduled jobs (`.github/workflows/weekly.yml`) handle **collection**: slates,
injuries, closing lines, grading, dashboards. This exists because missed weeks
were the root cause of every data gap in the predecessor project.

**Judgment is never automated.** Hypothesis definition, tier changes, and
PROPOSED → RATIFIED stay manual, permanently.

## First session

Open Claude Code in this directory and ask it to propose the starter hypothesis
framework. It should produce 3–5 falsifiable candidates — each with a trigger,
the underlying metrics that verify it, the prop expression, why the market might
misprice it, and what would disprove it — all opening as SHADOW. Ratify before
touching a slate.
