#!/usr/bin/env python3
"""The console — the write-enabled view, in a browser, with nothing installed.

WHAT THIS REPLACES

app.py was the live console: same tabs, plus the controls to log a row, capture
a close, mark whether a thesis held, and ratify. It was correct and it was
unreachable -- it needs Python on a machine that cannot install Python. Three
weeks of recommendations went into an empty ledger because of it.

This is app.py's job moved to a page that GitHub Pages serves. It is not a
third view; it is the second one, relocated. app.py stays in the repo for a
machine that can run it, but it is no longer the way the ledger gets written.

HOW A STATIC PAGE WRITES TO A LEDGER

It does not. GitHub Pages serves files; it runs nothing. What the page can do
is ask GitHub to run something, by POSTing to the workflow-dispatch endpoint
with a token the user supplies. So:

    select in the page -> dispatch ledger.yml -> ledger.py writes the CSV
      -> report.py and console.py rebuild -> Pages redeploys -> page reflects it

which takes about a minute end to end. The page says so rather than pretending
the write was instant, because a UI that claims success before the write lands
is how a ledger and a screen quietly disagree.

THE TOKEN

A fine-grained personal access token, scoped to this one repository, with
Actions: read and write. It lives in the browser's localStorage on the user's
own machine and is sent only to api.github.com. It is never committed, never
embedded here, and never passes through Claude. The page has a field for it;
the user pastes their own. A public repo makes this page public -- the token
does not travel with it.

READ PATH

Everything the page displays is embedded at build time: this week's
recommendations, the slips parlay.py built, the ledger rows, the hypothesis
registry. No fetch, no CORS, no cache. The page is as fresh as the last build,
and the build runs on every write.

  python scripts/console.py --week 3
"""
import argparse, csv, json, sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
import components as UI
from report import read_yaml

REPO = "saucyeightyfive/sports-props"


def read_csv(path):
    p = Path(path)
    if not p.exists():
        return []
    with open(p, newline="") as f:
        return list(csv.DictReader(f))


def load(week):
    """Everything the page needs, as one JSON blob embedded in the document."""
    recs, slips = [], []
    rp = C.STATE / f"recommendations_wk{week:02d}.json"
    if rp.exists():
        d = json.loads(rp.read_text())
        recs = d.get("recommendations", [])
        correlated = d.get("correlated_games", [])
        thin = d.get("too_thin", [])
    else:
        correlated, thin = [], []
    pp = C.STATE / f"parlays_wk{week:02d}.json"
    if pp.exists():
        slips = json.loads(pp.read_text()).get("slips", [])

    hyp = {h["id"]: h for h in (read_yaml(C.HYPOTHESES).get("hypotheses") or [])}
    bets = read_csv(C.BETS)
    return {
        "repo": REPO, "league": C.LEAGUE, "season": C.SEASON, "week": week,
        "built": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "recommendations": recs, "slips": slips, "too_thin": thin,
        "correlated": correlated,
        "bets": bets,
        "logged_keys": [f"{b.get('player')}|{b.get('prop_type')}|"
                        f"{b.get('side')}|{b.get('line_stake')}"
                        for b in bets if str(b.get("week")) == str(week)],
        "hypotheses": {k: {"tier": v.get("tier", "SHADOW"),
                           "status": v.get("status", ""),
                           "claim": (v.get("claimed_edge") or {}).get("value"),
                           "unit": (v.get("claimed_edge") or {}).get("unit"),
                           "min_n": v.get("min_n")}
                       for k, v in hyp.items()},
    }


