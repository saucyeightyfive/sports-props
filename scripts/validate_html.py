#!/usr/bin/env python3
"""Structural validation for generated dashboards.

Three checks, carried over from the predecessor project — a dashboard that fails
any of them is not shipped:
  1. tag balance (0 unclosed, 0 parser errors)
  2. every tab button has a matching tab-content div, and vice versa
  3. every jumplink target resolves to a real anchor
Plus: no badge class used that the theme doesn't define.

  python scripts/validate_html.py dashboards/nfl_2026_wk01.html
"""
import re, sys
from html.parser import HTMLParser
from pathlib import Path

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}


class Balance(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.errors = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack:
            self.errors.append(f"close <{tag}> with empty stack")
            return
        if self.stack[-1] == tag:
            self.stack.pop()
        elif tag in self.stack:
            while self.stack and self.stack[-1] != tag:
                self.errors.append(f"implicit close <{self.stack.pop()}> (wanted {tag})")
            if self.stack:
                self.stack.pop()
        else:
            self.errors.append(f"stray close <{tag}>")


def validate(path):
    doc = Path(path).read_text(encoding="utf-8")
    ok = True

    p = Balance(); p.feed(doc)
    c1 = not p.stack and not p.errors
    print(f"CHECK 1 tag balance      : {'PASS' if c1 else 'FAIL'}")
    if not c1:
        print(f"  unclosed: {p.stack[-6:]}")
        print(f"  errors  : {p.errors[:6]}")
    ok &= c1

    btns = set(re.findall(r"showTab\('([a-z]+)'", doc))
    divs = set(re.findall(r'id="tab-([a-z]+)"', doc))
    c2 = btns == divs and bool(btns)
    print(f"CHECK 2 tabs <-> content : {'PASS' if c2 else 'FAIL'}")
    if not c2:
        print(f"  button-only: {btns - divs}   div-only: {divs - btns}")
    ok &= c2

    targets = set(re.findall(r"getElementById\('(sec-[a-z0-9\-]+)'\)", doc))
    anchors = set(re.findall(r'id="(sec-[a-z0-9\-]+)"', doc))
    c3 = targets.issubset(anchors)
    print(f"CHECK 3 jumplinks        : {'PASS' if c3 else 'FAIL'}"
          f"{'  (none used)' if not targets else ''}")
    if not c3:
        print(f"  unresolved: {targets - anchors}")
    ok &= c3

    used = set(re.findall(r'class="badge (b[a-z0-9]+)"', doc))
    defined = set(re.findall(r'\.(b[a-z0-9]+)\s*\{', doc))
    missing = used - defined
    c4 = not missing
    print(f"CHECK 4 badge classes    : {'PASS' if c4 else 'FAIL'}")
    if missing:
        print(f"  undefined: {sorted(missing)}")
    ok &= c4

    print("=" * 42)
    print(f"{'ALL CHECKS PASS' if ok else 'VALIDATION FAILED'}")
    return ok


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: validate_html.py <file.html>")
    sys.exit(0 if validate(sys.argv[1]) else 1)
