#!/usr/bin/env python3
"""Farm a video URL into one source file in raw/data/.

The mechanical half of an ingest: fetch the metadata and the captions, strip
YouTube's rolling-caption repeats, and write one markdown file. It does NOT
decide what the video means — the agent that reads the transcript afterwards
fills the TODOs.

    python3 tools/farm.py <url> [--dir <subfolder>] [--dry-run]

Writes raw/data/[<dir>/]<upload-date>-<kebab-title>.md and prints the path.
Refuses to overwrite: raw/ is immutable once written.
"""

import argparse
import json
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parents[1]


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def ytdlp():
    """yt-dlp on PATH, else the uvx shim."""
    if shutil.which("yt-dlp"):
        return ["yt-dlp"]
    if shutil.which("uvx"):
        return ["uvx", "--from", "yt-dlp", "yt-dlp"]
    sys.exit("yt-dlp not found. Install it (brew/apt/pipx install yt-dlp) or install uv.")


def kebab(text, words=7):
    text = re.sub(r"[^\w\s-]", "", text.lower())
    parts = [w for w in re.split(r"[\s_-]+", text) if w]
    return "-".join(parts[:words]) or "untitled"


def clean_captions(vtt_text):
    """Strip WEBVTT cruft, inline tags, and the rolling repeat.

    YouTube auto-captions emit each line twice (incoming and outgoing), so keep
    the first sighting of each line: order preserved, length halved.
    """
    out, prev, stamp = [], None, None
    for line in vtt_text.splitlines():
        m = re.match(r"^(\d\d):(\d\d):(\d\d)\.\d+ -->", line)
        if m:
            h, mnt, sec = m.groups()
            stamp = f"{int(h) * 60 + int(mnt)}:{sec}"
            continue
        text = re.sub(r"<[^>]+>", "", line).strip()
        if not text or text.startswith(("WEBVTT", "Kind:", "Language:")) or text == prev:
            continue
        prev = text
        out.append((stamp, text))
    return out


def paragraphs(lines, every=12):
    blocks, buf, start = [], [], None
    for stamp, text in lines:
        start = start or stamp
        buf.append(text)
        if len(buf) >= every:
            blocks.append(f"[{start}] " + " ".join(buf))
            buf, start = [], None
    if buf:
        blocks.append(f"[{start}] " + " ".join(buf))
    return blocks


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--dir", default="", help="subfolder under raw/data/")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    yt = ytdlp()
    meta = run(yt + ["-J", "--no-warnings", "--skip-download", args.url])
    if meta.returncode != 0:
        sys.exit(f"yt-dlp could not read {args.url}:\n{meta.stderr.strip()[:400]}")
    info = json.loads(meta.stdout)

    title = info.get("title") or "untitled"
    channel = info.get("channel") or info.get("uploader") or "**[TODO: channel]**"
    upload = info.get("upload_date") or ""
    date = f"{upload[:4]}-{upload[4:6]}-{upload[6:]}" if len(upload) == 8 else "0000-00-00"
    secs = int(info.get("duration") or 0)
    duration = f"{secs // 60}:{secs % 60:02d}" if secs else "**[TODO: duration]**"

    out_dir = REPO / "raw" / "data" / args.dir
    out = out_dir / f"{date}-{kebab(title)}.md"
    if out.exists():
        sys.exit(f"{out.relative_to(REPO)} already exists. raw/ is immutable.")

    # If YouTube says captions exist, an empty download is a failed fetch, not a
    # silent video. A hollow source file is worse than crashing: it looks farmed.
    has_captions = bool(info.get("subtitles") or info.get("automatic_captions"))

    with tempfile.TemporaryDirectory() as tmp:
        sub = run(yt + ["--skip-download", "--write-auto-subs", "--write-subs",
                        "--sub-langs", "en.*", "--sub-format", "vtt",
                        "-o", f"{tmp}/cap", args.url])
        vtts = sorted(pathlib.Path(tmp).glob("*.vtt"))
        lines = clean_captions(vtts[0].read_text(errors="replace")) if vtts else []

    if has_captions and not lines:
        err = (sub.stderr or "").strip().splitlines()
        sys.exit(f"{args.url} has captions but none downloaded. Nothing written.\n"
                 f"  {err[-1] if err else 'no error reported'}\n"
                 f"  HTTP 429 means YouTube is rate-limiting: wait and re-run.")

    body = "\n\n".join(paragraphs(lines)) if lines else \
        "**[TODO: no captions. Transcribe or summarise by hand.]**"

    doc = f"""# {title}

*Video transcript, farmed by Argus. **[TODO: one line on why this was farmed.]***

| | |
|---|---|
| URL | {args.url} |
| Channel | {channel} |
| Published | {date} |
| Duration | {duration} |
| Captions | {"auto-generated, de-duplicated" if lines else "none available"} |

## What this covers

**[TODO: what the video establishes, including what was seen on screen, marked seen not heard.]**

## What it does not cover

**[TODO: the coverage limits. This is the half that gets forgotten.]**

## Transcript

{body}
"""

    if args.dry_run:
        print(f"would write {out.relative_to(REPO)} ({len(lines)} caption lines)")
        return
    out_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(doc)
    print(out.relative_to(REPO))


if __name__ == "__main__":
    main()
