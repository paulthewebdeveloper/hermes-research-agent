# Let your AI set this up

Paste the prompt below into **Claude Code** (or Codex, Gemini CLI, any coding
agent with a terminal) on your own computer. It clones this repo, asks you a
few questions, and builds your shared brain. Read what it proposes before you
approve commands.

```
Set up a shared brain for my AI tools using this repo:
https://github.com/paulthewebdeveloper/hermes-research-agent

Do this step by step and stop to ask me whenever you need a decision.

1. Clone the repo to ~/shared-brain (ask me if I want another folder). Read
   README.md, AGENTS.md and CLAUDE.md fully before doing anything else.
2. Turn on the lint gate: git config core.hooksPath tools/hooks, then run
   python3 tools/lint.py and show me the result.
3. Interview me. Ask, one question at a time: what my business or work is, the
   ten nouns it runs on (clients, projects, products, suppliers...), how I like
   to be worked with, and the two or three mistakes I keep making.
4. From my answers, create one page per noun in wiki/pages/, write
   wiki/pages/rules.md, update wiki/index.md, delete the example page, and add
   a first entry to wiki/log.md. Never invent a fact: anything I did not tell
   you is written as **[TODO: what is missing]**.
5. Make it my own repo: remove the git remote, and offer to create a PRIVATE
   GitHub repo for it with the gh CLI. My wiki must never be pushed to a public
   repo.
6. If Hermes Agent is installed (check with: hermes --version), point its
   working directory at this folder so it reads AGENTS.md, and show me the
   change before you make it. If it is not installed, give me the install
   command from the README and continue without it.
7. Optional, ask first: set up Mem0 as Hermes's memory plugin (hermes memory
   setup, choose mem0; it needs a free API key from app.mem0.ai that I will
   paste myself). Never print or store my key anywhere except ~/.hermes/.env.
8. Optional, ask first: schedule the example daily report from
   examples/daily-report.md with hermes cron.
9. Finish by proving it works: open a fresh session and answer one question
   about my business using only the wiki, quoting the page you read.
```

## What you end up with

| Layer | What it holds | Who reads it |
|---|---|---|
| **The wiki** (this folder) | Everything true about your business, one page per thing | Claude Code **and** Hermes |
| **Mem0** (optional) | Facts you mention in passing, saved automatically | Hermes |
| **Hermes built-in memory** | How you like to work, two small files | Hermes |

Only the wiki is shared. If you set up one thing, set up the wiki.
