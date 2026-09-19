#!/usr/bin/env python3
"""Live console — the dashboard you can type into.

report.py renders a static file. This serves the same seven tabs from the same
tab_*() functions, the same components, and the same theme, then adds the write
controls: log a row, capture a closing price, group rows into a slip, mark
whether a thesis held, ratify a classification.

There is one design system. If this looks different from the generated
dashboard, that's a bug.

Everything it writes goes to the CSVs in state/ledger and commits, so the git
history stays the proof that no number was retro-adjusted.

  python scripts/app.py                    # http://127.0.0.1:8787
  NFL_AUTOCOMMIT=0 python scripts/app.py   # write, don't commit
  NFL_DEMO=1 python scripts/app.py         # read-only preview with synthetic rows

Bound to localhost. No auth, and it can move your record. Do not expose it.
"""
import csv, os, subprocess, sys, urllib.parse
from datetime import datetime, timezone, date
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
import components as UI
import report as R

PORT = int(os.getenv("NFL_APP_PORT", "8787"))
AUTOCOMMIT = os.getenv("NFL_AUTOCOMMIT", "1") == "1"
DEMO = os.getenv("NFL_DEMO", "0") == "1"
SLIPS = C.LEDGER / "slips.csv"

CLASSES = ["CONFIRMED", "GAMBLED", "TEACHING", "FRONTIER"]
SIDES = ["over", "under", "yes", "no"]
HELD = [("", "— did the thesis hold? —"), ("HELD", "HELD"),
        ("FAILED", "FAILED"), ("UNCLEAR", "UNCLEAR")]
HELD_VALUES = [h[0] for h in HELD]

BETS_EXTRA = ["slip_id", "thesis", "mechanism_held"]
SLIPS_COLS = ["slip_id", "season", "week", "date", "kind", "label",
              "price_stake", "price_close", "stake_units", "status",
              "review_note", "proposed_class", "ratified_class",
              "date_ratified", "ts_created"]

# The grid. Outcome is arithmetic; whether the thesis held is judgment. Their
# intersection is the classification — which the tool proposes and never ratifies.
GRID = {("WIN", "HELD"): ("CONFIRMED", "Clean evidence the mechanism works."),
        ("WIN", "FAILED"): ("GAMBLED", "Right result, wrong reasons. Hold and investigate."),
        ("LOSS", "HELD"): ("FRONTIER", "Sound process, variance outcome. No lesson."),
        ("LOSS", "FAILED"): ("TEACHING", "A real, fixable process defect.")}

SPACER = '<label class="fld"><span class="fld-l">&nbsp;</span>{}</label>'


# --------------------------------------------------------------------------- io
def read_csv(path, default_cols=None):
    p = Path(path)
    if not p.exists():
        return [], list(default_cols or [])
    with open(p, newline="") as f:
        r = csv.DictReader(f)
        return list(r), (r.fieldnames or list(default_cols or []))


