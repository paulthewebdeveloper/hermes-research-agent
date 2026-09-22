#!/usr/bin/env python3
"""Live topic scan: what is being watched this week, and which of it a small channel made.

    trends.py                          # the default niche queries
    trends.py "claude code obsidian"   # your own
    trends.py --all-time "query"       # who owns the query outright, not just this week

For each query: this week's long-form uploads sorted by views. Then the top few of each
are looked up one by one for subscriber counts, because views/subs is the signal that
matters at this channel size: over 1x means the video travelled past the channel's own
audience, and a big ratio on a tiny channel is a topic anyone can win.

No API key, yt-dlp only. Pair it with your own curated-channel report if you keep one.
"""
import concurrent.futures as cf, datetime as dt, json, subprocess, sys

WEEK, ALL_TIME = "CAMSBAgDEAE", "CAMSAhAB"     # YouTube search filters: this week / any time, by view count
N, ENRICH = 12, 8                              # results read per query; every row printed gets a subs lookup (4 missed the best find)
DEFAULT = ["claude code", "ai agent setup", "hermes agent", "claude skills", "ai coding agent",
           "agent memory", "claude code obsidian", "ai second brain"]   # edit for your niche


def ytdlp(args):
    r = subprocess.run(["yt-dlp", "--no-warnings", "-J"] + args, capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 and r.stdout else {}


def scan(q, sp):
    d = ytdlp(["--flat-playlist", "--playlist-end", str(N),
               f"https://www.youtube.com/results?search_query={q.replace(' ', '+')}&sp={sp}"])
    rows = [{"id": e["id"], "title": e.get("title", ""), "views": e.get("view_count") or 0,
             "mins": round((e.get("duration") or 0) / 60), "chan": e.get("channel") or ""}
            for e in d.get("entries", []) if (e.get("duration") or 0) >= 90 and e.get("view_count")]   # no Shorts
    return sorted(rows, key=lambda r: -r["views"])


def enrich(row):
    d = ytdlp(["--skip-download", f"https://youtu.be/{row['id']}"])
    up = d.get("upload_date")
    row["subs"] = d.get("channel_follower_count")
    row["days"] = max((dt.date.today() - dt.date(int(up[:4]), int(up[4:6]), int(up[6:]))).days, 1) if up else None
    return row


if __name__ == "__main__":
    sp = ALL_TIME if "--all-time" in sys.argv else WEEK
    queries = [a for a in sys.argv[1:] if not a.startswith("--")] or DEFAULT
    with cf.ThreadPoolExecutor(8) as ex:
        found = dict(zip(queries, ex.map(lambda q: scan(q, sp), queries)))
        top = {r["id"]: r for rows in found.values() for r in rows[:ENRICH]}
        list(ex.map(enrich, top.values()))
    for q in queries:
        print(f"\n## {q}" + ("  (all time)" if sp == ALL_TIME else "  (this week)"))
        for r in found[q][:8]:
            subs, days = r.get("subs"), r.get("days")
            ratio = f"{r['views'] / subs:6.1f}x subs" if subs else " " * 12
            age = f"{days:>3}d" if days else "    "
            print(f"- {r['views']:>9,} · {ratio} · {age} · {r['mins']:>3}m · {r['chan']}"
                  + (f" ({subs:,})" if subs else "") + f" · {r['title']}\n      https://youtu.be/{r['id']}")
    small = sorted((r for r in top.values() if r.get("subs") and r["views"] / r["subs"] >= 1),
                   key=lambda r: -r["views"] / r["subs"])
    if small:
        print("\n## Travelled past their own audience (views >= subs)")
        for r in small:
            print(f"- {r['views'] / r['subs']:6.1f}x · {r['views']:,} views · {r['subs']:,} subs · {r['chan']} · {r['title']}")
