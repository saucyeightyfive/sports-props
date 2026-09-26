#!/usr/bin/env python3
"""Build the multi-tab HTML dashboard from the ledgers and state files.

Seven tabs mirroring the predecessor project: WEEK, PERFORMANCE, CONFIDENCE,
POST-HOC, HYPOTHESES, TRACKING, METHODOLOGY.

Leads with mean CLV rather than W/L — with ~16 games a week, CLV is the signal
that resolves first (G2). Self-validates before writing; a failing build is not
shipped.

  python scripts/report.py --week 1
  python scripts/report.py --week 1 --demo    # synthetic rows, to preview layout
"""
import argparse, csv, sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
import components as UI
import gaps
from validate_html import validate

try:
    import yaml
except ImportError:
    yaml = None


# --------------------------------------------------------------------------- data
def read_csv(path):
    p = Path(path)
    if not p.exists():
        return []
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def read_yaml(path):
    p = Path(path)
    if not (yaml and p.exists()):
        return {}
    try:
        return yaml.safe_load(p.read_text()) or {}
    except Exception:
        return {}


def num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def tone_for(v, invert=False):
    if v is None:
        return "neu"
    if v == 0:
        return "neu"
    good = v > 0 if not invert else v < 0
    return "pos" if good else "neg"


# --------------------------------------------------------------------------- tabs
# --- registry renderers (were review.py; folded in so the dashboard
# --- is the only place the registry is drawn) -------------------------
def _list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _clean(v):
    """YAML folded blocks arrive with newlines that mean nothing."""
    return " ".join(str(v).split()) if v is not None else ""


def touched(text, since):
    return bool(since) and since in str(text)


# --------------------------------------------------------------------------- html


def hypothesis_card(h, since=None):
    rec = h.get("record") or {}
    badges = [UI.badge(h.get("tier", "SHADOW"), (h.get("tier") or "shadow").lower())]
    if h.get("conjunction"):
        badges.append(UI.badge("CONJUNCTION", "flag"))
    if h.get("edge_claimed_on"):
        badges.append(UI.badge(f"EDGE ON {h['edge_claimed_on'].upper()}", "info"))
    if h.get("earliest_fire_week"):
        badges.append(UI.badge(f"OPENS WK {h['earliest_fire_week']}", "pending"))
    if since and touched(h, since):
        badges.append(UI.badge("REVISED", "win"))

    parts = [f"<p><strong>Mechanism.</strong> {UI.esc(_clean(h.get('mechanism')))}</p>"]

    trig = _list(h.get("trigger"))
    if trig:
        # Built without a backslash inside the f-string expression: legal from
        # Python 3.12 onward, a hard SyntaxError before it. CI runs 3.11.
        items = []
        for t in trig:
            cls = ' class="gt"' if touched(t, since) else ""
            items.append(f"<li{cls}>{UI.esc(_clean(t))}</li>")
        parts.append("<p><strong>Fires when — all of:</strong></p><ul>"
                     + "".join(items) + "</ul>")

    cond = h.get("conditions_named")
    if cond:
        rows = [[f'<span class="mono">{UI.esc(k)}</span>', UI.esc(_clean(v))]
                for k, v in cond.items()]
        parts.append("<p><strong>Conditions this expression requires</strong> "
                     "(G3a — no prop is a single condition):</p>"
                     + UI.table(["Condition", "What has to be true"], rows))

    ver = _list(h.get("verify_underlying"))
    if ver:
        parts.append("<p><strong>Verified on (G4):</strong> "
                     + UI.esc(" · ".join(_clean(v) for v in ver)) + "</p>")

    axes = _list(h.get("axes"))
    if axes:
        rows = [[f'<span class="mono">{UI.esc(a.get("name"))}</span>',
                 UI.esc(_clean(a.get("pair"))), UI.esc(_clean(a.get("claim")))]
                for a in axes]
        parts.append("<p><strong>Axes under test:</strong></p>"
                     + UI.table(["Axis", "Paired against", "Claim"], rows))

    parts.append(f"<p><strong>Expression.</strong> "
                 f"{UI.esc(_clean(h.get('expression')))}</p>")

    if h.get("conjunction_note"):
        parts.append(UI.insight("WHY IT IS FLAGGED THIS WAY",
                                UI.esc(_clean(h["conjunction_note"])),
                                "g" if touched(h.get("conjunction_note"), since) else "b"))

    parts.append(f"<p><strong>Dies if.</strong> "
                 f"{UI.esc(_clean(h.get('disproof')))}</p>")

    n, mn = rec.get("rows", 0), h.get("min_n", "?")
    parts.append(f"<p><strong>Gate.</strong> {n} of {mn} rows · "
                 f"mean CLV {rec.get('mean_clv_cents') or '—'} · "
                 f"mean margin {rec.get('mean_margin_vs_fair') or '—'}</p>")
    if h.get("min_n_note"):
        parts.append(f'<p class="mut">{UI.esc(_clean(h["min_n_note"]))}</p>')
    for note in _list(h.get("notes")):
        parts.append(UI.alert(UI.esc(_clean(note)), kind="warn", icon="⚠"))

    tone = "win" if (since and touched(h, since)) else "shadow"
    return UI.panel(f"{h.get('id')} — {h.get('name')}", badges, "".join(parts), tone)


