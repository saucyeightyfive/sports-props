#!/usr/bin/env python3
"""Export the registry and rules as markdown.

The HTML rendering lives in report.py — the dashboard's HYPOTHESES and
METHODOLOGY tabs ARE the registry view, and there is no second page. This
script exists only for when you want the registry as plain text: to paste
somewhere, to diff, or to read without opening a browser.

hypotheses.yaml and rules.yaml are the system's source of truth, and YAML is a
poor format to review judgment in — the parts that matter (what fires it, what
kills it, which condition the edge is claimed on) are buried in indentation.
This renders both in full, using the same components as the dashboard, so
ratifying a change does not require reading a config file.

  python scripts/review.py                      # -> dashboards/<league>/registry.md
  python scripts/review.py --since 2026-09-19   # flag what changed on or after

Nothing here writes to state/. It is a viewer.
"""
import argparse, sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import config as C
from report import read_yaml, _list, _clean, touched

OUT = C.DASHBOARDS


def build_md(hyp, rules, since):
    L = []
    meta = hyp.get("meta") or {}
    L.append(f"# Registry review — {C.SEASON}\n")
    L.append(f"*Framework status: **{meta.get('framework_status','—')}**. "
             f"Everything below is proposed until ratified.*\n")
    if meta.get("revision_note"):
        L.append(f"> {_clean(meta['revision_note'])}\n")

    L.append("\n## Open hypotheses\n")
    for h in _list(hyp.get("hypotheses")):
        flag = " — **revised**" if since and touched(h, since) else ""
        L.append(f"\n### {h.get('id')} — {h.get('name')}{flag}\n")
        L.append(f"`{h.get('tier','SHADOW')}` · opens week "
                 f"{h.get('earliest_fire_week','?')} · gate "
                 f"{(h.get('record') or {}).get('rows',0)}/{h.get('min_n','?')}"
                 + (f" · conjunction, edge claimed on **{h['edge_claimed_on']}**"
                    if h.get("edge_claimed_on") else "") + "\n")
        L.append(f"\n**Mechanism.** {_clean(h.get('mechanism'))}\n")
        trig = _list(h.get("trigger"))
        if trig:
            L.append("\n**Fires when — all of:**\n")
            for t in trig:
                L.append(f"- {_clean(t)}")
            L.append("")
        if h.get("conditions_named"):
            L.append("\n**Conditions required (G3a):**\n")
            for k, v in h["conditions_named"].items():
                L.append(f"- *{k}* — {_clean(v)}")
            L.append("")
        for a in _list(h.get("axes")):
            L.append(f"\n**Axis `{a.get('name')}`** — {_clean(a.get('pair'))}  \n"
                     f"{_clean(a.get('claim'))}\n")
        L.append(f"\n**Expression.** {_clean(h.get('expression'))}\n")
        if h.get("conjunction_note"):
            L.append(f"\n**Why flagged this way.** {_clean(h['conjunction_note'])}\n")
        L.append(f"\n**Dies if.** {_clean(h.get('disproof'))}\n")
        if h.get("min_n_note"):
            L.append(f"\n*{_clean(h['min_n_note'])}*\n")
        for n in _list(h.get("notes")):
            L.append(f"\n> ⚠ {_clean(n)}\n")

    cands = _list(hyp.get("candidates"))
    if cands:
        L.append("\n## Candidates — written down, not opened\n")
        for c in cands:
            L.append(f"\n### {c.get('id')} — {c.get('name')}\n")
            L.append(f"**Mechanism.** {_clean(c.get('mechanism'))}\n")
            L.append(f"\n**Why it stays closed.** {_clean(c.get('why_not_opened'))}\n")
            L.append(f"\n**Revisit.** {_clean(c.get('revisit'))}\n")

    L.append("\n## Rules\n")
    for r in _list(rules.get("rules")):
        L.append(f"\n**{r.get('id')} — {r.get('name')}.** {_clean(r.get('text'))}")
        if r.get("origin"):
            L.append(f"  \n*Origin: {_clean(r['origin'])}*")
    L.append("\n\n## Amendment log\n")
    amends = _list(rules.get("amendments"))
    if not amends:
        L.append("\n*No amendments.*\n")
    for a in amends:
        st = (a.get("status") or "RATIFIED").upper()
        L.append(f"\n### {a.get('rule')} · {a.get('date')} · **{st}**\n")
        L.append(f"{_clean(a.get('change'))}\n")
        if a.get("origin"):
            L.append(f"\n*Origin: {_clean(a['origin'])}*\n")
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default=None,
                    help="date string to flag as revised, e.g. 2026-09-19")
    a = ap.parse_args()

    hyp = read_yaml(C.HYPOTHESES)
    rules = read_yaml(C.RULES)
    OUT.mkdir(exist_ok=True)

    path = OUT / "registry.md"
    path.write_text(build_md(hyp, rules, a.since))
    print(f"built {path.relative_to(C.ROOT)}  ({path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
