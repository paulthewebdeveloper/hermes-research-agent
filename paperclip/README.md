# Five settings for a Paperclip agent company

I ran my YouTube channel out of a Paperclip company — seven agents on a board, each with a job — and
the first version underperformed badly. Every reason was a setting I chose, or a default I left
alone. This folder is the five settings I would set from the start, in the order I read them out in
the video, with the config files to copy.

Nothing here is Paperclip's fault, and nothing here is Hermes's fault. Four of the five are my own
configuration. The fifth is Google's security rule, and it has a way round it.

## 1. Pick the execution engine on purpose

A Claude Code agent in Paperclip runs on one of two engines, and **the default is ACP**. On ACP, in my
setup, the agents could not see **my skills, my plugins or my browser** — they got Paperclip's own
skills only. Two access checks failed on it, and the same two passed the moment I switched. One line:

```json
"adapterConfig": { "engine": "cli", "chrome": true }
```

ACP is not the wrong choice — it has the richer live view, and the shell and the Claude connectors
worked fine on it. It is the wrong choice *for an agent that needs your own tooling*. The lesson is
**change the default**, not avoid the engine.

→ [`claude-local.json`](claude-local.json) · [`codex-local.json`](codex-local.json) (Codex has the
same trap: unset means ACP, which keeps its own sandbox and stages skills ephemerally)

## 2. Turn memory on, then prove it stored something

Every one of my agent profiles had `memory_enabled: false`. Nothing was ever learned, by any of them,
for weeks. The flag is not the test — I had a session save a code word and a **fresh** session recall
it with no tools before I believed it.

```yaml
memory:
  memory_enabled: true
  user_profile_enabled: true
compression:
  enabled: true
```

→ [`researcher-profile.yaml`](researcher-profile.yaml)

## 3. One engine, one install, one agent at a time

I had five agents on one local install writing to the same session store. The result: over a thousand
`FATAL: session storage stopped writing` errors in a single day, and four profiles with **zero** saved
sessions. They were never storing anything.

If you must share one install: quit the app, stop the gateway, check nothing is holding the store,
restart — and then **watch the error log**. The real lesson is the general one: *check the log exists
before you trust the thing writing to it.* Mine had been shouting for days.

## 4. Only the toolsets an agent's job needs

Every toolset was on, on every agent. So the agent whose job was making images drove my actual screen
with computer use instead of calling the image tool. An agent with every tool does not pick the best
one, it picks the first one.

Give each agent the list its job needs and nothing else, plus a brief you would accept yourself — the
skill it reads, where it stops, where it writes the lesson down. Five-line briefs were the other half
of this problem.

```yaml
platform_toolsets:
  cli: [web, browser, file, terminal, memory, session_search, skills, delegation, todo, vision]
```

Two sandbox notes, both from reading the docs rather than from an incident:

- **Codex** ran with `sandbox_mode = "danger-full-access"` globally on my machine, which every agent
  run inherited. The per-agent fix is in `extraArgs`, not a Codex profile, because Paperclip manages
  `CODEX_HOME` for you. See [`codex-local.json`](codex-local.json).
- **Never point a Hermes profile's `skills.external_dirs` at your Claude skills folder.** External
  skill directories are not write-protected, so an agent can rewrite the method it was told to follow.

→ [`hermes-local.json`](hermes-local.json) · [`researcher-profile.yaml`](researcher-profile.yaml)

## 5. Give any agent that needs a logged-in page its own browser

**Chrome 136+ ignores the remote debugging port on your default profile.** That is Google's security
change, it is a good one, and it is not something to work around — it is something to respect by
giving the agent a browser of its own: separate profile folder, own debug port, bound to localhost,
started at login by one launch agent, and **nothing in it but the page the agent reads**.

```yaml
browser:
  cdp_url: http://127.0.0.1:9223
  use_real_profile: false
```

Mine is logged into my own account, which is my choice and my risk: the brief keeps that agent
read-only on the two pages it needs. Copying your real profile while Chrome is open fails on macOS,
and the community Chrome extensions only bind to long-running API sessions, never to the one-shot runs
a board actually starts. One of them self-updates from git and runs JavaScript in any tab; I would not
install it.

→ [`chrome-agent.plist`](chrome-agent.plist)

## Then route the engines by what each is good at

Five agents on Claude Code, the lane that loads my skill library. The thumbnail agent on Codex,
because its image tool gives me back something that actually looks like me. And **Hermes down from
five agents to one** researcher, because memory is the thing it does better than the others.

Scheduled work goes in a routine, not in an agent's own cron: every run becomes an issue with a brief
and an audit trail. → [`routine-daily-metrics.md`](routine-daily-metrics.md)

## The loop that makes it worth running

Every creative agent stops at the decision that matters — before it generates, after the edit plan,
after the shortlist. I get a card, I pick, and **the agent writes my pick into a skill file**, in git,
with a commit message. Not into a model's memory where I cannot see it: into a diff I can revert.

The briefs are in [`instructions/`](instructions/) — a generic
[`AGENTS.md`](instructions/AGENTS.md) with the house rules and the learning loop, and a CEO
[`HEARTBEAT.md`](instructions/HEARTBEAT.md) for the wake that has no issue attached.

**The agents follow my own skills**, which stay in my own repo and are not published here. What is
published is the shape: the brief says *which* skill to read and where the lesson gets written, and
the method lives in the skill so it can be edited after a mistake.

## One ordering rule that is not a setting

**Thumbnails are made after the recording, not before.** The image has to come off the real footage —
the actual expression, what was really on screen, the real number. Before the shoot the thumbnail
exists only as one line of text saying what the image must show, written beside the title, because the
title and the tile are one piece of writing. An agent briefed to design the tile first will produce
something the video then has to live up to.

## What it cost

Three agent runs behind one video: about fifteen minutes of agent time and six million cached tokens.
A few dollars at list price, none of it paid — it was inside a subscription I already had. The real
cost was the day I lost to a browser port.
