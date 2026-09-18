#!/usr/bin/env python3
"""Daily YouTube channel report: views since yesterday and comments waiting for a reply.

No API key and no AI model: it reads public numbers with yt-dlp, so running it costs nothing.

    python3 tools/youtube-report.py @yourhandle

Schedule it with Hermes (see examples/daily-report.md). Needs yt-dlp on PATH.
Run it on your own computer: YouTube blocks most cloud servers.
"""
import json, pathlib, subprocess, sys

STATE = pathlib.Path.home() / ".hermes" / "cron-state" / "youtube-report.json"


def ytdlp(args):
    r = subprocess.run(["yt-dlp", "--no-warnings"] + args, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("yt-dlp failed: " + (r.stderr.strip().splitlines() or ["no error text"])[-1])
    return json.loads(r.stdout)


def main():
    if len(sys.argv) != 2 or not sys.argv[1].startswith("@"):
        sys.exit("usage: youtube-report.py @yourhandle")
    handle = sys.argv[1]
    data = ytdlp(["--flat-playlist", "--playlist-end", "10", "-J", f"https://www.youtube.com/{handle}/videos"])
    prev = json.loads(STATE.read_text()) if STATE.exists() else {}
    now, lines = {}, []
    for e in data.get("entries") or []:
        views = int(e.get("view_count") or 0)
        before = prev.get(e["id"])
        delta = f" (+{views - before:,})" if before is not None else ""
        info = ytdlp(["--skip-download", "--write-comments", "-J", f"https://www.youtube.com/watch?v={e['id']}"])
        comments = info.get("comments") or []
        replied = {c["parent"] for c in comments if c.get("parent") != "root" and c.get("author") == handle}
        waiting = [c for c in comments if c.get("parent") == "root" and c.get("author") != handle and c.get("id") not in replied]
        lines.append(f"{views:,}{delta} views: {e.get('title', '')[:60]}" + (f", {len(waiting)} comment(s) waiting" if waiting else ""))
        lines += [f"   {c.get('author')}: {c.get('text', '')[:100].strip()}" for c in waiting[:3]]
        now[e["id"]] = views
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(now))
    print(f"Channel report for {handle}:")
    print("\n".join(lines) if lines else "No videos found.")


if __name__ == "__main__":
    main()
