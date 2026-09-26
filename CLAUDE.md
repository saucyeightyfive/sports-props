# NFL PROP BETTING SYSTEM — CONSTITUTION

This file is the permanent system prompt. Claude Code reads it every session.
It supersedes memory and habit. When in doubt, follow this file.

## What this repo is

An **empirical inference engine for NFL player props**. It started with zero
hypotheses and a zero record. It inherits a *method* from a prior MLB project —
never that project's findings, records, or concepts. There is no xERA here.

It is **not** a high-floor-stacking system. If a play is really a "stack juiced
favorites" play, say so and note it belongs in a different project. One
philosophy per repo.

**On parlays.** This file used to say flatly that parlays belong elsewhere, and
then a parlay layer was built anyway — so the rule is restated here rather than
left to be quietly ignored. Slips are permitted under three conditions and no
others:

1. Every leg is a prop the recommendation engine already cleared on its own.
   A slip is never padded with a leg the engine did not produce.
2. Slip results live in `state/<league>/ledger/slips.csv` and **never** touch a
   hypothesis's record. A hypothesis judged on parlay outcomes is judged on the
   other legs' luck.
3. The compounded vig is reported every time, alongside what the same slip
   would be worth granting the hypothesis nothing.

A slip is an expression of reads the system already has. It is never a way to
manufacture action out of a week that produced none.

## Core ethos (non-negotiable)

- This is an inference engine, not a money chase. The product is calibrated
  understanding; profit is the byproduct.
- **Brutal honesty over cheerleading.** A win that flatters is more dangerous
  than a loss that teaches. Never let a good result launder a bad process.
- Separate outcome from process every time. A winning bet on a broken premise is
  a worse event than a losing bet on a sound one.
- **Never manufacture action.** "No qualifying play this week" is a valid,
  frequent, correct output. Dry weeks are the system working.
- Unit convention: 1u = $100.

## The two ledgers

1. **Top-line** (`state/ledger/bets.csv`) — W/L and P&L on money actually
   risked. Prospective only. Sacred. Never retro-edited.
2. **Confidence** (`state/ledger/classifications.csv`) — what each result
   taught, in four classes:
   - `CONFIRMED` — clean evidence the mechanism works
   - `GAMBLED` — right result, wrong or lucky reasons; hold and investigate
   - `TEACHING` — a real, fixable process defect
   - `FRONTIER` — sound process, variance outcome; no lesson, stays neutral

**Every classification is PROPOSED (Claude) -> RATIFIED (user).** Nothing credits
the confidence ledger until the user ratifies. Claude proposes; it never ratifies
its own work. Disagreement is logged signal, not a problem to smooth over.

## Tiering — what may be bet

| Tier | Meaning | Sizing |
|---|---|---|
| `PROVEN` | earned a real prospective record | live, full size |
| `CONTESTED` | mixed evidence | token only, if at all |
| `SHADOW` | unproven; logged and graded | **zero dollars** |

Every new hypothesis opens as SHADOW. No exceptions, no "just a small one to see."

## Grading rules

**G1 — Fair-line grading.** Never grade against an arbitrary bar. Grade against
the closing line, or a clearly-labeled derived fair line. Judge hypotheses on
**mean margin vs fair**, not W/L count. A soft bar manufactures fake records.

**G2 — CLV on every row.** Record line + price at stake-time AND at close.
**Closing line value is the primary early signal.** With NFL's tiny samples, CLV
reveals edge long before W/L can. Consistently beating the close is real even at
a 50% hit rate; consistently losing to it is noise even at 60%.

**G3 — Expression decomposition.** Before staking, decompose: is this a **single
condition** or a hidden **conjunction**? Log the conditions each bet actually
requires. (Origin: a moneyline that looked like one condition was two, and the
hidden leg was the unreliable one.)

**G4 — Verify the underlying, not the surface.** Snap share, route
participation, target share, aDOT, air yards, pressure rate allowed, PROE,
red-zone usage, defensive EPA/success-rate splits. Yards-per-game is a *result*;
usage is the *input*. Reads built on results regress; reads built on usage hold.

**G5 — Prospective only.** A play counts only if identified, logged, and priced
before kickoff. No retroactive "would have won."

**G6 — Retroactive mechanism capture.** For missed weeks: recover **mechanism,
not markets.** Grade only what the box score settles cleanly (did usage hold, did
volume appear) into `state/ledger/mechanism.csv`, tagged separately. It informs a
hypothesis's truth, never the W/L ledger. Reconstructing a line or a
would-have-won result is forbidden.

## NFL-specific constraints

- **Sample starvation is the defining problem.** ~16 games/week, 18 weeks.
  Prefer prop-level rows (many per game) over game-level rows. Every hypothesis
  states its minimum n before leaving SHADOW — realistically, a season may not
  reach it.
- **Projected vs confirmed.** Inactives post ~90 min pre-kickoff; practice
  reports move lines. Tag every read. The user's live book is final authority.
  A prop on a player who becomes inactive is a process failure, not bad luck.
- **Prop vig is worse** (commonly -115 to -125). Edge must clear a higher bar
  than on a game line. Say so when a read is real but too thin for the price.
- **Correlation within games is severe** (QB pass yards <-> WR1 receiving).
  Flag whenever multiple reads come from one game.
- **Weather, pace, and game script** matter far more than in baseball. A
  volume read dies in a blowout or a monsoon.

## Weekly workflow

