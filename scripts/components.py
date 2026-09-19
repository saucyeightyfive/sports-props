"""HTML component builders for the dashboard.

Ports the terminal-analytics design system (dark surface, IBM Plex, amber
accent) from the predecessor project. Every helper returns an HTML string and
closes its own tags, so the structural validator stays green.
"""
import html
from pathlib import Path

THEME = Path(__file__).resolve().parent.parent / "web" / "theme.css"

TAB_JS = """
function showTab(name, btn){
  document.querySelectorAll('.tc').forEach(t=>t.classList.remove('active'));
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  document.getElementById('tab-'+name).classList.add('active');
  btn.classList.add('active');
}
"""

# Semantic badge vocabulary -> CSS class from the ported theme.
BADGE = {
    "confirmed": "bcw", "confirming": "bcw", "win": "bwi", "loss": "blo",
    "gambled": "bgw", "teaching": "btls", "frontier": "bfl",
    "shadow": "bsr", "unproven": "bsu", "contested": "bsc", "proven": "bsh2",
    "retired": "bsk", "skip": "bsk", "new": "bnw", "pending": "bpu",
    "live": "bgold", "flag": "bly", "danger": "bvu", "info": "bc2",
    "note": "btl", "alert": "bdr",
}


def esc(s):
    return html.escape(str(s if s is not None else ""))


def badge(text, kind="info"):
    return f'<span class="badge {BADGE.get(kind, "bc2")}">{esc(text)}</span>'


def alert(text, kind="warn", icon="📋"):
    cls = {"warn": "warn", "res": "res", "under": "under", "act": "act"}.get(kind, "warn")
    return (f'<div class="al {cls}"><div class="al-ic">{icon}</div>'
            f'<div class="al-tx">{text}</div></div>')


def insight(label, body, tone="b"):
    """Callout box. tone: b(lue) r(ed) g(reen) tl(teal) plain."""
    return (f'<div class="ins"><span class="ins-tag {tone}">{esc(label)}</span>'
            f'<p>{body}</p></div>')


def section(title, *blocks):
    return (f'<div class="sec"><div class="sec-t">// {esc(title)}</div>'
            f'{"".join(blocks)}</div>')


def table(headers, rows, foot=None):
    """rows: list of lists of pre-rendered HTML cells."""
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    if not rows:
        body = (f'<tr><td colspan="{len(headers)}" class="mono" '
                f'style="color:var(--muted);padding:16px 9px">— no rows yet —</td></tr>')
    else:
        body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
                       for r in rows)
    tf = ""
    if foot:
        tf = ('<tr class="f5tot">' +
              "".join(f"<td>{c}</td>" for c in foot) + "</tr>")
    return (f'<table class="tbl"><thead><tr>{th}</tr></thead>'
            f'<tbody>{body}{tf}</tbody></table>')


def statcards(cards):
    """cards: list of (label, value, sublabel, tone)."""
    out = []
    for label, value, sub, tone in cards:
        out.append(f'<div class="sc"><div class="sc-l">{esc(label)}</div>'
                   f'<div class="sc-v {tone}">{esc(value)}</div>'
                   f'<div class="sc-s">{esc(sub)}</div></div>')
    return f'<div class="scards">{"".join(out)}</div>'


def panel(title, meta_badges, body, tone="under"):
    """The bordered highlight card used for a featured read."""
    meta = "".join(meta_badges)
    return (f'<div class="pc {tone}"><div class="ph">'
            f'<span class="pm">{esc(title)}</span>'
            f'<div class="pmeta">{meta}</div></div>'
            f'<div class="pb">{body}</div></div>')


def rulecard(rid, desc, tone="new"):
    return (f'<div class="rb {tone}"><div class="rid {tone}">{esc(rid)}</div>'
            f'<div class="rdesc">{desc}</div></div>')


def header(title, version, stats, control=None):
    """stats: list of (label, value, tone). control: optional HTML on the left,
    used by the live console for the week picker."""
    hs = "".join(f'<div class="hs"><div class="hs-l">{esc(l)}</div>'
                 f'<div class="hs-v {t}">{esc(v)}</div></div>'
                 for l, v, t in stats)
    return (f'<div class="header"><div style="display:flex;align-items:baseline;gap:10px">'
            f'<span class="htitle">{esc(title)}</span>'
            f'<span class="hver">{esc(version)}</span>'
            f'{control or ""}</div>'
            f'<div class="hstats">{hs}</div></div>')