# --------------------------------------------------------------------------- css
EXTRA_CSS = """
.cwrap{max-width:1180px;margin:0 auto;padding:22px;}
.leg{background:var(--surface);border:1px solid var(--border);border-left:4px solid var(--purple);border-radius:4px;padding:13px 16px;margin-bottom:10px;display:grid;grid-template-columns:26px 1fr;gap:12px;align-items:start;}
.leg.sel{border-color:var(--accent);border-left-color:var(--accent);background:var(--surface2);}
.leg.done{opacity:.55;border-left-color:var(--border2);}
.leg input[type=checkbox]{width:17px;height:17px;accent-color:var(--accent);cursor:pointer;margin-top:2px;}
.leg-t{font-family:'IBM Plex Mono',monospace;font-size:13px;font-weight:700;}
.leg-s{font-size:11px;color:var(--muted);margin-top:2px;}
.leg-w{font-size:12px;color:var(--text);margin-top:7px;line-height:1.45;}
.nums{display:flex;gap:8px;flex-wrap:wrap;margin-top:9px;align-items:flex-end;}
.nf{display:flex;flex-direction:column;gap:3px;}
.nf label{font-size:9px;color:var(--muted);text-transform:uppercase;letter-spacing:.08em;}
.nf input{background:var(--bg);border:1px solid var(--border2);color:var(--text);font-family:'IBM Plex Mono',monospace;font-size:12px;padding:5px 7px;border-radius:3px;width:84px;}
.nf input:focus{outline:none;border-color:var(--accent);}
.nf input.edited{border-color:var(--accent);color:var(--accent);}
.evsplit{display:flex;gap:14px;flex-wrap:wrap;margin-top:7px;font-family:'IBM Plex Mono',monospace;font-size:11px;}
.evsplit b{font-weight:700;}
.tray{position:sticky;bottom:0;background:var(--surface);border-top:2px solid var(--accent);padding:13px 22px;display:flex;gap:14px;align-items:center;flex-wrap:wrap;z-index:20;}
.tray-c{font-family:'IBM Plex Mono',monospace;font-size:13px;font-weight:700;color:var(--accent);}
.btn{font-family:'IBM Plex Mono',monospace;font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;padding:9px 16px;border-radius:3px;border:1px solid var(--border2);background:var(--surface2);color:var(--text);cursor:pointer;transition:all .15s;}
.btn:hover:not(:disabled){border-color:var(--accent);color:var(--accent);}
.btn.pri{background:var(--accent);color:#000;border-color:var(--accent);}
.btn.pri:hover:not(:disabled){filter:brightness(1.12);}
.btn:disabled{opacity:.4;cursor:not-allowed;}
.tog{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted);cursor:pointer;}
.tog input{accent-color:var(--accent);width:15px;height:15px;cursor:pointer;}
.tokbar{background:var(--surface2);border:1px solid var(--border2);border-radius:4px;padding:13px 16px;margin-bottom:18px;}
.tokbar input{background:var(--bg);border:1px solid var(--border2);color:var(--text);font-family:'IBM Plex Mono',monospace;font-size:12px;padding:7px 9px;border-radius:3px;width:330px;max-width:100%;}
.tokrow{display:flex;gap:9px;align-items:center;flex-wrap:wrap;}
.dot{width:8px;height:8px;border-radius:50%;background:var(--red);display:inline-block;}
.dot.ok{background:var(--green);}
.log{font-family:'IBM Plex Mono',monospace;font-size:11px;background:var(--bg);border:1px solid var(--border);border-radius:3px;padding:11px 13px;margin-top:11px;white-space:pre-wrap;color:var(--muted);max-height:220px;overflow:auto;}
.trk{display:grid;grid-template-columns:repeat(3,1fr);gap:0;margin-top:9px;border:1px solid var(--border);border-radius:3px;overflow:hidden;}
.trk div{padding:7px 10px;font-size:10px;text-align:center;background:var(--bg);color:var(--muted);text-transform:uppercase;letter-spacing:.07em;border-right:1px solid var(--border);}
.trk div:last-child{border-right:none;}
.trk div.on{background:#1a3d2a;color:var(--green);font-weight:700;}
.trk div.wait{background:#3d3210;color:var(--accent);font-weight:700;}
.hint{font-size:11px;color:var(--muted);margin-top:5px;line-height:1.5;}
"""


