# Example: a daily report, built once and run for free

The pattern from the video: **Claude Code builds the job once, Hermes runs it
every day.** The job is a plain script, so the daily run uses no AI model and
costs nothing. Spend tokens on building and thinking, not on reading a number.

## 1. The script

`tools/youtube-report.py` prints your last ten videos with views since
yesterday and any comment threads you have not replied to.

```bash
brew install yt-dlp        # or: pipx install yt-dlp
python3 tools/youtube-report.py @yourhandle
```

## 2. Hand it to Hermes

Hermes runs scripts from `~/.hermes/scripts/`:

```bash
mkdir -p ~/.hermes/scripts
cat > ~/.hermes/scripts/youtube-report.sh <<'SH'
#!/usr/bin/env bash
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"
python3 "$HOME/shared-brain/tools/youtube-report.py" @yourhandle
SH
chmod +x ~/.hermes/scripts/youtube-report.sh

hermes cron create "0 8 * * *" --name "Channel daily" --no-agent \
  --script youtube-report.sh --deliver telegram
```

`--no-agent` means no model runs: Hermes executes the script and delivers what
it printed. Drop `--deliver telegram` to read it in the Hermes app instead.

**The scheduler must be running** or nothing fires:

```bash
hermes cron status          # says if jobs will fire
hermes gateway install      # starts it at login (macOS and Linux)
```

Your computer has to be awake at the scheduled time.

## 3. When you do want thinking

Leave out `--no-agent` and add a prompt. Hermes runs the script, reads its
output, reads your wiki, and writes you a brief:

```bash
hermes cron create "0 8 * * 1" "Below is this week's channel report. Read wiki/log.md and the relevant pages first. Copy the numbers exactly as printed, then tell me in under ten lines what needs me this week." \
  --name "Monday brief" --script youtube-report.sh --workdir "$HOME/shared-brain" --deliver telegram
```

## Build your own

Ask Claude Code, in this folder: *"Build me a script that reports X every
morning, then schedule it in Hermes."* It knows your business from the wiki and
your Hermes setup from this file.