def candidate_card(c):
    badges = [UI.badge("NOT OPENED", "flag")]
    if c.get("written"):
        badges.append(UI.badge(f"WRITTEN {c['written']}", "info"))
    body = (f"<p><strong>Mechanism.</strong> {UI.esc(_clean(c.get('mechanism')))}</p>"
            f"<p><strong>Why it stays closed.</strong> "
            f"{UI.esc(_clean(c.get('why_not_opened')))}</p>"
            f"<p><strong>Revisit.</strong> {UI.esc(_clean(c.get('revisit')))}</p>")
    return UI.panel(f"{c.get('id')} — {c.get('name')}", badges, body, "skip")


def _gap_banner(week):
    """Open collection gaps, in red, at the top of the week.

    The system's whole premise is that the record must not flatter itself. A
    missing prop board is the most flattering failure available: no board means
    no candidates, no candidates reads as a dry week, and a dry week reads as
    discipline. It is not — it is a hole, and it says so here until it is
    filled."""
    try:
        open_gaps = gaps.for_week(week)
    except Exception:
        return ""
    if not open_gaps:
        return ""
    items = "".join(
        f"<li><span class='mono'>{UI.esc(g['kind'])}</span> — "
        f"{UI.esc(gaps.REMEDY.get(g['reason'], g['reason']))}"
        + (f" <span class='mut'>({UI.esc(g['detail'])})</span>"
           if g.get("detail") else "") + "</li>"
        for g in open_gaps)
    return UI.alert(
        f"<strong>{len(open_gaps)} COLLECTION GAP(S) THIS WEEK — the data is "
        f"missing, not empty.</strong><ul>{items}</ul>"
        "Anything below that reads as \"no candidates\" may simply be "
        "untested. Do not grade a week against a board that was never "
        "captured.", kind="act", icon="🚨")


def tab_week(bets, week):
    rows = [b for b in bets if str(b.get("week")) == str(week)]
    live = [b for b in rows if (num(b.get("stake_units"), 0) or 0) > 0]

    head = UI.alert(
        f"<strong>WEEK {week} — {len(rows)} row(s) logged, "
        f"{len(live)} live, {len(rows)-len(live)} shadow.</strong><br>"
        "Every row must be logged before kickoff (G5) and tagged PROJECTED vs "
        "CONFIRMED — inactives post ~90 minutes out, and a prop on a scratched "
        "player is a process failure, not bad luck.",
        kind="warn")

    trs = []
    for b in rows:
        clv = num(b.get("clv_cents"))
        clv_cell = (f'<span class="{tone_for(clv)}">{clv:+.2f}</span>'
                    if clv is not None else '<span class="mono">—</span>')
        staked = (num(b.get("stake_units"), 0) or 0) > 0
        trs.append([
            f'<span class="mono">{UI.esc(b.get("row_id"))}</span>',
            UI.esc(b.get("player")),
            f'<span class="mono">{UI.esc(b.get("prop_type"))}</span>',
            f'<span class="mono">{UI.esc(b.get("side"))} {UI.esc(b.get("line_stake"))}</span>',
            f'<span class="mono">{UI.esc(b.get("price_stake"))}</span>',
            f'<span class="mono">{UI.esc(b.get("price_close")) or "—"}</span>',
            clv_cell,
            f'<span class="mono">{UI.esc(b.get("hypothesis"))}</span>',
            UI.badge(f'LIVE {b.get("stake_units")}u', "live") if staked
            else UI.badge("SHADOW", "shadow"),
            UI.badge(b.get("status_at_stake") or "—",
                     "info" if b.get("status_at_stake") == "CONFIRMED" else "flag"),
        ])

    tbl = UI.table(
        ["ID", "Player", "Market", "Side/Line", "Price", "Close", "CLV",
         "H", "Tier", "Status"], trs)

    guard = UI.insight(
        "BEFORE STAKING ANYTHING",
        "Only a <strong>PROVEN</strong> hypothesis gets live money. Everything "
        "else is <strong>zero dollars</strong>, logged and graded all the same. "
        "If no hypothesis fires this week, the correct output is to say so and "
        "stop — a dry week is the system working, not a gap to fill.", "r")

    return _gap_banner(week) + head + UI.section(f"Week {week} rows", tbl) + UI.section("Discipline", guard)