def weekpicker(week, weeks, logged=()):
    """GET form in the header. Weeks with rows already logged are marked, so
    the empty week you are about to work on is visibly different from the ones
    behind you."""
    opts = []
    for w in weeks:
        mark = " ·" if w in logged else ""
        sel = " selected" if int(w) == int(week) else ""
        opts.append(f'<option value="{w}"{sel}>WEEK {w}{mark}</option>')
    return ('<form method="get" action="/" class="wkpick">'
            '<select class="inp wk" name="week" onchange="this.form.submit()" '
            f'aria-label="week">{"".join(opts)}</select></form>')


def tabs(items):
    """items: list of (key, label, note_html_or_None). First is active."""
    out = []
    for i, (key, label, note) in enumerate(items):
        active = " active" if i == 0 else ""
        nb = f'<span class="nb g">{esc(note)}</span>' if note else ""
        out.append(f'<button class="tab{active}" '
                   f'onclick="showTab(\'{key}\',this)">{esc(label)}{nb}</button>')
    return f'<div class="tabs">{"".join(out)}</div>'


def tabcontent(key, inner, active=False):
    cls = "tc active" if active else "tc"
    return f'<div id="tab-{key}" class="{cls}">{inner}</div>'


def document(title, head_title, body):
    css = THEME.read_text() if THEME.exists() else ""
    return (f'<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="UTF-8">\n'
            f'<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
            f'<title>{esc(head_title)}</title>\n<style>\n{css}\n</style>\n</head>\n'
            f'<body>\n{body}\n<script>{TAB_JS}</script>\n</body>\n</html>\n')


# --- form builders ---------------------------------------------------------
# The live console needs write controls. They live here for the same reason
# every other element does: so the HTML has one owner and the validator can
# reason about it.

def field(label, name, value="", kind="text", placeholder="", required=False):
    req = " required" if required else ""
    ph = f' placeholder="{esc(placeholder)}"' if placeholder else ""
    return (f'<label class="fld"><span class="fld-l">{esc(label)}</span>'
            f'<input class="inp" type="{kind}" name="{esc(name)}" '
            f'id="f-{esc(name)}" value="{esc(value)}"{ph}{req}></label>')


def textarea(label, name, value="", placeholder="", required=False):
    req = " required" if required else ""
    ph = f' placeholder="{esc(placeholder)}"' if placeholder else ""
    return (f'<label class="fld"><span class="fld-l">{esc(label)}</span>'
            f'<textarea class="inp" name="{esc(name)}" id="f-{esc(name)}"'
            f'{ph}{req}>{esc(value)}</textarea></label>')


def select(label, name, options, value="", auto=False):
    """options: list of (value, label) or plain strings."""
    opts = []
    for o in options:
        v, t = o if isinstance(o, tuple) else (o, o)
        sel = " selected" if str(v) == str(value) else ""
        opts.append(f'<option value="{esc(v)}"{sel}>{esc(t)}</option>')
    js = ' onchange="this.form.submit()"' if auto else ""
    return (f'<label class="fld"><span class="fld-l">{esc(label)}</span>'
            f'<select class="inp" name="{esc(name)}" id="f-{esc(name)}"{js}>'
            f'{"".join(opts)}</select></label>')


def hidden(name, value):
    return f'<input type="hidden" name="{esc(name)}" value="{esc(value)}">'


def button(text, primary=True):
    return f'<button class="btn{" go" if primary else ""}">{esc(text)}</button>'


def form(action, *blocks, title=None, inline=False):
    t = f'<div class="frm-t">{esc(title)}</div>' if title else ""
    wrap = "irow" if inline else "fgrid"
    inner = "".join(blocks)
    body = (f'<form method="post" action="{esc(action)}">'
            f'<div class="{wrap}">{inner}</div></form>')
    return body if inline else f'<div class="frm">{t}{body}</div>'


def flash(kind, message):
    return f'<div class="flash {esc(kind)}">{esc(message)}</div>'


def gatebar(n, target):
    pct = min(100, round(100 * n / target)) if target else 0
    return (f'<span class="mono">{n} / {target}</span>'
            f'<div class="gatebar"><span style="width:{pct}%"></span></div>')


def ticketlink(slip_id):
    return f'<a class="tklink" href="/slip/{esc(slip_id)}">open ticket →</a>'
