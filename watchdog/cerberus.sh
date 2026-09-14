#!/usr/bin/env bash
# Cerberus: a watchdog for your Hermes server.
#
# Deliberately has NO model. Checking whether a site returns 200 is curl and an
# `if`. An LLM here costs money, adds latency, and can decide everything is fine
# when it is not. A shell script cannot hallucinate a 200.
#
# Silent on success. One message per distinct failure, sent through Hermes'
# own gateway, saying what broke and where to look. State lives in
# ~/.hermes/cerberus/ so a standing failure alerts once, not every run.
#
#   cerberus.sh --quick    the site only. Run hourly.
#   cerberus.sh            everything. Run daily.
#
# Install (crontab -e):
#   17 * * * * /path/to/repo/watchdog/cerberus.sh --quick
#   30 8 * * * /path/to/repo/watchdog/cerberus.sh
#
# Written for Linux (GNU stat/df). Edit the five settings below.

set -uo pipefail

SITE="https://example.com"            # the one URL that makes you money
ALERT_TO="telegram:Your Name"         # any `hermes send -t` target
HERMES_SERVICE="hermes-serve"         # systemd unit name, or "" to skip
WIKI="$HOME/hermes-research-agent"    # the wiki clone the agent works in
DISK_PCT_MAX=85
STALE_HOURS=30                        # a nightly job silent for 30h missed a run

STATE="$HOME/.hermes/cerberus"
mkdir -p "$STATE"

# alert <key> <message>: once per distinct failure; cleared when the check passes.
alert() {
  local flag="$STATE/$1.failing"
  if [ -f "$flag" ] && [ "$(cat "$flag")" = "$2" ]; then
    return 0
  fi
  printf '%s' "$2" > "$flag"
  hermes send -t "$ALERT_TO" "🔴 Cerberus: $2" >/dev/null 2>&1 \
    || echo "cerberus: send FAILED for: $2" >&2
}

clear_alert() { rm -f "$STATE/$1.failing"; }

# Hours since the repo's last commit. Not the mtime of .git/HEAD: on a branch
# that file never changes when you commit, so every healthy repo looks stale.
commit_age_hours() {
  local ts
  ts=$(git -C "$1" log -1 --format=%ct 2>/dev/null) || { echo 99999; return; }
  [ -n "$ts" ] || { echo 99999; return; }
  echo $(( ( $(date +%s) - ts ) / 3600 ))
}

check_site() {
  local code
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$SITE" 2>/dev/null)
  if [ "$code" = "200" ]; then clear_alert site
  else alert site "$SITE returned ${code:-no response}."
  fi
}

check_hermes() {
  [ -n "$HERMES_SERVICE" ] || return 0
  if systemctl is-active --quiet "$HERMES_SERVICE"; then clear_alert hermes
  else alert hermes "$HERMES_SERVICE is not active. journalctl -u $HERMES_SERVICE -n 50"
  fi
}

check_disk() {
  local pct
  pct=$(df --output=pcent / | tail -1 | tr -dc '0-9')
  if [ "${pct:-0}" -lt "$DISK_PCT_MAX" ]; then clear_alert disk
  else alert disk "Disk at ${pct}% on /."
  fi
}

# Nightly jobs prove themselves by moving git, not by writing a log line.
# A log line gets written whether or not the job did anything.
check_wiki() {
  local age
  age=$(commit_age_hours "$WIKI")
  if [ "$age" -lt "$STALE_HOURS" ]; then clear_alert wiki
  else alert wiki "No commit in $WIKI for ${age}h. Is the nightly sync running?"
  fi
}

case "${1:-}" in
  --quick) check_site ;;
  *)       check_site; check_hermes; check_disk; check_wiki ;;
esac