def tab_performance(bets):
    live = [b for b in bets if (num(b.get("stake_units"), 0) or 0) > 0]
    graded = [b for b in bets if b.get("outcome")]
    pnl = sum(num(b.get("pnl_units"), 0) or 0 for b in live)
    clvs = [num(b.get("clv_cents")) for b in bets if num(b.get("clv_cents")) is not None]
    mean_clv = sum(clvs) / len(clvs) if clvs else None
    wins = sum(1 for b in graded if b["outcome"] == "WIN")
    losses = sum(1 for b in graded if b["outcome"] == "LOSS")
    pushes = sum(1 for b in graded if b["outcome"] == "PUSH")
    pos_clv = sum(1 for c in clvs if c > 0)

    cards = UI.statcards([
        ("Mean CLV", f"{mean_clv:+.2f}c" if mean_clv is not None else "—",
         f"n={len(clvs)} · primary signal", tone_for(mean_clv)),
        ("Beat the close", f"{pos_clv}/{len(clvs)}" if clvs else "—",
         "rows with +CLV", "neu"),
        ("P&L (live only)", f"{pnl:+.2f}u", f"{len(live)} staked row(s)",
         tone_for(pnl)),
        ("Graded record", f"{wins}-{losses}" + (f"-{pushes}" if pushes else ""),
         "incl. shadow rows", "neu"),
        ("Shadow rows", str(len(bets) - len(live)), "tracked, unstaked", "neu"),
    ])

    weeks = {}
    for b in bets:
        w = b.get("week")
        d = weeks.setdefault(w, {"n": 0, "live": 0, "pnl": 0.0, "clv": []})
        d["n"] += 1
        if (num(b.get("stake_units"), 0) or 0) > 0:
            d["live"] += 1
            d["pnl"] += num(b.get("pnl_units"), 0) or 0
        c = num(b.get("clv_cents"))
        if c is not None:
            d["clv"].append(c)

    trs = []
    for w in sorted(weeks, key=lambda x: int(x) if str(x).isdigit() else 0):
        d = weeks[w]
        mc = sum(d["clv"]) / len(d["clv"]) if d["clv"] else None
        trs.append([
            f'<span class="mono">Week {UI.esc(w)}</span>',
            f'<span class="mono">{d["n"]}</span>',
            f'<span class="mono">{d["live"]}</span>',
            f'<span class="mono {tone_for(mc)}">{f"{mc:+.2f}" if mc is not None else "—"}</span>',
            f'<span class="mono {tone_for(d["pnl"])}">{d["pnl"]:+.3f}u</span>',
        ])

    note = UI.insight(
        "READ THIS BEFORE THE P&L",
        "With ~16 games a week, <strong>win-loss says almost nothing</strong> "
        "across dozens of rows. Mean CLV is the number that resolves first: a "
        "hypothesis that persistently beats the close is real even at a middling "
        "hit rate, and one that loses to the close is noise even while it is "
        "winning. Judge the season on CLV and margin vs fair — not the record.", "tl")

    return (cards + UI.section("Why CLV leads", note) +
            UI.section("Weekly log", UI.table(
                ["Week", "Rows", "Live", "Mean CLV", "P&L"], trs)))


def tab_confidence(classes, hyp):
    pending = [c for c in classes if (c.get("status") or "").upper() == "PROPOSED"]
    ratified = [c for c in classes if (c.get("status") or "").upper() == "RATIFIED"]

    head = UI.alert(
        "<strong>Two-step ratification.</strong> Every classification is "
        "PROPOSED by Claude, then RATIFIED by you. Nothing credits the "
        "confidence ledger until you sign off — and Claude never ratifies its "
        "own work. Disagreement is logged signal, not a problem to smooth over.",
        kind="under", icon="⚖")

    ptrs = [[f'<span class="mono">{UI.esc(c.get("class_id"))}</span>',
             f'<span class="mono">{UI.esc(c.get("hypothesis"))}</span>',
             UI.badge(c.get("proposed_class", "—"),
                      (c.get("proposed_class") or "info").lower()),
             UI.esc(c.get("rationale"))] for c in pending]

    rtrs = [[f'<span class="mono">{UI.esc(c.get("date_ratified"))}</span>',
             f'<span class="mono">{UI.esc(c.get("hypothesis"))}</span>',
             UI.badge(c.get("ratified_class", "—"),
                      (c.get("ratified_class") or "info").lower()),
             UI.esc(c.get("user_note") or c.get("rationale"))] for c in ratified]

    htrs = []
    for h in (hyp.get("hypotheses") or []):
        rec = h.get("record") or {}
        mc = rec.get("mean_clv_cents")
        htrs.append([
            f'<span class="mono">{UI.esc(h.get("id"))}</span>',
            UI.esc(h.get("name")),
            UI.badge(h.get("tier", "SHADOW"), (h.get("tier") or "shadow").lower()),
            f'<span class="mono">{rec.get("rows", 0)}/{h.get("min_n", "?")}</span>',
            f'<span class="mono {tone_for(mc)}">'
            f'{f"{mc:+.2f}" if isinstance(mc, (int, float)) else "—"}</span>',
        ])

    return (head +
            UI.section("Awaiting your ratification",
                       UI.table(["ID", "H", "Proposed", "Rationale"], ptrs)) +
            UI.section("Per-hypothesis state",
                       UI.table(["H", "Name", "Tier", "Rows / min-n", "Mean CLV"], htrs)) +
            UI.section("Ratified history",
                       UI.table(["Date", "H", "Class", "Note"], rtrs)))


