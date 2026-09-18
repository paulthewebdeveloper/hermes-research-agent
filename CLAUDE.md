# CLAUDE.md

Claude Code reads this file at the start of every session in this folder.

**The rules for this wiki are in [AGENTS.md](AGENTS.md). Read it now and follow it.**
Hermes reads the same file, so both agents work from one set of rules and one
set of pages. That is the shared brain: not a plugin, a folder both agents read.

Before answering anything about the business, read in this order:

1. `grep "^## \[" wiki/log.md | tail -5`
2. `wiki/hot.md`
3. `wiki/index.md`, then the page it points to

When something is decided or changes, write it to the page that owns it and add
one line to `wiki/log.md`. The next session, in either agent, starts from there.