# --------------------------------------------------------------------------- js
APP_JS = r"""
const D = window.__DATA__;
const LS_TOK = 'sp_gh_token';
const sel = new Map();          // pick index -> {line, price, book}

const $ = s => document.querySelector(s);
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function tok(){ try { return localStorage.getItem(LS_TOK) || ''; } catch(e){ return ''; } }
function setTok(v){ try { v ? localStorage.setItem(LS_TOK, v) : localStorage.removeItem(LS_TOK); } catch(e){} paintTok(); }
function paintTok(){
  const has = !!tok();
  $('#tokdot').className = 'dot' + (has ? ' ok' : '');
  $('#tokmsg').textContent = has
    ? 'Token saved in this browser. Entries will be submitted to GitHub.'
    : 'No token. You can browse and select, but Enter is disabled until you add one.';
  // A control that needs BOTH a token and a selection must satisfy both. An
  // earlier version enabled Enter the moment a token was saved, which offered
  // a button that could only decline.
  document.querySelectorAll('.needtok').forEach(b => {
    b.disabled = !has || (b.classList.contains('needsel') && !sel.size);
  });
}

function mark(i){
  const card = document.querySelector('.leg[data-i="'+i+'"]');
  if (card) card.classList.toggle('sel', sel.has(i));
  const n = sel.size;
  $('#count').textContent = n === 0 ? 'nothing selected'
    : n + ' leg' + (n===1?'':'s') + ' selected';
  document.querySelectorAll('.needsel').forEach(b => b.disabled = !n || !tok());
  const sl = $('#asslip');
  if (sl) { sl.disabled = n < 2; if (n < 2) sl.checked = false; }
}

function toggle(i, on){
  if (on) {
    const c = document.querySelector('.leg[data-i="'+i+'"]');
    sel.set(i, {
      line:  parseFloat(c.querySelector('.f-line').value),
      price: parseInt(c.querySelector('.f-price').value, 10),
      book:  c.querySelector('.f-book').value.trim(),
    });
  } else sel.delete(i);
  mark(i);
}

function edited(i, field, el){
  el.classList.toggle('edited', el.value !== el.dataset.orig);
  if (!sel.has(i)) return;
  const v = sel.get(i);
  v[field] = field === 'book' ? el.value.trim()
           : field === 'price' ? parseInt(el.value, 10) : parseFloat(el.value);
  sel.set(i, v);
}

function say(msg, tone){
  const l = $('#log');
  l.style.color = tone === 'bad' ? 'var(--red)'
                : tone === 'good' ? 'var(--green)' : 'var(--muted)';
  l.textContent = msg;
}

async function enter(){
  if (!sel.size) return;
  const asSlip = $('#asslip') && $('#asslip').checked;
  const legs = [...sel.entries()].map(([i, v]) => ({
    pick: i + 1, line: v.line, price: v.price, book: v.book, stake: 0
  }));

  // Correlation is checked here, not only at build time, because the user can
  // select a combination the engine never proposed.
  if (asSlip) {
    const games = legs.map(l => D.recommendations[l.pick-1].game);
    const dupe = games.find((g,i) => games.indexOf(g) !== i);
    if (dupe && !confirm(
        'Two or more of these legs come from ' + dupe + '.\n\n' +
        'Legs from one game are not independent -- multiplying their ' +
        'probabilities overstates the slip. Enter it anyway?')) return;
  }

  const payload = { week: D.week, slip: asSlip, legs };
  const btns = document.querySelectorAll('.needsel, .needtok');
  btns.forEach(b => b.disabled = true);
  say('submitting ' + legs.length + ' leg(s)...');

  try {
    const r = await fetch(
      'https://api.github.com/repos/' + D.repo +
      '/actions/workflows/ledger.yml/dispatches', {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer ' + tok(),
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
      },
      body: JSON.stringify({ ref: 'main', inputs: {
        action: 'enter', league: D.league, week: String(D.week),
        payload: JSON.stringify(payload),
      }}),
    });
    if (r.status === 204) {
      say('Submitted.\n\n' + legs.length + ' leg(s) sent' +
          (asSlip ? ' as one slip' : ' as singles') + '.\n\n' +
          'The ledger is written by the run, not by this page. Give it about a ' +
          'minute, then reload -- the rows appear under TRACKING once the run ' +
          'finishes and Pages redeploys.\n\n' +
          'Watch it: github.com/' + D.repo + '/actions', 'good');
      sel.clear();
      document.querySelectorAll('.leg input[type=checkbox]').forEach(c => c.checked = false);
      document.querySelectorAll('.leg').forEach(c => c.classList.remove('sel'));
      mark(-1);
    } else if (r.status === 401 || r.status === 403) {
      say('GitHub refused the token (' + r.status + ').\n\n' +
          'It needs Actions: read and write on ' + D.repo + ', and it must not ' +
          'be expired. Nothing was written.', 'bad');
    } else if (r.status === 404) {
      say('404 from GitHub.\n\nEither the token cannot see ' + D.repo + ', or ' +
          'ledger.yml is not on the main branch yet. Nothing was written.', 'bad');
    } else {
      const t = await r.text();
      say('GitHub returned ' + r.status + '. Nothing was written.\n\n' + t, 'bad');
    }
  } catch (e) {
    say('The request never reached GitHub: ' + e.message +
        '\n\nNothing was written.', 'bad');
  } finally {
    paintTok(); mark(-1);
  }
}

function selectAll(){
  document.querySelectorAll('.leg:not(.done) input[type=checkbox]').forEach(c => {
    if (!c.checked) { c.checked = true; toggle(parseInt(c.dataset.i,10), true); }
  });
}
function clearAll(){
  document.querySelectorAll('.leg input[type=checkbox]').forEach(c => c.checked = false);
  sel.clear(); document.querySelectorAll('.leg').forEach(c => c.classList.remove('sel'));
  mark(-1);
}

function useSlip(n){
  clearAll();
  D.slips[n].legs.forEach(leg => {
    const i = D.recommendations.findIndex(r =>
      r.player === leg.player && r.market === leg.market && r.line === leg.line);
    if (i < 0) return;
    const c = document.querySelector('.leg[data-i="'+i+'"] input[type=checkbox]');
    if (c && !c.disabled) { c.checked = true; toggle(i, true); }
  });
  if ($('#asslip')) $('#asslip').checked = sel.size >= 2;
  // components.py renders tabs as showTab(key, this); PICKS is the first.
  const first = document.querySelectorAll('.tab')[0];
  if (first) showTab('picks', first);
  window.scrollTo({top: 0, behavior: 'smooth'});
}

document.addEventListener('DOMContentLoaded', () => {
  paintTok();
  $('#toksave').onclick = () => { setTok($('#tokin').value.trim()); $('#tokin').value=''; };
  $('#tokclear').onclick = () => setTok('');
  document.querySelectorAll('.leg input[type=checkbox]').forEach(c => {
    c.onchange = () => toggle(parseInt(c.dataset.i, 10), c.checked);
  });
  document.querySelectorAll('.leg .f-line, .leg .f-price, .leg .f-book').forEach(el => {
    el.oninput = () => edited(parseInt(el.dataset.i,10), el.dataset.f, el);
  });
  $('#btnEnter').onclick = enter;
  $('#btnAll').onclick = selectAll;
  $('#btnNone').onclick = clearAll;
  mark(-1);
});
"""