def tab_posthoc(bets, week):
    prev = week - 1
    rows = [b for b in bets if str(b.get("week")) == str(prev) and b.get("outcome")]
    if not rows:
        return UI.alert(
            f"<strong>No graded rows for week {prev} yet.</strong><br>"
            f"Run <span class='mono'>python scripts/grade.py --week {prev}</span> "
            "after the games, then propose classifications.",
            kind="warn", icon="🔬")

    trs = []
    for b in rows:
        clv = num(b.get("clv_cents"))
        margin = num(b.get("margin_vs_fair"))
        trs.append([
            f'<span class="mono">{UI.esc(b.get("row_id"))}</span>',
            UI.esc(b.get("player")),
            f'<span class="mono">{UI.esc(b.get("side"))} {UI.esc(b.get("line_stake"))}</span>',
            f'<span class="mono">{UI.esc(b.get("actual_result"))}</span>',
            f'<span class="mono {tone_for(margin)}">'
            f'{f"{margin:+.2f}" if margin is not None else "—"}</span>',
            f'<span class="mono {tone_for(clv)}">'
            f'{f"{clv:+.2f}" if clv is not None else "—"}</span>',
            UI.badge(b.get("outcome"), (b.get("outcome") or "").lower()),
            f'<span class="mono">{UI.esc(b.get("hypothesis"))}</span>',
        ])

    gap = UI.insight(
        "THE GAP IS THE PRODUCT",
        "Grade the <em>nature</em> of each result, not just the sign. A win on a "
        "broken premise is a worse event than a loss on a sound one. Separate "
        "process defects (TEACHING) from variance (FRONTIER), and never let a "
        "good week launder a bad read.", "g")

    return (UI.alert(f"<strong>WEEK {prev} POST-HOC — {len(rows)} row(s) graded.</strong><br>"
                     "Graded against fair line (G1); margin and CLV shown per row.",
                     kind="under", icon="🔬") +
            UI.section(f"Week {prev} results",
                       UI.table(["ID", "Player", "Side/Line", "Actual", "Margin",
                                 "CLV", "Result", "H"], trs)) +
            UI.section("Classification discipline", gap))


def tab_hypotheses(hyp, since=None):
    hs = _list(hyp.get("hypotheses"))
    cands = _list(hyp.get("candidates"))
    meta = hyp.get("meta") or {}
    if not hs:
        return (UI.alert(
            "<strong>No hypotheses defined yet — this is correct on day one.</strong><br>"
            "Ask for a starter framework: 3–5 falsifiable candidates, each with a "
            "trigger, the underlying metrics that verify it (G4), the prop "
            "expression, why the market might misprice it, and what would disprove "
            "it. All open as SHADOW. Ratify before touching a slate.",
            kind="warn", icon="🧪") +
            UI.section("Template", UI.rulecard(
                "Every hypothesis must name the market's error",
                "If you cannot say <em>why</em> the market is wrong — which "
                "specific input it is underweighting — it is not a hypothesis, it "
                "is a hunch. Write the disproof condition before the data arrives, "
                "so the standard cannot drift to fit the results.", "new")))

    gate = UI.alert(
        "<strong>Definitions are editable only while a hypothesis holds zero "
        "rows.</strong><br>Once the first row lands, triggers freeze until the "
        "hypothesis reaches its minimum sample. Retuning on a handful of rows "
        "looks like learning and behaves like drift.", kind="under", icon="⚖")
    rev = (UI.insight("LAST REVISION", UI.esc(_clean(meta["revision_note"])), "tl")
           if meta.get("revision_note") else "")

    out = (gate + rev +
           UI.section("Open hypotheses", *[hypothesis_card(h, since) for h in hs]))
    if cands:
        out += UI.section("Candidates — written down, not opened",
                          *[candidate_card(c) for c in cands])
    return out

def tab_tracking(bets, mech):
    clv_rows = [b for b in bets if num(b.get("clv_cents")) is not None]
    by_h = {}
    for b in clv_rows:
        by_h.setdefault(b.get("hypothesis") or "—", []).append(num(b["clv_cents"]))

    trs = []
    for h, vals in sorted(by_h.items()):
        mean = sum(vals) / len(vals)
        beat = sum(1 for v in vals if v > 0)
        trs.append([
            f'<span class="mono">{UI.esc(h)}</span>',
            f'<span class="mono">{len(vals)}</span>',
            f'<span class="mono {tone_for(mean)}">{mean:+.2f}</span>',
            f'<span class="mono">{beat}/{len(vals)}</span>',
            UI.badge("positive" if mean > 0 else "negative",
                     "confirmed" if mean > 0 else "danger"),
        ])

    mtrs = [[f'<span class="mono">{UI.esc(m.get("date"))}</span>',
             UI.esc(m.get("player")),
             f'<span class="mono">{UI.esc(m.get("metric"))}</span>',
             f'<span class="mono">{UI.esc(m.get("value"))}</span>',
             f'<span class="mono">{UI.esc(m.get("expected"))}</span>',
             UI.esc(m.get("note"))] for m in mech]

    g6 = UI.insight(
        "G6 — MECHANISM, NOT MARKETS",
        "Observations recovered from weeks you missed live here, tagged "
        "separately and permanently outside the bet ledger. They can tell you "
        "whether a mechanism holds; they can never tell you whether a bet would "
        "have won. Reconstructing a line after the fact is how a record starts "
        "flattering you.", "b")

    return (UI.section("CLV by hypothesis — the leading indicator",
                       UI.table(["H", "Rows", "Mean CLV", "Beat close", "Signal"], trs)) +
            UI.section("Mechanism observations",
                       UI.table(["Date", "Player", "Metric", "Actual", "Expected",
                                 "Note"], mtrs)) +
            UI.section("Why these are separate", g6))


