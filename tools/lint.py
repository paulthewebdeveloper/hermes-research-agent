#!/usr/bin/env python3
"""Lint the wiki. Blocks the commit (exit 1) when the wiki is structurally broken.

Four rules, on purpose. Add a rule when the agent actually breaks something,
not before.

  1. every wiki page has a `description:` in its frontmatter
  2. every open item `- [ ]` carries a `due:` (a date or a trigger)
  3. every [[wikilink]] resolves to a page in wiki/ or a file in raw/
  4. every log heading is `## [YYYY-MM-DD] <op> | Title` so `grep | tail` works

    python3 tools/lint.py
"""

import pathlib
import re
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
WIKI = REPO / "wiki"
RAW = REPO / "raw"


def check():
    pages = sorted(WIKI.rglob("*.md"))
    names = {p.stem for p in pages} | {p.name for p in RAW.rglob("*") if p.is_file()}
    errors = []

    for page in pages:
        rel = page.relative_to(REPO)
        text = page.read_text(errors="replace")
        # ponytail: strips fenced code naively, fine until a page nests fences
        prose = re.sub(r"```.*?```", "", text, flags=re.S)

        front = re.match(r"^---\n(.*?)\n---\n", text, re.S)
        if not front or not re.search(r"^description:\s*\S", front.group(1), re.M):
            errors.append(f"{rel}: no description in frontmatter")

        for line in prose.splitlines():
            if line.lstrip().startswith("- [ ]") and "due:" not in line:
                errors.append(f"{rel}: open item has no due: {line.strip()[:70]}")

        for link in re.findall(r"\[\[([^\]|#]+)", prose):
            if link.strip() not in names:
                errors.append(f"{rel}: dead link [[{link.strip()}]]")

        if page.name == "log.md":
            for h in re.findall(r"^## .*$", prose, re.M):
                if not re.match(r"^## \[\d{4}-\d\d-\d\d\] (ingest|query|lint|work) \| \S", h):
                    errors.append(f"{rel}: log heading off-format: {h[:70]}")
    return errors


if __name__ == "__main__":
    errors = check()
    for e in errors:
        print(e)
    print(f"{len(errors)} error(s)")
    sys.exit(1 if errors else 0)
