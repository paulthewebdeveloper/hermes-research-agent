# Hermes Research Agent

An AI agent that knows your business and does your research for you. Give it a
YouTube link, and a worker agent pulls the transcript, **watches the frames for
what's on screen**, files it into your knowledge base, and builds a NotebookLM
notebook you can chat with.

This is the setup from the video
**[I Stopped Watching YouTube. Now YouTubers Answer My Questions.](https://youtu.be/frDNPtWofIM)**
Setup takes about 30 minutes.

```
 you ──► Hermes (main agent) ──hands off──► Argus (worker)
              │                               │  farm.py: transcript → raw/
              │ reads before answering        │  hermes-video-watch: frames → "seen, not heard"
              ▼                               ▼
         wiki/ (LLM wiki)              NotebookLM notebook ◄── you chat with the video
              ▲
 cerberus.sh (no AI) checks every hour that the server, site and wiki sync are healthy
```

## What you get

| Part | What it does | File |
|---|---|---|
| **Wiki memory** | The agent's knowledge is a folder of markdown pages, one per thing in your business, so it reads a page instead of "remembering" | `AGENTS.md`, `wiki/`, `raw/` |
| **Lint gate** | A pre-commit hook that blocks the agent from committing a broken wiki | `tools/lint.py`, `tools/hooks/pre-commit` |
| **Argus, the worker** | One job: turn a video into a source file, including what was on screen, then push it to NotebookLM | `hermes/argus/`, `tools/farm.py`, `hermes/skills/hermes-video-watch/` |
| **Cerberus, the watchdog** | A plain shell script, no model, that messages you once when something breaks | `watchdog/cerberus.sh` |

Everything is text files in git. No vector database, no subscription beyond the
model you already use.

## Before you start

- [Hermes Agent](https://github.com/NousResearch/hermes-agent) installed and connected to a model
- Python 3.10+, `git`, `ffmpeg`
- `yt-dlp` (`brew install yt-dlp`, `pipx install yt-dlp`, or `uv`)
- A Google account for NotebookLM
- Optional: [Obsidian](https://obsidian.md) to browse the wiki as a graph

**Run Argus on your own computer, not a cloud server.** YouTube blocks most
datacenter IPs ("Sign in to confirm you're not a bot"). A server is fine for
the main agent and the watchdog.

## Setup

### 1. Install Hermes

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
hermes setup
```

### 2. Clone this repo as your wiki

```bash
git clone https://github.com/paulthewebdeveloper/hermes-research-agent.git ~/hermes-research-agent
cd ~/hermes-research-agent
git config core.hooksPath tools/hooks     # turns on the lint gate
python3 tools/lint.py                     # should print: 0 error(s)
```

Point Hermes at this folder as its working directory (in `~/.hermes/config.yaml`,
the terminal `cwd`), so it reads `AGENTS.md` on every session.

### 3. Make the wiki yours

Open `AGENTS.md` and read it; it's the rules the agent follows. Then:

1. Write down the ten nouns your business runs on (clients, projects, suppliers,
   courses, whatever). Those are your first ten pages in `wiki/pages/`.
2. Delete `wiki/pages/example-client.md`.
3. Add a `wiki/pages/rules.md`: how you want to be worked with, plus the two or
   three mistakes you keep making. The agent will call them out.

The pattern comes from Andrej Karpathy's
[LLM wiki](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f).
It's worth reading once.

### 4. Install the video skill

```bash
mkdir -p ~/.hermes/skills/media
ln -s ~/hermes-research-agent/hermes/skills/hermes-video-watch ~/.hermes/skills/media/hermes-video-watch
python3 ~/.hermes/skills/media/hermes-video-watch/scripts/hermes_video_watch.py --help
```

### 5. Install the NotebookLM CLI

Uses [notebooklm-mcp-cli](https://github.com/jacob-bd/gemini-notebook-mcp-cli) (MIT).

```bash
uv tool install notebooklm-mcp-cli
nlm login                      # opens a browser, sign in with your Google account
nlm notebook list              # proves it works
```

### 6. Create Argus, the worker

```bash
hermes profile create argus --clone \
  --description "$(sed -n '/^description:/,/^description_auto/p' hermes/argus/profile.yaml | sed '1s/^description: //;$d' | tr '\n' ' ')"

cp hermes/argus/SOUL.md ~/.hermes/profiles/argus/SOUL.md
sed -i.bak "s#<REPO>#$HOME/hermes-research-agent#" ~/.hermes/profiles/argus/SOUL.md
```

Then cut its tools down to the list in `hermes/argus/toolsets.txt`
(web, terminal, file, video, vision, skills, memory):

```bash
HERMES_HOME=~/.hermes/profiles/argus hermes tools list
HERMES_HOME=~/.hermes/profiles/argus hermes tools disable <each tool not in toolsets.txt>
```

**Do this step.** `--clone` copies everything from your main profile:

- every tool (browser, sub-agents, cron, computer use)
- your chat-platform tokens in `.env`
- your main persona

A worker with every tool is a liability. Also open
`~/.hermes/profiles/argus/config.yaml` and `.env`: turn off any messaging
platforms (Telegram and so on) and remove their tokens. A worker never talks
to you directly.

### 7. Try it

Talk to your main Hermes agent:

> Create a NotebookLM notebook about this video: https://www.youtube.com/watch?v=... Use Argus for it.

Hermes hands the job to Argus. Argus writes a file in `raw/data/` with the
transcript plus what it saw on screen, then gives you a notebook link. Open it
and ask the video questions, or generate an audio overview.

You can also run the worker directly:

```bash
hermes -p argus chat --oneshot -q "farm https://www.youtube.com/watch?v=..."
```

More prompts are in `examples/prompts.md`.

### 8. Optional: the watchdog

For a server running Hermes around the clock. Edit the settings at the top of
`watchdog/cerberus.sh` (your site URL, where alerts go), then:

```bash
crontab -e
# 17 * * * * $HOME/hermes-research-agent/watchdog/cerberus.sh --quick
# 30 8 * * * $HOME/hermes-research-agent/watchdog/cerberus.sh
```

It stays silent while everything passes and sends one message per failure,
through `hermes send`. It uses no AI on purpose: a shell script can't
hallucinate a 200. Written for Linux.

## How the pieces behave

- **The agent reads before it answers.** Log tail, then `hot.md`, then the
  index, then the page. It's slower than a chatbot, and right.
- **`raw/` is immutable.** `farm.py` refuses to overwrite a file, and Argus never
  edits one.
- **Argus marks what it saw on screen as *seen, not heard*.** NotebookLM only
  reads transcripts, so Argus's file is a better source than the bare YouTube link.
- **Unknowns stay unknown.** `**[TODO: ...]**` is correct. An invented answer is not.

## Adapt it

The shape stays the same for any business. The inputs change:

- **Worker input:** meeting recordings, client emails, supplier PDFs. One input,
  one file in `raw/`, honest about what it couldn't read.
- **Notebooks:** one per business area.
- **Watchdog:** start with the one URL that makes you money, and add checks
  when something actually breaks.

Build a new worker only after you've done the job by hand three times.

## Credits

- LLM wiki pattern: [Andrej Karpathy](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f)
- [Hermes Agent](https://github.com/NousResearch/hermes-agent) by Nous Research
- `hermes-video-watch` (MIT, included), inspired by [bradautomates/claude-video](https://github.com/bradautomates/claude-video)
- [notebooklm-mcp-cli](https://github.com/jacob-bd/gemini-notebook-mcp-cli) by jacob-bd (MIT)

I set up agent systems like this for businesses: [maketheclick.com](https://maketheclick.com)

MIT licensed.