def tab_methodology(rules):
    cards = [UI.rulecard(
        f"{r.get('id')} — {r.get('name')}",
        UI.esc(_clean(r.get("text"))) +
        (f"<br><br><em>Origin: {UI.esc(_clean(r['origin']))}</em>"
         if r.get("origin") else ""), "new")
        for r in _list(rules.get("rules"))]

    acards = []
    for a in _list(rules.get("amendments")):
        st = (a.get("status") or "RATIFIED").upper()
        badges = [UI.badge(st, "pending" if st == "PROPOSED" else "confirmed"),
                  UI.badge(str(a.get("rule")), "info"),
                  UI.badge(str(a.get("date")), "info")]
        body = f"<p>{UI.esc(_clean(a.get('change')))}</p>"
        if a.get("origin"):
            body += (f"<p><strong>Origin.</strong> "
                     f"{UI.esc(_clean(a['origin']))}</p>")
        acards.append(UI.panel(f"Amendment to {a.get('rule')}", badges, body,
                               "info" if st == "PROPOSED" else "win"))
    if not acards:
        acards = [UI.insight("NO AMENDMENTS",
                             "The rules have not changed since the framework "
                             "opened.", "b")]
    return (UI.section("Active rules", *cards) +
            UI.section("Amendment log", *acards))

# --------------------------------------------------------------------------- build

def _recommendations(week):
    import json as _json
    path = C.STATE / f"recommendations_wk{week:02d}.json"
    if not path.exists():
        return ""
    d = _json.loads(path.read_text())
    recs, thin = d.get("recommendations", []), d.get("too_thin", [])

    out = ""
    if recs:
        blocks = []
        for r in recs:
            badges = [UI.badge(f"EV {r['ev_pct']:+.2f}%",
                               "confirmed" if r["ev_pct"] > 0 else "danger"),
                      UI.badge(r["hypothesis"], "live"),
                      UI.badge("SHADOW · 0u", "shadow")]
            math = UI.table(
                ["Market fair", "Claimed edge", "Model", "Best price",
                 "Breakeven", "EV"],
                [[f'<span class="mono">{r["fair_prob"]}%</span>',
                  f'<span class="mono">+{r["claimed_edge"]}</span>',
                  f'<span class="mono gt">{r["model_prob"]}%</span>',
                  f'<span class="mono">{r["best_price"]:+d} '
                  f'<span class="mut">{UI.esc(r["best_book"])}</span></span>',
                  f'<span class="mono">{r["breakeven_prob"]}%</span>',
                  f'<span class="mono gt">{r["ev_pct"]:+.2f}%</span>']])
            blocks.append(UI.panel(
                f'{r["player"]} ({r["team"]}) — {r["market"]} {r["side"]} {r["line"]}',
                badges,
                f'<p class="mut">{UI.esc(r["game"])}</p>'
                f'<p>{UI.esc(r["reason"])}</p>{math}', "live"))
        out += UI.section("Recommendations", *blocks)

    if thin:
        rows = [[f'<span class="mono">{UI.esc(r["player"])}</span>',
                 f'<span class="mono mut">{UI.esc(r["market"])} {UI.esc(r["side"])} '
                 f'{UI.esc(r["line"])}</span>',
                 f'<span class="mono">{r["model_prob"]}%</span>',
                 f'<span class="mono">{r["breakeven_prob"]}%</span>',
                 f'<span class="mono">{r["hold"]}%</span>'] for r in thin]
        out += UI.section(
            "Real reads, wrong price",
            UI.insight("TOO THIN IS A RESULT",
                       "These fired a trigger and still should not be bet: even "
                       "granting the full edge the hypothesis claims, the price "
                       "does not clear. Prop vig is the reason most true reads "
                       "are unprofitable, and a system that cannot say so will "
                       "talk you into the wrong price every week.", "r"),
            UI.table(["Player", "Market", "Model", "Breakeven", "Vig"], rows))
    return out