# ------------------------------------------------------------------------ render
def leg_card(i, r, already):
    tone = " done" if already else ""
    ev, hyp_ev, shop_ev = r["ev_pct"], r["ev_hypothesis_pct"], r["ev_shopping_pct"]
    cls = lambda v: "pos" if v > 0 else "neg"
    vac = (f"Absorbing the {r.get('vacated_share',0):.0%} target share vacated by "
           f"{UI.esc(r.get('vacated_by','?'))} ({UI.esc(r.get('vacated_status',''))})."
           if r.get("vacated_by") else "")
    return f"""
<div class="leg{tone}" data-i="{i}">
  <input type="checkbox" data-i="{i}"{' disabled' if already else ''}>
  <div>
    <div class="leg-t">{UI.esc(r['player'])} · {UI.esc(r['market'])} {r['side']} {r['line']}</div>
    <div class="leg-s">{UI.esc(r['team'])} — {UI.esc(r['game'])} · {r['hypothesis']}
      {' · <b style="color:var(--muted)">already on the ledger</b>' if already else ''}</div>
    <div class="leg-w">{vac} Consensus fair {r['fair_prob']}%; the price needs
      {r['breakeven_prob']}% to break even.</div>
    <div class="evsplit">
      <span>EV <b class="{cls(ev)}">{ev:+.2f}%</b></span>
      <span>hypothesis <b class="{cls(hyp_ev)}">{hyp_ev:+.2f}%</b></span>
      <span>shopping <b class="{cls(shop_ev)}">{shop_ev:+.2f}%</b></span>
    </div>
    <div class="nums">
      <div class="nf"><label>line</label>
        <input class="f-line" data-i="{i}" data-f="line" data-orig="{r['line']}" value="{r['line']}"></div>
      <div class="nf"><label>price</label>
        <input class="f-price" data-i="{i}" data-f="price" data-orig="{r['best_price']}" value="{r['best_price']}"></div>
      <div class="nf"><label>book</label>
        <input class="f-book" data-i="{i}" data-f="book" data-orig="{UI.esc(r['best_book'])}" value="{UI.esc(r['best_book'])}"></div>
    </div>
    <div class="hint">These are the captured board's numbers. Change them to what
      your book actually shows — your book is the authority, and the number you
      enter is the one CLV is measured from.</div>
  </div>
</div>"""