def write_csv(path, fields, rows):
    tmp = Path(path).with_suffix(".tmp")
    with open(tmp, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    tmp.replace(path)


def migrate():
    """Additive only. Columns are appended, never dropped or reordered, so every
    earlier commit of the ledger still parses."""
    rows, fields = read_csv(C.BETS)
    missing = [c for c in BETS_EXTRA if c not in fields]
    if missing:
        fields = fields + missing
        for r in rows:
            for c in missing:
                r.setdefault(c, "")
        write_csv(C.BETS, fields, rows)
        print(f"   migrated bets.csv: +{', '.join(missing)}")
    if not SLIPS.exists():
        write_csv(SLIPS, SLIPS_COLS, [])
        print("   created slips.csv")


def commit(msg):
    if not AUTOCOMMIT or DEMO:
        return
    try:
        subprocess.run(["git", "add", "state/"], cwd=C.ROOT, capture_output=True)
        subprocess.run(["git", "commit", "-m", msg], cwd=C.ROOT, capture_output=True)
    except Exception:
        pass


def num(v, d=None):
    return R.num(v, d)


def legs_of(bets, sid):
    return [b for b in bets if b.get("slip_id") == sid]


def load_all():
    bets, _ = read_csv(C.BETS)
    if DEMO:
        bets = bets + R.demo_rows(1)
    slips, _ = read_csv(SLIPS, SLIPS_COLS)
    classes, _ = read_csv(C.CLASSIFICATIONS)
    mech, _ = read_csv(C.MECHANISM)
    hyp = R.read_yaml(C.HYPOTHESES)
    rules = R.read_yaml(C.RULES)
    return bets, slips, classes, mech, hyp, rules


def fmt(v, spec, dash="—"):
    return dash if v is None else format(v, spec)


# --------------------------------------------------------------------------- logic
def propose_class(legs):
    if not legs:
        return None, "No legs attached."
    if any(not l.get("outcome") for l in legs):
        return None, "Not every leg is graded yet."
    if any(not l.get("mechanism_held") for l in legs):
        return None, ("Mark whether each leg's thesis held. The tool knows what "
                      "happened; it cannot know whether the reasoning was sound.")
    holds = [l["mechanism_held"] for l in legs]
    if "UNCLEAR" in holds:
        return None, "A leg is unclear. Resolve it or leave the slip unclassified."
    won = all(l["outcome"] in ("WIN", "PUSH") for l in legs)
    held = all(h == "HELD" for h in holds)
    cls, why = GRID[("WIN" if won else "LOSS", "HELD" if held else "FAILED")]
    detail = ("every thesis held" if held
              else f"{sum(1 for h in holds if h == 'FAILED')} of {len(holds)} theses failed")
    return cls, f"{why} Slip {'won' if won else 'lost'}; {detail}."


def hyp_gate(bets, hyp):
    """Per-hypothesis progress toward min_n, with the mechanism rate alongside
    CLV. The two coming apart is the earliest warning available."""
    out = []
    for h in (hyp.get("hypotheses") or []):
        hid = h.get("id")
        rows = [b for b in bets if b.get("hypothesis") == hid]
        clvs = [c for c in (num(b.get("clv_cents")) for b in rows) if c is not None]
        judged = [b for b in rows if b.get("mechanism_held") in ("HELD", "FAILED")]
        held = sum(1 for b in judged if b["mechanism_held"] == "HELD")
        out.append({
            "id": hid, "name": h.get("name", ""), "tier": h.get("tier", "SHADOW"),
            "min_n": h.get("min_n") or 0, "n": len(rows),
            "mean_clv": sum(clvs) / len(clvs) if clvs else None, "clv_n": len(clvs),
            "hold_rate": (held / len(judged)) if judged else None,
            "hold_n": len(judged),
        })
    return out


# --------------------------------------------------------------------------- tabs
def tab_week_live(bets, slips, hyp, week):
    """report.tab_week, plus the three things that actually get skipped."""
    base = R.tab_week(bets, week)

    needs = [b for b in bets if b.get("ts_stake") and not b.get("price_close")]
    if needs:
        trs = []
        for b in needs:
            f = UI.form("/close",
                        UI.hidden("row_id", b["row_id"]),
                        '<input class="inp" name="line_close" placeholder="line" '
                        'aria-label="closing line">',
                        '<input class="inp" name="price_close" placeholder="price" '
                        'aria-label="closing price" required>',
                        UI.button("save", primary=False), inline=True)
            trs.append([f'<span class="mono">{UI.esc(b["row_id"])}</span>',
                        UI.esc(b.get("player")),
                        f'<span class="mono">{UI.esc(b.get("prop_type"))} '
                        f'{UI.esc(b.get("side"))} {UI.esc(b.get("line_stake"))} @ '
                        f'{UI.esc(b.get("price_stake"))}</span>', f])
        close_block = (UI.alert(
            f"<strong>{len(needs)} row(s) have no closing price.</strong><br>"
            "This is the only number in the system that cannot be recovered "
            "afterwards. Once the game kicks off it is gone for good, and CLV is "
            "the signal that resolves first.", kind="act", icon="⏱") +
            UI.table(["Row", "Player", "Bet", "Closing price"], trs))
    else:
        close_block = UI.insight("CLOSING PRICES",
                                 "Every logged row has a close. Nothing to do.", "g")

    strs = []
    for s in [x for x in slips if str(x.get("week")) == str(week)]:
        legs = legs_of(bets, s["slip_id"])
        graded = [l for l in legs if l.get("outcome")]
        if legs and len(graded) == len(legs):
            won = all(l["outcome"] in ("WIN", "PUSH") for l in legs)
            res = UI.badge("WON" if won else "LOST", "win" if won else "loss")
        else:
            res = UI.badge(f"OPEN {len(graded)}/{len(legs)}", "pending")
        stake = num(s.get("stake_units"), 0) or 0
        cls = (UI.badge(s["ratified_class"], s["ratified_class"].lower())
               if s.get("ratified_class") else '<span class="mono">—</span>')
        strs.append([f'<span class="mono">{UI.esc(s["slip_id"])}</span>',
                     UI.esc(s.get("label")),
                     f'<span class="mono">{len(legs)}</span>',
                     UI.badge(f"LIVE {stake:g}u", "live") if stake
                     else UI.badge("SHADOW", "shadow"),
                     res, cls, UI.ticketlink(s["slip_id"])])

    new_slip = UI.form("/slip/new",
                       UI.hidden("week", week),
                       UI.field("Label", "label", placeholder="Week 1 three-leg"),
                       UI.select("Kind", "kind", ["parlay", "single"]),
                       UI.field("Stake (units)", "stake_units", "0"),
                       SPACER.format(UI.button("open slip")),
                       title="Open a new slip")

    hopts = [("NONE", "NONE — unattributed, credits no hypothesis")] + [
        (h.get("id"), f"{h.get('id')} — {h.get('name')} [{h.get('tier', 'SHADOW')}]")
        for h in (hyp.get("hypotheses") or [])]
    slopts = [("", "— no slip —")] + [
        (s["slip_id"], f"{s['slip_id']} — {s.get('label')}") for s in slips]

    log_form = UI.form(
        "/log",
        UI.field("Week", "week", str(week), required=True),
        UI.field("Date", "date", date.today().isoformat(), kind="date", required=True),
        UI.field("Kickoff ET", "kickoff_et", placeholder="13:00"),
        UI.field("Game", "game", placeholder="TB @ CIN"),
        UI.select("Slip", "slip_id", slopts),
        UI.field("Player", "player", required=True),
        UI.field("Team", "team"),
        UI.field("Opponent", "opponent"),
        UI.field("Position", "position"),
        UI.select("Status", "status_at_stake", ["PROJECTED", "CONFIRMED"]),
        UI.select("Market", "prop_type", list(C.PROP_MARKETS)),
        UI.select("Side", "side", SIDES),
        UI.field("Line", "line_stake", required=True),
        UI.field("Price", "price_stake", placeholder="-115", required=True),
        UI.select("Book", "book_stake", list(C.BOOKMAKERS)),
        UI.select("Hypothesis", "hypothesis", hopts),
        UI.field("Stake (units)", "stake_units", "0"),
        UI.select("Conjunction", "conjunction",
                  [("false", "false — single condition"),
                   ("true", "true — needs more than one thing")]),
        UI.textarea("Thesis — what has to be true", "thesis", required=True,
                    placeholder="You will read this back after the game to decide "
                                "whether the reasoning held. Write it for that reader."),
        UI.textarea("Conditions this bet requires", "expression_conditions",
                    required=True,
                    placeholder="One per line. If you can only think of one, check again."),
        SPACER.format(UI.button("log row")),
        title="Log a row")

    guard = UI.insight(
        "THE FORM ENFORCES THE TIER",
        "Setting a stake above zero on a hypothesis that is not "
        "<strong>PROVEN</strong> is refused at submit, not warned about. A rule "
        "that lives only in a markdown file is a rule you can talk yourself past "
        "at 12:55 on a Sunday.", "r")

    return (base +
            UI.section("Needs a closing price", close_block) +
            UI.section(f"Slips — week {week}",
                       UI.table(["Slip", "Label", "Legs", "Stake", "Result",
                                 "Class", ""], strs), new_slip) +
            UI.section("Log a row", log_form, guard))


def tab_confidence_live(bets, slips, classes, hyp):
    base = R.tab_confidence(classes, hyp)

    pend = []
    for s in slips:
        if s.get("ratified_class"):
            continue
        proposed, why = propose_class(legs_of(bets, s["slip_id"]))
        if not proposed:
            continue
        f = UI.form("/slip/ratify",
                    UI.hidden("slip_id", s["slip_id"]),
                    UI.select("Your classification", "ratified_class", CLASSES, proposed),
                    UI.field("Review note", "review_note",
                             placeholder="If you disagree, say why — the "
                                         "disagreement is the signal"),
                    SPACER.format(UI.button("ratify")))
        pend.append(UI.panel(f"{s['slip_id']} · {s.get('label')}",
                             [UI.badge(proposed + " proposed", proposed.lower())],
                             f"<p>{UI.esc(why)}</p>{f}", tone="info"))

    slip_block = ("".join(pend) if pend else UI.insight(
        "NOTHING TO RATIFY",
        "A slip reaches this queue once every leg is graded and every thesis is "
        "marked. Until then there is nothing to propose, and saying so beats "
        "guessing.", "b"))

    gtrs = []
    for g in hyp_gate(bets, hyp):
        clv_txt = fmt(g["mean_clv"], "+.2f")
        hold_txt = "—" if g["hold_rate"] is None else f'{g["hold_rate"] * 100:.0f}%'
        gate_cell = (UI.gatebar(g["n"], g["min_n"]) if g["min_n"]
                     else f'<span class="mono">{g["n"]}</span>')
        gtrs.append([
            f'<span class="mono">{UI.esc(g["id"])}</span>',
            UI.esc(g["name"]),
            UI.badge(g["tier"], g["tier"].lower()),
            gate_cell,
            f'<span class="mono {R.tone_for(g["mean_clv"])}">{clv_txt}</span>'
            f'<span class="mono" style="color:var(--muted)"> (n={g["clv_n"]})</span>',
            f'<span class="mono">{hold_txt}</span>'
            f'<span class="mono" style="color:var(--muted)"> ({g["hold_n"]})</span>',
        ])

    gate_note = UI.insight(
        "WHY THE RULES DO NOT MOVE WEEKLY",
        "Evidence accumulates every week; the rules change only at the gate. A "
        "system that retunes its triggers on ten rows is fitting noise, and it "
        "will look like learning while it drifts. <strong>Thesis held</strong> is "
        "the mechanism rate from ticket reviews — independent of whether the bets "
        "won. The two coming apart is the earliest warning you get.", "tl")

    return (base +
            UI.section("Slips awaiting ratification", slip_block) +
            UI.section("Distance to gate",
                       UI.table(["H", "Name", "Tier", "Rows to gate",
                                 "Mean CLV", "Thesis held"], gtrs), gate_note))


def tab_ticket(bets, slips, sid):
    s = next((x for x in slips if x["slip_id"] == sid), None)
    if not s:
        return UI.alert("<strong>No such slip.</strong>", kind="act", icon="⚠")
    legs = legs_of(bets, sid)

    head = UI.alert(
        "<strong>The two axes are separate.</strong><br>Whether the slip won is "
        "arithmetic. Whether each thesis held is judgment, and only you make it. "
        "A win on a broken thesis is a worse event than a loss on a sound one — "
        "this page exists so that distinction survives contact with the "
        "scoreboard.", kind="under", icon="⚖")

    blocks = []
    for l in legs:
        out = l.get("outcome") or ""
        clv = num(l.get("clv_cents"))
        badges = [UI.badge(out or "UNGRADED", out.lower() if out else "pending"),
                  UI.badge(l.get("hypothesis") or "NONE", "info")]
        verdict_form = UI.form("/leg/held",
                               UI.hidden("row_id", l["row_id"]),
                               UI.hidden("slip_id", sid),
                               UI.select("Did the thesis hold?", "mechanism_held",
                                         HELD, l.get("mechanism_held") or "", auto=True))
        body = (f'<p><strong>Before the game:</strong> '
                f'{UI.esc(l.get("thesis") or l.get("expression_conditions") or "(none recorded)")}</p>'
                f'<div class="f5box"><table><tr class="hdr">'
                f'<td>bet</td><td>result</td><td>vs fair</td><td>clv</td></tr><tr>'
                f'<td>{UI.esc(l.get("side"))} {UI.esc(l.get("line_stake"))} @ '
                f'{UI.esc(l.get("price_stake"))}</td>'
                f'<td>{UI.esc(l.get("actual_result")) or "—"}</td>'
                f'<td>{UI.esc(l.get("margin_vs_fair")) or "—"}</td>'
                f'<td class="{R.tone_for(clv)}">{fmt(clv, "+.2f")}</td>'
                f'</tr></table></div>{verdict_form}')
        tone = {"WIN": "win", "LOSS": "loss"}.get(out, "shadow")
        blocks.append(UI.panel(f'{l.get("player")} · {l.get("game")}', badges, body, tone))

    if not blocks:
        blocks = [UI.insight("NO LEGS", "Attach rows to this slip below, or log a "
                             "new row against it from the WEEK tab.", "b")]

    free = [b for b in bets if not b.get("slip_id")]
    if free:
        attach = UI.form("/slip/attach",
                         UI.hidden("slip_id", sid),
                         UI.select("Row", "row_id",
                                   [(b["row_id"],
                                     f'{b["row_id"]} — {b.get("player")} '
                                     f'{b.get("prop_type")} {b.get("side")} '
                                     f'{b.get("line_stake")}') for b in free]),
                         SPACER.format(UI.button("attach", primary=False)),
                         title="Attach an existing row")
    else:
        attach = UI.insight("NOTHING UNATTACHED",
                            "Every logged row already belongs to a slip.", "b")

    proposed, why = propose_class(legs)
    if s.get("ratified_class"):
        verdict = UI.alert(
            f"<strong>Ratified: {UI.esc(s['ratified_class'])}</strong><br>"
            f"{UI.esc(s.get('review_note') or '')}", kind="res", icon="✓")
    elif proposed:
        verdict = UI.panel(
            "Proposed — awaiting your ratification",
            [UI.badge(proposed, proposed.lower())],
            f"<p>{UI.esc(why)}</p>" +
            UI.form("/slip/ratify",
                    UI.hidden("slip_id", sid),
                    UI.select("Your classification", "ratified_class", CLASSES, proposed),
                    UI.field("Review note", "review_note",
                             placeholder="If you disagree, say why"),
                    SPACER.format(UI.button("ratify"))),
            tone="info")
    else:
        verdict = UI.insight("NOT YET CLASSIFIABLE", UI.esc(why), "b")

    return (head +
            UI.section(f"{sid} · {UI.esc(s.get('label'))} — legs", *blocks) +
            UI.section("Attach", attach) +
            UI.section("Verdict", verdict))


# --------------------------------------------------------------------------- build
def build_page(week, flash=None, ticket=None):
    bets, slips, classes, mech, hyp, rules = load_all()

    clvs = [c for c in (num(b.get("clv_cents")) for b in bets) if c is not None]
    mean_clv = sum(clvs) / len(clvs) if clvs else None
    live = [b for b in bets if (num(b.get("stake_units"), 0) or 0) > 0]
    pnl = sum(num(b.get("pnl_units"), 0) or 0 for b in live)
    hs = hyp.get("hypotheses") or []
    proven = sum(1 for h in hs if (h.get("tier") or "").upper() == "PROVEN")
    open_closes = sum(1 for b in bets if b.get("ts_stake") and not b.get("price_close"))

    logged = {int(b["week"]) for b in bets if str(b.get("week", "")).isdigit()}
    picker = UI.weekpicker(week, range(1, C.WEEKS + 1), logged)
    cal = C.default_week(logged)
    head = UI.header(
        "🏈 NFL PROPS",
        f"{C.SEASON} · console" + (" · DEMO" if DEMO else ""),
        [("Mean CLV", f"{mean_clv:+.2f}c" if mean_clv is not None else "—",
          R.tone_for(mean_clv)),
         ("P&L (live)", f"{pnl:+.2f}u", R.tone_for(pnl)),
         ("Rows logged", str(len(bets)), "neu"),
         ("Slips", str(len(slips)), "neu"),
         ("Needs close", str(open_closes), "neg" if open_closes else "pos"),
         ("Hypotheses", f"{proven} proven / {len(hs)}", "neu")],
        control=picker)

    pending_ratify = any(not s.get("ratified_class")
                         and propose_class(legs_of(bets, s["slip_id"]))[0]
                         for s in slips)
    items = [("week", f"WEEK {week}", str(open_closes) if open_closes else None),
             ("performance", "PERFORMANCE", None),
             ("confidence", "CONFIDENCE", "RATIFY" if pending_ratify else None),
             ("posthoc", f"WK {week - 1} POST-HOC", None),
             ("hypotheses", "HYPOTHESES", None),
             ("tracking", "TRACKING", None),
             ("methodology", "METHODOLOGY", None)]
    contents = []
    if ticket:
        items.insert(0, ("ticket", "TICKET", None))
        contents.append(UI.tabcontent("ticket", tab_ticket(bets, slips, ticket),
                                      active=True))
    contents += [
        UI.tabcontent("week", tab_week_live(bets, slips, hyp, week), active=not ticket),
        UI.tabcontent("performance", R.tab_performance(bets)),
        UI.tabcontent("confidence", tab_confidence_live(bets, slips, classes, hyp)),
        UI.tabcontent("posthoc", R.tab_posthoc(bets, week)),
        UI.tabcontent("hypotheses", R.tab_hypotheses(hyp)),
        UI.tabcontent("tracking", R.tab_tracking(bets, mech)),
        UI.tabcontent("methodology", R.tab_methodology(rules)),
    ]

    offweek = ("" if week == cal else UI.flash(
        "err", f"Viewing week {week}. The current week by the calendar is "
               f"{cal} — switch back in the header when you are done."))
    demo_note = (UI.flash("err", "DEMO MODE — synthetic rows are mixed in to "
                                 "preview the layout. Nothing here is your record.")
                 if DEMO else "")
    fl = UI.flash(*flash) if flash else ""
    body = head + UI.tabs(items) + demo_note + offweek + fl + "".join(contents)
    return UI.document("NFL Props", f"NFL Props — {C.SEASON} Week {week}", body)


# --------------------------------------------------------------------------- writes
def do_log(form):
    bets, fields = read_csv(C.BETS)
    hyp = R.read_yaml(C.HYPOTHESES)
    reg = {h.get("id"): h for h in (hyp.get("hypotheses") or [])}
    hid = form.get("hypothesis", "NONE")
    stake = num(form.get("stake_units"), 0) or 0
    if hid != "NONE":
        h = reg.get(hid)
        if not h:
            return "err", f"{hid} is not in the registry."
        tier = h.get("tier", "SHADOW")
        if stake > 0 and tier != "PROVEN":
            return "err", (f"{hid} is {tier}. Only PROVEN hypotheses take money — "
                           f"log it at 0 units and let it earn the tier.")
    else:
        tier = "NONE"
    try:
        week = int(form.get("week", ""))
    except ValueError:
        return "err", "Week must be a number."

    row = {k: "" for k in fields}
    row.update({
        "row_id": f"W{week}R{sum(1 for b in bets if str(b.get('week')) == str(week)) + 1:03d}",
        "season": str(C.SEASON), "week": str(week), "date": form.get("date", ""),
        "kickoff_et": form.get("kickoff_et", ""), "game": form.get("game", ""),
        "player": form.get("player", "").strip(), "team": form.get("team", ""),
        "opponent": form.get("opponent", ""), "position": form.get("position", ""),
        "prop_type": form.get("prop_type", ""), "side": form.get("side", ""),
        "line_stake": form.get("line_stake", ""),
        "price_stake": form.get("price_stake", ""),
        "book_stake": form.get("book_stake", ""),
        "ts_stake": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "hypothesis": hid, "tier_at_stake": tier,
        "thesis": " ".join(form.get("thesis", "").split()),
        "expression_conditions": " | ".join(
            x.strip() for x in form.get("expression_conditions", "").splitlines()
            if x.strip()),
        "conjunction": form.get("conjunction", "false"),
        "status_at_stake": form.get("status_at_stake", "PROJECTED"),
        "stake_units": str(stake), "slip_id": form.get("slip_id", ""),
        "mechanism_held": "",
    })
    bets.append(row)
    write_csv(C.BETS, fields, bets)
    commit(f"log {row['row_id']} {row['player']} ({hid})")
    where = f" on {row['slip_id']}" if row["slip_id"] else ""
    return "ok", (f"Logged {row['row_id']}{where} as "
                  f"{'shadow' if not stake else str(stake) + 'u'}.")


def do_close(form):
    bets, fields = read_csv(C.BETS)
    rid = form.get("row_id", "")
    row = next((b for b in bets if b.get("row_id") == rid), None)
    if not row:
        return "err", f"No row {rid}."
    if row.get("price_close"):
        return "err", f"{rid} already has a close. Corrections are appended, not edited."
    price = (form.get("price_close") or "").strip()
    if not price:
        return "err", "A closing price is required."
    row["price_close"] = price
    if (form.get("line_close") or "").strip():
        row["line_close"] = form["line_close"].strip()
    row["book_close"] = "manual"
    row["ts_close"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    try:
        row["clv_cents"] = str(C.clv_cents(row["price_stake"], price))
        row["clv_pct"] = str(C.clv_pct(row["price_stake"], price))
    except Exception as ex:
        return "err", f"CLV calculation failed for {rid}: {ex}"
    write_csv(C.BETS, fields, bets)
    commit(f"close {rid} @ {price}")
    return "ok", f"{rid} closed at {price} — CLV {row['clv_cents']}."


def do_new_slip(form):
    slips, fields = read_csv(SLIPS, SLIPS_COLS)
    try:
        week = int(form.get("week", ""))
    except ValueError:
        return "err", "Week must be a number.", None
    n = len(slips) + 1
    while any(s["slip_id"] == f"S{week}-{n:03d}" for s in slips):
        n += 1
    sid = f"S{week}-{n:03d}"
    slips.append({"slip_id": sid, "season": str(C.SEASON), "week": str(week),
                  "date": date.today().isoformat(),
                  "kind": form.get("kind", "parlay"),
                  "label": (form.get("label") or "").strip() or f"Week {week} slip",
                  "stake_units": str(num(form.get("stake_units"), 0) or 0),
                  "status": "OPEN",
                  "ts_created": datetime.now(timezone.utc).isoformat(timespec="seconds")})
    write_csv(SLIPS, fields, slips)
    commit(f"open slip {sid}")
    return "ok", f"Opened {sid}.", sid


def do_attach(form):
    bets, fields = read_csv(C.BETS)
    rid, sid = form.get("row_id", ""), form.get("slip_id", "")
    row = next((b for b in bets if b.get("row_id") == rid), None)
    if not row:
        return "err", f"No row {rid}."
    if row.get("slip_id"):
        return "err", f"{rid} is already on {row['slip_id']}."
    row["slip_id"] = sid
    write_csv(C.BETS, fields, bets)
    commit(f"attach {rid} to {sid}")
    return "ok", f"{rid} attached to {sid}."


def do_held(form):
    bets, fields = read_csv(C.BETS)
    rid = form.get("row_id", "")
    row = next((b for b in bets if b.get("row_id") == rid), None)
    if not row:
        return "err", f"No row {rid}."
    val = form.get("mechanism_held", "")
    if val not in HELD_VALUES:
        return "err", "Unrecognised value."
    row["mechanism_held"] = val
    write_csv(C.BETS, fields, bets)
    commit(f"thesis verdict {rid}: {val or 'cleared'}")
    return "ok", f"{rid}: thesis marked {val or 'cleared'}."


def do_ratify(form):
    slips, fields = read_csv(SLIPS, SLIPS_COLS)
    bets, _ = read_csv(C.BETS)
    sid = form.get("slip_id", "")
    s = next((x for x in slips if x["slip_id"] == sid), None)
    if not s:
        return "err", f"No slip {sid}."
    if s.get("ratified_class"):
        return "err", f"{sid} is already ratified."
    chosen = form.get("ratified_class", "")
    if chosen not in CLASSES:
        return "err", f"{chosen} is not one of the four classes."
    proposed, _ = propose_class(legs_of(bets, sid))
    s.update({"proposed_class": proposed or "", "ratified_class": chosen,
              "date_ratified": date.today().isoformat(),
              "review_note": form.get("review_note", ""), "status": "CLOSED"})
    write_csv(SLIPS, fields, slips)
    commit(f"ratify {sid} as {chosen}")
    extra = (f", overriding the proposed {proposed}"
             if proposed and proposed != chosen else "")
    return "ok", f"{sid} ratified as {chosen}{extra}."


# --------------------------------------------------------------------------- server
class Handler(BaseHTTPRequestHandler):
    server_version = "nfl-props-console"

    def _send(self, body, code=200):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _flash(self):
        p = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        for k in ("ok", "err"):
            if k in p:
                return (k, p[k][0])
        return None

    def _go(self, path, kind, msg, week=None):
        parts = [f"{kind}={urllib.parse.quote(msg)}"]
        if week is not None:
            parts.append(f"week={week}")
        sep = "&" if "?" in path else "?"
        self.send_response(303)
        self.send_header("Location", f"{path}{sep}{'&'.join(parts)}")
        self.end_headers()

    def _week(self, q):
        """Explicit ?week= wins. Otherwise the calendar decides — the week you
        want is the one you have not logged yet, so deriving it from the ledger
        would open on last week every Thursday."""
        if q.get("week") and str(q["week"][0]).isdigit():
            return max(1, min(C.WEEKS, int(q["week"][0])))
        bets, _ = read_csv(C.BETS)
        logged = [int(b["week"]) for b in bets if str(b.get("week", "")).isdigit()]
        return C.default_week(logged)

    def do_GET(self):
        u = urllib.parse.urlparse(self.path)
        q = urllib.parse.parse_qs(u.query)
        if u.path == "/":
            self._send(build_page(self._week(q), self._flash()))
        elif u.path.startswith("/slip/"):
            sid = u.path.split("/slip/", 1)[1]
            self._send(build_page(self._week(q), self._flash(), ticket=sid))
        else:
            self._send(build_page(self._week(q), ("err", "No such page.")), 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        form = {k: v[0] for k, v in
                urllib.parse.parse_qs(self.rfile.read(n).decode()).items()}
        p = urllib.parse.urlparse(self.path).path
        if DEMO:
            return self._go("/", "err", "Demo mode is read-only.")
        wk = form.get("week") if str(form.get("week", "")).isdigit() else None
        if p == "/log":
            self._go("/", *do_log(form), week=wk)
        elif p == "/close":
            self._go("/", *do_close(form), week=wk)
        elif p == "/slip/new":
            k, m, sid = do_new_slip(form)
            self._go(f"/slip/{sid}" if sid else "/", k, m)
        elif p == "/slip/attach":
            self._go(f"/slip/{form.get('slip_id', '')}", *do_attach(form))
        elif p == "/slip/ratify":
            self._go(f"/slip/{form.get('slip_id', '')}", *do_ratify(form))
        elif p == "/leg/held":
            self._go(f"/slip/{form.get('slip_id', '')}", *do_held(form))
        else:
            self._go("/", "err", "Unknown action.")

    def log_message(self, fmt_, *args):
        sys.stderr.write(f"  {fmt_ % args}\n")


def main():
    print(f"== NFL props console — {C.SEASON} ==")
    if not DEMO:
        migrate()
    print(f"   autocommit: {'on' if AUTOCOMMIT and not DEMO else 'off'}"
          + ("   DEMO (read-only)" if DEMO else ""))
    print(f"   http://127.0.0.1:{PORT}\n")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