def _parlays(week):
    """Slips built from qualifying single props. Separate ledger, always."""
    import json as _json
    path = C.STATE / f"parlays_wk{week:02d}.json"
    if not path.exists():
        return ""
    d = _json.loads(path.read_text())
    slips = d.get("slips", [])
    if not slips:
        return UI.section("Parlays", UI.insight(
            "NO SLIP THIS WEEK",
            f"{d.get('qualifying_legs', 0)} qualifying single prop(s). A parlay "
            "built from fewer than two of them is not a parlay, and padding it "
            "with legs the engine did not recommend is how a disciplined system "
            "becomes a lottery ticket.", "b"))

    blocks = []
    for s_ in slips:
        badges = [UI.badge(f"{s_['n_legs']} LEG", "info"),
                  UI.badge(f"{s_['offered_price']:+d}", "live"),
                  UI.badge(f"EV {s_['ev_pct']:+.2f}%",
                           "confirmed" if s_["ev_pct"] > 0 else "danger")]
        if s_["same_game"]:
            badges.append(UI.badge("CORRELATED", "danger"))
        legs = UI.table(
            ["H", "Player", "Market", "Price", "Fair", "Model"],
            [[f'<span class="mono">{UI.esc(l["hypothesis"])}</span>',
              UI.esc(l["player"]),
              f'<span class="mono mut">{UI.esc(l["market"])} {UI.esc(l["side"])} '
              f'{UI.esc(l["line"])}</span>',
              f'<span class="mono">{l["best_price"]:+d} '
              f'<span class="mut">{UI.esc(l["best_book"])}</span></span>',
              f'<span class="mono">{l["fair_prob"]}%</span>',
              f'<span class="mono gt">{l["model_prob"]}%</span>'] for l in s_["legs"]])
        body = (f'<p>Your price <span class="mono">{s_["offered_price"]:+d}</span> '
                f'against a fair <span class="mono">{s_["fair_price"]:+d}</span>. '
                f'Compounded vig costs <strong>{abs(s_["vig_cost_pct"]):.2f}%</strong> '
                f'of the edge — each added leg pays the house again.</p>{legs}')
        if s_["same_game"]:
            body += ('<p><strong>These legs share a game.</strong> They are not '
                     'two independent bets, and the combined probability above '
                     'overstates the slip.</p>')
        blocks.append(UI.panel(
            " + ".join(l["player"] for l in s_["legs"]), badges, body,
            "loss" if s_["same_game"] or s_["ev_pct"] <= 0 else "live"))

    note = UI.insight(
        "WHY PARLAYS HAVE THEIR OWN LEDGER",
        "A slip's result is recorded in slips.csv and never credits or debits a "
        "hypothesis. A hypothesis cannot be judged on another leg's luck — a "
        "correct read that loses because an unrelated leg failed would poison "
        "the evidence it was collected for.", "tl")

    return UI.section("Parlays", *blocks) + UI.section("Reading these", note)


def tab_candidates(week):
    """What the scanner found. Proposals only — nothing here is staked."""
    path = C.STATE / f"candidates_wk{week:02d}.json"
    if not path.exists():
        return UI.alert(
            f"<strong>No scan yet for week {week}.</strong><br>"
            f"Run <span class='mono'>python scripts/scan.py --week {week}</span> "
            "after the slate pull. The scanner reads the captured prop board "
            "and the usage data, tests every hypothesis trigger, and lists what "
            "fired — or says plainly why it could not.", kind="warn", icon="🔍")
    import json as _json
    d = _json.loads(path.read_text())

    head = UI.statcards([
        ("Board lines", f"{d.get('board_lines', 0):,}", "captured this week", "neu"),
        ("Players w/ usage", str(d.get("players_with_usage", 0)),
         "current season", "neu"),
        ("Candidates", str(sum(len(r["candidates"]) for r in d["results"])),
         "proposals, zero staked", "neu"),
        ("Unevaluable", str(sum(1 for r in d["results"]
                                if r["verdict"] == "UNEVALUABLE")),
         "hypotheses blocked", "neg" if any(
             r["verdict"] == "UNEVALUABLE" for r in d["results"]) else "pos"),
    ])

    blocks = []
    for r in d["results"]:
        v = r["verdict"]
        tone = {"FIRED": "live", "NO CANDIDATES": "skip",
                "UNEVALUABLE": "loss"}[v]
        badges = [UI.badge(v, {"FIRED": "confirmed", "NO CANDIDATES": "shadow",
                               "UNEVALUABLE": "danger"}[v]),
                  UI.badge(str(r.get("tier", "SHADOW")), "shadow")]
        body = ""
        if r["candidates"]:
            trs = []
            for c in r["candidates"]:
                trs.append([
                    f'<span class="mono">{UI.esc(c["player"])}</span>',
                    f'<span class="mono mut">{UI.esc(c["team"])}</span>',
                    UI.esc(c["game"]),
                    f'<span class="mono">{UI.esc(c["market"])} '
                    f'{UI.esc(c["side"])} {UI.esc(c["line"])}</span>',
                    f'<span class="mono">{c["price"]:+d} '
                    f'<span class="mut">{UI.esc(c["book"])}</span></span>',
                    f'<span class="mono">{c["target_share_prior"]} → '
                    f'{c["target_share"]} '
                    f'<span class="gt">(+{c["rise"]})</span></span>',
                ])
            body += UI.table(["Player", "Tm", "Game", "Market", "Best price",
                              "Target share"], trs)
        if r["notes"]:
            items = "".join(f"<li>{UI.esc(n)}</li>" for n in r["notes"][:8])
            body += f'<p><strong>Notes</strong></p><ul>{items}</ul>'
        blocks.append(UI.panel(f'{r["id"]} — {r["name"]}', badges, body, tone))

    why = UI.insight(
        "UNEVALUABLE IS NOT A DRY WEEK",
        "A hypothesis with no candidates was tested and found nothing — that is "
        "the system working. A hypothesis marked <strong>UNEVALUABLE</strong> "
        "was never tested at all, because its trigger names an input that does "
        "not exist in the data being collected. Left alone it sits at zero rows "
        "all season looking patient. Amend the trigger, fund the source, or "
        "retire it.", "r")

    staked = UI.alert(
        "<strong>Nothing on this tab is a bet.</strong><br>Candidates are "
        "proposals produced by a rule. Logging one is a decision only you make, "
        "and it still opens at zero stake unless the hypothesis is PROVEN.",
        kind="under", icon="⚖")

    return _gap_banner(week) + head + staked + _recommendations(week) + _parlays(week) + \
        UI.section("By hypothesis — what the scanner tested", *blocks) + \
        UI.section("Reading this tab", why)