def tab_picks(d):
    recs, logged = d["recommendations"], set(d["logged_keys"])
    if not recs:
        return UI.alert(
            "No recommendation this week. That is a valid and frequent output — "
            "a dry week is the system working, not a collection failure. Check "
            "the WEEK tab of the dashboard for whether the board was captured at "
            "all; an empty board and an empty week are different things.",
            "under", "📋")
    body = ""
    for c in d["correlated"]:
        body += UI.alert(
            f"{c['reads']} of these come from {UI.esc(c['game'])}. They are one "
            f"read's worth of evidence, not {c['reads']}, and stacking them on a "
            f"slip multiplies a single outcome rather than diversifying it.",
            "warn", "⚠")
    tiers = {h: v["tier"] for h, v in d["hypotheses"].items()}
    if all(tiers.get(r["hypothesis"]) != "PROVEN" for r in recs):
        body += UI.alert(
            "Every hypothesis behind these is SHADOW, so every entry is logged at "
            "zero units. That is not a limitation to work around — it is the "
            "system refusing to bet an unproven claim. What accumulates now is "
            "CLV and margin vs fair, not money.", "under", "◆")
    for i, r in enumerate(recs):
        key = f"{r['player']}|{r['market']}|{r['side']}|{r['line']}"
        body += leg_card(i, r, key in logged)
    return body


def tab_slips(d):
    if not d["slips"]:
        return UI.alert(
            "No slip this week. parlay.py will not build one out of legs the "
            "props engine did not recommend — with too few qualifying singles, "
            "the correct output is no slip, not a padded one.", "under", "📋")
    out = ""
    for n, s in enumerate(d["slips"]):
        legs = "".join(
            f"<div class='leg-s'>· {UI.esc(l['player'])} {UI.esc(l['market'])} "
            f"{l['side']} {l['line']} @ {l['best_price']:+d} ({UI.esc(l['best_book'])})</div>"
            for l in s["legs"])
        vig = s.get("vig_cost_pct")
        mo = s.get("ev_market_only_pct")
        out += f"""
<div class="leg" style="grid-template-columns:1fr">
  <div>
    <div class="leg-t">{s['n_legs']}-leg · {s.get('combined_price', 0):+d}
      <span class="leg-s">(fair {s.get('fair_price', 0):+d})</span></div>
    {legs}
    <div class="evsplit">
      <span>slip EV <b class="{'pos' if s.get('ev_pct',0)>0 else 'neg'}">{s.get('ev_pct',0):+.2f}%</b></span>
      {f"<span>vig cost <b class='neg'>{vig:.2f}%</b></span>" if vig is not None else ""}
      {f"<span>market-only <b class='{'pos' if mo>0 else 'neg'}'>{mo:+.2f}%</b></span>" if mo is not None else ""}
    </div>
    <div class="hint">Compounded vig: every leg pays the house its cut, so the
      slip is taxed more than its legs are separately. The market-only number is
      what this same slip is worth granting the hypothesis nothing.</div>
    <div style="margin-top:10px">
      <button class="btn" onclick="useSlip({n})">Load these legs into PICKS</button>
    </div>
  </div>
</div>"""
    return out


def tab_tracking(d):
    week_rows = [b for b in d["bets"] if str(b.get("week")) == str(d["week"])]
    if not week_rows:
        return UI.alert(
            "Nothing entered for this week yet. Select on the PICKS tab and press "
            "Enter — the row appears here about a minute later, once the run has "
            "written it and Pages has redeployed.", "under", "📋")
    out = ""
    for b in week_rows:
        pre = bool(b.get("ts_stake"))
        clo = bool(b.get("price_close"))
        grd = bool(b.get("outcome"))
        clv = b.get("clv_cents")
        tone = ("win" if b.get("outcome") == "W" else
                "loss" if b.get("outcome") == "L" else "shadow")
        out += f"""
<div class="pc {tone}">
  <div class="ph">
    <span class="pm">{UI.esc(b['row_id'])} · {UI.esc(b['player'])}
      {UI.esc(b['prop_type'])} {b['side']} {b['line_stake']}</span>
    <span class="pmeta">
      {UI.badge(b.get('hypothesis',''), 'shadow')}
      {UI.badge(b.get('tier_at_stake',''), 'shadow')}
      {UI.badge((b.get('stake_units') or '0') + 'u', 'skip')}
    </span>
  </div>
  <div class="leg-s">entered @ {b['price_stake']} ({UI.esc(b.get('book_stake',''))})
    · close {b.get('price_close') or '—'}
    · CLV {clv if clv else '—'}
    {'· ' + UI.esc(b['outcome']) if grd else ''}</div>
  <div class="trk">
    <div class="{'on' if pre else ''}">pre-game · entered</div>
    <div class="{'on' if clo else 'wait'}">{'close captured' if clo else 'awaiting close'}</div>
    <div class="{'on' if grd else 'wait'}">{'graded' if grd else 'awaiting result'}</div>
  </div>
</div>"""
    open_close = sum(1 for b in week_rows if not b.get("price_close"))
    if open_close:
        out = UI.alert(
            f"{open_close} row(s) still have no closing price. That is the one "
            f"number that cannot be recovered after kickoff — the Sunday capture "
            f"runs at 12:30 ET, and anything entered after the early window "
            f"closes will carry no CLV for the rest of its life.",
            "warn", "⏱") + out
    return out