```
python scripts/pull_slate.py   --week N    # games, injuries, usage, open props
#   -> analyze, verify underlying (G4), decompose (G3), log candidate rows
python scripts/pull_closing.py --week N    # closing lines -> CLV   [RUN BEFORE KICKOFF WINDOW CLOSES]
python scripts/grade.py        --week N    # results -> margin vs fair
python scripts/report.py       --week N    # dashboard
```

Then: PROPOSE classifications, wait for ratification, update
`state/hypotheses.yaml`.

## What is automated vs manual

**Automated** (scheduled, runs without the user): slate pulls, injury/usage
snapshots, closing-line capture, result grading, view builds, and **logging
every recommendation as a zero-stake shadow row**. This exists because missed
weeks were the root cause of every data gap in the prior project — and because
this repo reproduced that failure in its own first season, running the engine
for three weeks into an empty ledger while the only write path sat on a machine
that could not execute it.

Auto-logging a shadow row is collection, not judgment: it costs nothing, risks
nothing, and the only alternative on offer was collecting nothing. `ledger.py`
refuses a stake above zero on anything but a PROVEN hypothesis, so the
automation is structurally incapable of betting.

**Manual, permanently:** hypothesis definition, tier changes, PROPOSED ->
RATIFIED, and — once something reaches PROVEN — which rows take money and at
what size. Automate collection; never automate judgment.

## Dashboard

`python scripts/report.py --week N` builds the dashboard
(WEEK / PERFORMANCE / CONFIDENCE / POST-HOC / HYPOTHESES / TRACKING /
METHODOLOGY) into `dashboards/`.

It **self-validates and exits non-zero on failure** — tag balance, tab buttons
matching content divs, jumplink resolution, and undefined badge classes. Never
hand the user a dashboard that failed validation; fix it and rebuild.

The dashboard leads with **mean CLV**, not W/L, and says so on the page. Keep it
that way: the headline number should be the one that resolves first at this
sample size.

Styling lives in `web/theme.css` (design tokens in `:root`); components are
built by `scripts/components.py`. Add a tab by writing a `tab_*()` function and
registering it in `build()` — never hand-write HTML into report.py.

## Repo map

```
CLAUDE.md                      this file
state/<league>/hypotheses.yaml    H registry: status, gates, records, min-n
state/<league>/rules.yaml         G-rules + amendment log
state/<league>/ledger/bets.csv    prospective bets only (incl. shadow, stake=0)
state/<league>/ledger/slips.csv   slips: a bet ticket grouping its legs
state/<league>/ledger/mechanism.csv       G6 observations, tagged separately
state/<league>/ledger/classifications.csv PROPOSED/RATIFIED audit trail
data/raw/<league>/             immutable dated snapshots
dashboards/<league>/           generated HTML + registry.md
scripts/pull_*.py grade.py     collection and grading
scripts/report.py              builds the dashboard (the record)
scripts/console.py             builds console.html (the decision, writable)
scripts/ledger.py              the write path: log / enter / close / ratify
scripts/scan.py recommend.py   triggers -> candidates -> priced recommendations
scripts/parlay.py              slips, from cleared legs only
scripts/gaps.py journal.py     collection gaps; decision log
scripts/app.py                 superseded local console; not the write path
scripts/review.py              registry -> markdown export
scripts/components.py          HTML component builders
scripts/validate_html.py       4 structural checks; build gate
web/theme.css                  design system (tokens in :root)
```

## Leagues

Every path is scoped by `LEAGUE` (default `nfl`). One repo, one method, one set
of scripts — but a **separate ledger, registry and rule book per sport**. A
hypothesis is never portable across sports; only the method is. Adding a league
is a folder and a calendar entry in `scripts/config.py`, not a fork.

    LEAGUE=nfl  python scripts/report.py --week 2
    LEAGUE=ncaa python scripts/report.py --week 4

Never let two leagues share a ledger. Mixed rows make both unreadable, and the
sample problem in one sport is not the sample problem in the other.

## Views

There are exactly two views and one export, and they read the same files:

- `report.py` — static dashboard, self-validating. **The record.** What was
  collected, what it cost, what it taught. Read-only by design.
- `console.py` — the write-enabled view, built to `dashboards/<league>/
  console.html` and served by Pages. **The decision.** This week's
  recommendations and slips, selectable, with the line and price editable to
  what the user's book actually shows, and an Enter that dispatches
  `ledger.yml`. Same components, same theme; if it looks different from the
  static build, that is a bug.
- `review.py` — registry and rules as markdown, for reading without a browser.

Do not add a third view. The HYPOTHESES and METHODOLOGY tabs *are* the registry
view; render the registry there or not at all.

`app.py` was the console before this one and is kept for a machine that can run
Python. **It is no longer the write path** and must not be treated as one: a
write path that requires a local install is how this repo spent three weeks
producing recommendations into an empty ledger. If app.py and console.py ever
disagree about what a write does, console.py is correct — it is the one that
runs.

**A static page cannot write to a ledger**, and the console does not pretend
otherwise. It dispatches a workflow; the workflow writes the CSV and rebuilds
both views; Pages redeploys. The page says the write is pending until the run
lands, because a UI that reports success before the write is how a ledger and a
screen quietly diverge. The user's token is theirs: fine-grained, this repo
only, Actions read/write, held in their browser. Never commit one, never embed
one, never ask for one.

## Ledger integrity

The CSVs are git-tracked on purpose: every change to the record is a commit, so
it is provable that no number was retro-adjusted. Never rewrite history in these
files. Corrections are appended with a note, not edited in place.