def tab_journal():
    """Decisions and reasoning, dated. The record the ledgers do not keep."""
    import csv as _csv
    p = C.LEDGER / "journal.csv"
    if not p.exists():
        return UI.alert(
            "<strong>Journal is empty.</strong><br>Log a decision with "
            "<span class='mono'>python scripts/journal.py --add decision "
            "\"subject\" \"body\"</span>, or from the console. This is where "
            "the reasoning lives — what was argued, what was rejected, what you "
            "believed at the time and were wrong about.", kind="warn", icon="📓")
    with open(p, newline="") as f:
        rows = list(_csv.DictReader(f))

    kinds = {}
    for r in rows:
        kinds[r["kind"]] = kinds.get(r["kind"], 0) + 1
    cards = UI.statcards(
        [("Entries", str(len(rows)), "all time", "neu")] +
        [(k.title(), str(v), "", "neu") for k, v in sorted(kinds.items())][:4])

    blocks = []
    for r in reversed(rows):
        badges = [UI.badge(r["kind"].upper(), {
            "decision": "confirmed", "amendment": "live",
            "correction": "danger", "discussion": "info",
            "observation": "shadow"}.get(r["kind"], "info")),
            UI.badge(f"WK {r['week']}", "info"),
            UI.badge(r["ts"][:10], "info")]
        if r.get("refs"):
            badges.append(UI.badge(r["refs"], "flag"))
        blocks.append(UI.panel(f'{r["entry_id"]} — {r["subject"]}', badges,
                               f'<p>{UI.esc(r["body"])}</p>', "info"))

    note = UI.insight(
        "WHY THIS EXISTS",
        "The bet ledger records what was risked. The confidence ledger records "
        "what a result taught. Neither records the argument that produced the "
        "decision. In March, the difference between a season you can learn from "
        "and a pile of numbers is whether anyone wrote down <em>why</em>.", "b")

    return cards + UI.section("Entries, newest first", *blocks) + \
        UI.section("Why this exists", note)


def build(week, bets, classes, mech, hyp, rules):
    clvs = [num(b.get("clv_cents")) for b in bets if num(b.get("clv_cents")) is not None]
    mean_clv = sum(clvs) / len(clvs) if clvs else None
    live = [b for b in bets if (num(b.get("stake_units"), 0) or 0) > 0]
    pnl = sum(num(b.get("pnl_units"), 0) or 0 for b in live)
    n_h = len(hyp.get("hypotheses") or [])
    proven = sum(1 for h in (hyp.get("hypotheses") or [])
                 if (h.get("tier") or "").upper() == "PROVEN")

    head = UI.header(
        "🏈 NFL PROPS", f"{C.SEASON} · WEEK {week} · built {datetime.now():%b %d %H:%M}",
        [("Mean CLV", f"{mean_clv:+.2f}c" if mean_clv is not None else "—",
          tone_for(mean_clv)),
         ("P&L (live)", f"{pnl:+.2f}u", tone_for(pnl)),
         ("Rows logged", str(len(bets)), "neu"),
         ("Hypotheses", f"{proven} proven / {n_h}", "neu"),
         ("Live-eligible", "yes" if proven else "none yet",
          "pos" if proven else "neg")])

    nav = UI.tabs([
        ("week", f"WEEK {week}", None),
        ("candidates", "PICKS", None),
        ("performance", "PERFORMANCE", None),
        ("confidence", "CONFIDENCE", "RATIFY" if any(
            (c.get("status") or "").upper() == "PROPOSED" for c in classes) else None),
        ("posthoc", f"WK {week-1} POST-HOC", None),
        ("hypotheses", "HYPOTHESES", None),
        ("tracking", "TRACKING", None),
        ("methodology", "METHODOLOGY", None),
        ("journal", "JOURNAL", None),
    ])

    body = (head + nav +
            UI.tabcontent("week", tab_week(bets, week), active=True) +
            UI.tabcontent("candidates", tab_candidates(week)) +
            UI.tabcontent("performance", tab_performance(bets)) +
            UI.tabcontent("confidence", tab_confidence(classes, hyp)) +
            UI.tabcontent("posthoc", tab_posthoc(bets, week)) +
            UI.tabcontent("hypotheses", tab_hypotheses(hyp)) +
            UI.tabcontent("tracking", tab_tracking(bets, mech)) +
            UI.tabcontent("methodology", tab_methodology(rules)) +
            UI.tabcontent("journal", tab_journal()))

    return UI.document("NFL Props", f"NFL Props — {C.SEASON} Week {week}", body)