def build(week):
    d = load(week)
    logged = len(d["logged_keys"])
    live = sum(1 for b in d["bets"] if float(b.get("stake_units") or 0) > 0)
    clvs = [float(b["clv_cents"]) for b in d["bets"] if b.get("clv_cents")]

    head = UI.header(
        f"CONSOLE — {C.LEAGUE.upper()} {C.SEASON} WK {week}",
        d["built"][:16].replace("T", " ") + "Z",
        [("recommendations", str(len(d["recommendations"])), "neu"),
         ("entered this week", str(logged), "neu"),
         ("mean CLV", f"{sum(clvs)/len(clvs):+.2f}" if clvs else "—",
          "pos" if clvs and sum(clvs) > 0 else "neu"),
         ("live rows", str(live), "neu")])

    tokbar = f"""
<div class="tokbar">
  <div class="tokrow">
    <span id="tokdot" class="dot"></span>
    <input id="tokin" type="password" placeholder="GitHub token (ghp_… or github_pat_…)">
    <button id="toksave" class="btn pri">Save</button>
    <button id="tokclear" class="btn">Forget</button>
  </div>
  <div class="hint" id="tokmsg"></div>
  <div class="hint">A fine-grained token on <b>{REPO}</b> only, with
    <b>Actions: read and write</b>. It is stored in this browser and sent only to
    api.github.com. It is never committed to the repo and it never passes through
    Claude. Create one at github.com/settings/personal-access-tokens.</div>
</div>"""

    tabs = UI.tabs([("picks", "PICKS", len(d["recommendations"]) or None),
                    ("slips", "PARLAYS", len(d["slips"]) or None),
                    ("tracking", "TRACKING", logged or None)])
    content = (
        UI.tabcontent("picks", UI.section("This week's recommendations",
                                          tab_picks(d)), active=True)
        + UI.tabcontent("slips", UI.section("Slips parlay.py would build",
                                            tab_slips(d)))
        + UI.tabcontent("tracking", UI.section("Entered — pre, close, result",
                                               tab_tracking(d))))

    tray = """
<div class="tray">
  <span class="tray-c" id="count">nothing selected</span>
  <button class="btn" id="btnAll">Select all</button>
  <button class="btn" id="btnNone">Clear</button>
  <label class="tog"><input type="checkbox" id="asslip" disabled>
    enter as one slip</label>
  <button class="btn pri needsel needtok" id="btnEnter" disabled>Enter selected</button>
</div>
<div class="cwrap"><div class="log" id="log">Select legs above, adjust the line
and price to what your book shows, then press Enter. Nothing is written until
you do, and nothing takes money while every hypothesis is SHADOW.</div></div>"""

    body = (head + tabs + '<div class="cwrap">' + tokbar + "</div>"
            + content + tray)
    doc = UI.document(f"Console — {C.LEAGUE.upper()} wk {week}",
                      f"Console wk {week}", body)
    doc = doc.replace("</style>", EXTRA_CSS + "</style>")
    doc = doc.replace("</body>", (
        "<script>window.__DATA__=" + json.dumps(d).replace("</", "<\\/")
        + ";</script><script>" + APP_JS + "</script></body>"))

    out = C.ROOT / "dashboards" / C.LEAGUE / "console.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(doc)
    print(f"built {out.relative_to(C.ROOT)}  ({len(doc):,} bytes)")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--week", type=int)
    a = ap.parse_args()
    build(a.week or C.default_week())


if __name__ == "__main__":
    main()
