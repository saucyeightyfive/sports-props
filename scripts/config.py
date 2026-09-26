"""Shared paths, constants, and odds math."""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent.parent

# Every path is scoped by league. One repo, one method, one set of scripts --
# but a separate ledger, registry and rule book per sport, because a hypothesis
# is never portable across sports and a shared ledger would make both
# unreadable. Adding a league is a folder, not a fork.
LEAGUE = os.getenv("LEAGUE", "nfl").lower()

STATE = ROOT / "state" / LEAGUE
LEDGER = STATE / "ledger"
BETS = LEDGER / "bets.csv"
SLIPS = LEDGER / "slips.csv"
MECHANISM = LEDGER / "mechanism.csv"
CLASSIFICATIONS = LEDGER / "classifications.csv"
HYPOTHESES = STATE / "hypotheses.yaml"
RULES = STATE / "rules.yaml"
RAW = ROOT / "data" / "raw" / LEAGUE
DASHBOARDS = ROOT / "dashboards" / LEAGUE

SEASON = int(os.getenv("SEASON", os.getenv("NFL_SEASON", "2026")))

# The Odds API. Free tier works for live lines; historical endpoints (needed for
# reliable closing lines) are paid. See README.
ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
ODDS_BASE = "https://api.the-odds-api.com/v4"
SPORT = "americanfootball_nfl"

# Prop markets we track. Keep this list tight — every market added multiplies
# rows, and unfocused volume is not the same as sample.
# The Odds API bills each per-event request as (markets x regions).
#
# On the free tier the right answer was to collect only what a live hypothesis
# reads -- three markets, 48 credits a sweep, because 500 a month made every
# unread market a real cost. On the 20,000-credit tier that trade reverses, for
# one reason: a board not captured this week cannot be bought back later at
# this tier. Storage is free and history is not repurchasable, so collect the
# wider set now and let a future hypothesis have something to test.
#
# Six markets across ~32 events is ~192 credits a sweep. Three sweeps a week is
# roughly 2,300 a month against 20,000.
PROP_MARKETS = [
    "player_pass_yds",
    "player_pass_tds",
    "player_rush_yds",
    "player_reception_yds",
    "player_receptions",
    "player_anytime_td",
]

BOOKMAKERS = ["draftkings", "fanduel", "betmgm", "caesars"]

# Books are free -- the bill is markets x regions per event, so four books cost
# the same as one and give a real de-vig and a best-price comparison.

# How far ahead to buy boards. Widened from 4 days on the paid tier: H1's
# trigger asks whether a line has moved since the prior week, which needs an
# early board to compare against, and the softest lines are the earliest ones.
PROPS_HORIZON_DAYS = int(os.getenv("PROPS_HORIZON_DAYS", "8"))

# Minimum gap between sweeps of the same week. This is a guard against a
# debugging re-run silently re-buying a board, not a budget cap -- six hours
# still allows Thursday, Sunday morning and a pre-kickoff capture.
PROPS_REFRESH_HOURS = int(os.getenv("PROPS_REFRESH_HOURS", "6"))


# ---------------------------------------------------------------------------
# Odds math. CLV is the primary early signal (G2), so this has to be right.
# ---------------------------------------------------------------------------

def american_to_prob(odds):
    """American odds -> implied probability (with vig still in)."""
    o = float(odds)
    return (-o) / ((-o) + 100.0) if o < 0 else 100.0 / (o + 100.0)


def prob_to_american(p):
    """Implied probability -> American odds."""
    p = float(p)
    if not 0 < p < 1:
        raise ValueError(f"probability out of range: {p}")
    return -round(100 * p / (1 - p)) if p >= 0.5 else round(100 * (1 - p) / p)


def devig_two_way(price_a, price_b):
    """Remove vig from a two-way market. Returns (fair_prob_a, fair_prob_b).

    Simple multiplicative (proportional) de-vig. Adequate for props; shout if a
    market is wildly asymmetric, where a power/Shin method would be better.
    """
    pa, pb = american_to_prob(price_a), american_to_prob(price_b)
    total = pa + pb
    if total <= 0:
        raise ValueError("bad two-way prices")
    return pa / total, pb / total


def clv_cents(price_stake, price_close):
    """CLV in cents of American odds. Positive = you beat the close.

    Measured in probability space then re-expressed, so it stays meaningful
    across the -100 boundary (where raw American subtraction lies to you).
    """
    p_stake = american_to_prob(price_stake)
    p_close = american_to_prob(price_close)
    # You beat the close when your price implied a LOWER probability (longer
    # odds) than the closing price for the same outcome.
    return round((p_close - p_stake) * 10000) / 100.0


def clv_pct(price_stake, price_close):
    """CLV as % edge vs the closing implied probability."""
    p_stake = american_to_prob(price_stake)
    p_close = american_to_prob(price_close)
    if p_stake <= 0:
        return None
    return round((p_close / p_stake - 1) * 10000) / 100.0


def payout_units(price, stake_units):
    """Profit in units for a winning bet (excludes returned stake)."""
    o = float(price)
    return stake_units * (100.0 / (-o)) if o < 0 else stake_units * (o / 100.0)

# ---------------------------------------------------------------------------
# Season calendar. The week you care about is almost always the one you have
# not logged yet, so the default week comes from the date, not from the ledger.
# ---------------------------------------------------------------------------
from datetime import date as _date

# First game of week 1. 2026 opened Wednesday Sept 9.
# Opening day and week count per league. Week numbers are a calendar fact, not
# a ledger fact -- see default_week().
_CAL = {
    "nfl":  {"start": _date(2026, 9, 9),  "weeks": 18},
    "ncaa": {"start": _date(2026, 8, 29), "weeks": 15},
}
_cal = _CAL.get(LEAGUE, _CAL["nfl"])
SEASON_START = _cal["start"]
WEEKS = _cal["weeks"]


def current_week(today=None):
    """Week number by the calendar, clamped to the season.

    Weeks roll on the same weekday the season opened, so the new week is
    current from the moment the previous one finishes — which is when you
    start logging it. Returns 1 before the season and WEEKS after it.
    """
    today = today or _date.today()
    n = (today - SEASON_START).days // 7 + 1
    return max(1, min(WEEKS, n))


def default_week(ledger_weeks=()):
    """Calendar week, falling back to the ledger when out of season."""
    today = _date.today()
    if SEASON_START <= today <= _date(SEASON_START.year + 1, 3, 1):
        return current_week(today)
    return max(ledger_weeks) if ledger_weeks else 1