def demo_rows(week):
    """Synthetic rows so the layout can be previewed before real data exists."""
    base = dict(season=C.SEASON, week=week, date="2026-09-13", game="KC@BAL",
                team="KC", opponent="BAL", tier_at_stake="SHADOW",
                conjunction="false", stake_units="0")
    return [
        {**base, "row_id": "W1R001", "player": "Sample WR1", "position": "WR",
         "prop_type": "player_reception_yds", "side": "over", "line_stake": "64.5",
         "price_stake": "+105", "price_close": "-115", "clv_cents": "4.71",
         "hypothesis": "H1", "status_at_stake": "CONFIRMED",
         "actual_result": "78", "margin_vs_fair": "13.5", "outcome": "WIN",
         "pnl_units": "0"},
        {**base, "row_id": "W1R002", "player": "Sample RB2", "position": "RB",
         "prop_type": "player_rush_yds", "side": "under", "line_stake": "70.5",
         "price_stake": "-120", "price_close": "+100", "clv_cents": "-4.55",
         "hypothesis": "H2", "status_at_stake": "PROJECTED",
         "actual_result": "88", "margin_vs_fair": "17.5", "outcome": "LOSS",
         "pnl_units": "0"},
        {**base, "row_id": "W1R003", "player": "Sample TE", "position": "TE",
         "prop_type": "player_receptions", "side": "over", "line_stake": "3.5",
         "price_stake": "-110", "price_close": "-135", "clv_cents": "8.36",
         "hypothesis": "H1", "status_at_stake": "CONFIRMED",
         "actual_result": "5", "margin_vs_fair": "1.5", "outcome": "WIN",
         "pnl_units": "0"},
    ]



def build_index():
    """Landing page for GitHub Pages.

    Pages needs one entry point, and the dashboards are dated per league per
    week. This scans what has actually been built and links the newest of each,
    so the published URL always lands on something current rather than a
    directory listing.
    """
    root = C.ROOT / "dashboards"
    root.mkdir(exist_ok=True)
    cards = []
    for league_dir in sorted(d for d in root.iterdir() if d.is_dir()):
        builds = sorted(league_dir.glob(f"{league_dir.name}_*_wk*.html"))
        if not builds:
            continue
        latest = builds[-1]
        week = latest.stem.split("wk")[-1].lstrip("0") or "0"
        others = "".join(
            f'<a class="tklink" style="margin-right:12px" '
            f'href="{league_dir.name}/{b.name}">wk{b.stem.split("wk")[-1]}</a>'
            for b in reversed(builds[:-1][-8:]))
        reg = league_dir / "registry.md"
        reglink = (f'<a class="tklink" href="{league_dir.name}/registry.md">'
                   f'registry (markdown)</a>' if reg.exists() else "")
        cards.append(UI.panel(
            league_dir.name.upper(),
            [UI.badge(f"WEEK {week}", "live")],
            f'<p><a class="tklink" style="font-size:14px" '
            f'href="{league_dir.name}/{latest.name}">Open week {week} dashboard →</a></p>'
            + (f'<p class="mut">Earlier: {others}</p>' if others else "")
            + (f"<p>{reglink}</p>" if reglink else ""),
            tone="live"))

    if not cards:
        cards = [UI.insight("NOTHING BUILT YET",
                            "Run <span class='mono'>python scripts/report.py</span> "
                            "for a league and this page will list it.", "b")]

    body = (UI.header("🏈 SPORTS PROPS", f"built {datetime.now():%b %d %H:%M}",
                      [("Leagues", str(len(cards)), "neu")]) +
            UI.tabs([("home", "DASHBOARDS", None)]) +
            UI.tabcontent("home",
                          UI.alert("<strong>This is a published record, not a "
                                   "tip sheet.</strong><br>Rows marked SHADOW "
                                   "carry zero stake. The ledger is in git "
                                   "precisely so it cannot be retro-adjusted.",
                                   kind="under", icon="📓") +
                          UI.section("Latest builds", *cards), active=True))
    out = root / "index.html"
    out.write_text(UI.document("Sports Props", "Sports Props", body))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int, default=None,
                    help="defaults to the current week by the calendar")
    ap.add_argument("--demo", action="store_true",
                    help="inject synthetic rows to preview the layout")
    a = ap.parse_args()
    if a.week is None:
        logged = [int(b["week"]) for b in read_csv(C.BETS)
                  if str(b.get("week", "")).isdigit()]
        a.week = C.default_week(logged)
        print(f"no --week given; using week {a.week} from the calendar")

    bets = read_csv(C.BETS)
    classes = read_csv(C.CLASSIFICATIONS)
    mech = read_csv(C.MECHANISM)
    hyp = read_yaml(C.HYPOTHESES)
    rules = read_yaml(C.RULES)

    if a.demo:
        bets = bets + demo_rows(a.week)
        classes = classes + [{
            "class_id": "C001", "hypothesis": "H1", "proposed_class": "FRONTIER",
            "rationale": "Sound read, variance outcome — no lesson, stays neutral.",
            "status": "PROPOSED"}]

    C.DASHBOARDS.mkdir(parents=True, exist_ok=True)
    out = C.DASHBOARDS / f"{C.LEAGUE}_{C.SEASON}_wk{a.week:02d}.html"
    out.write_text(build(a.week, bets, classes, mech, hyp, rules))
    print(f"built {out.relative_to(C.ROOT)}  ({out.stat().st_size:,} bytes)\n")

    if not validate(out):
        print("\n!! dashboard failed validation — not fit to ship")
        sys.exit(1)

    idx = build_index()
    print(f"built {idx.relative_to(C.ROOT)}")


if __name__ == "__main__":
    main()
