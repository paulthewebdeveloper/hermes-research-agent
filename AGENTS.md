# AGENTS.md: the schema

The agent reads this file before anything else. It says where things live, how
to find an answer, and what the agent may change on its own. Edit it to fit
your business; keep it short.

The pattern is Andrej Karpathy's LLM wiki:
https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f

## Layout

```
raw/      sources: transcripts, exports, PDFs, client messages.
          Never edit a file that is already here. Add, never alter.
wiki/     the pages. One page per thing that exists in your business.
  index.md  the catalog, one line per page
  log.md    what happened, append-only
  hot.md    standing warnings: broken, blocked, off-limits
  pages/    everything else
tools/    farm.py, lint.py, hooks/
hermes/   worker profiles (persona + toolset) for Hermes
watchdog/ cerberus.sh, the no-AI health check
```

## Rules

- **One fact, one page.** Every other page links to it with `[[page-name]]`.
  A copied number goes stale the moment the original changes.
- Every page starts with frontmatter holding a one-line `description:`.
- Unknowns are written `**[TODO: what is missing]**`. Never invent a fact.
- Open items are `- [ ] Thing — **due: 2026-09-21**`. A trigger is fine too:
  `due: on their reply`. No `due:` means it does not exist.

## Answering a question: read in this order

1. The log tail: `grep "^## \[" wiki/log.md | tail -5`
2. `wiki/hot.md`
3. `wiki/index.md`, to find the page
4. The page itself

If the answer is not in the wiki, say so. Do not answer from memory.

## Writing

- A new fact goes on the page that owns it, plus one log line:
  `## [YYYY-MM-DD] ingest|query|lint|work | Title`
- Run `python3 tools/lint.py` before committing. The pre-commit hook blocks a
  broken wiki anyway.
- **Small edits alone** (a log line, a fact, a ticked box). Anything structural
  (new sections, deleting or renaming pages, changing these rules): leave a
  note on the page and let the human decide.

## How the human leaves instructions

`%% note: this page is out of date, the price changed %%`, anywhere on a page.
Obsidian hides it in reading view. Do what it asks, delete the note, log it.

## Rules page (write your own)

Add `wiki/pages/rules.md`: how you want to be worked with, in a few sentences.
Include the two or three mistakes you keep making, so the agent can call them
out when it sees them in the log.
