#!/usr/bin/env python3
"""Farm any video into one source file in raw/data/.

Input can be a YouTube / Instagram / TikTok / any yt-dlp URL, or a local video
file. Captions are used when the platform has them; otherwise the audio is
transcribed locally with whisper.cpp (no API key). The file is written in the
house format with three TODOs for the agent that reads it afterwards.

    python3 tools/farm.py <url-or-file> [--dir <subfolder>] [--dry-run]

Writes raw/data/[<dir>/]<date>-<kebab-title>.md and prints the path.
Refuses to overwrite: raw/ is immutable once written.

Local transcription needs `whisper-cli` (brew install whisper-cpp) and a ggml
model; set WHISPER_MODEL to the model path (see README).
"""

import argparse
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date

REPO = pathlib.Path(__file__).resolve().parents[1]


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


def ytdlp():
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


def transcribe(media):
    """Local speech-to-text with whisper.cpp. Returns [(stamp, text)]."""
    if not shutil.which("whisper-cli"):
        sys.exit("No captions and whisper-cli not found. brew install whisper-cpp, then set WHISPER_MODEL.")
    model = os.environ.get("WHISPER_MODEL", "")
    if not model or not pathlib.Path(model).is_file():
        sys.exit("No captions and WHISPER_MODEL is not set to a ggml model file (see README).")
    with tempfile.TemporaryDirectory() as tmp:
        wav = f"{tmp}/a.wav"
        r = run(["ffmpeg", "-v", "error", "-y", "-i", str(media), "-vn", "-ac", "1", "-ar", "16000",
                 "-c:a", "pcm_s16le", wav])
        if r.returncode != 0:
            sys.exit(f"ffmpeg could not extract audio: {r.stderr.strip()[:300]}")
        r = run(["whisper-cli", "-m", model, "-f", wav, "-l", "auto", "-oj", "-of", f"{tmp}/out", "-np"])
        if r.returncode != 0:
            sys.exit(f"whisper-cli failed: {r.stderr.strip()[:300]}")
        segs = json.load(open(f"{tmp}/out.json")).get("transcription", [])
    out = []
    for s in segs:
        text = (s.get("text") or "").strip()
        if not text:
            continue
        ms = (s.get("offsets") or {}).get("from", 0)
        out.append((f"{ms // 60000}:{(ms // 1000) % 60:02d}", text))
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
    ap.add_argument("source", help="video URL, or path to a local video file")
    ap.add_argument("--dir", default="", help="subfolder under raw/data/")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    local = pathlib.Path(args.source).expanduser()
    is_file = local.is_file()
    lines, how = [], ""

    if is_file:
        title = local.stem.replace("_", " ").replace("-", " ")
        channel = "local file"
        day = date.fromtimestamp(local.stat().st_mtime).isoformat()
        probe = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(local)])
        secs = int(float(probe.stdout.strip() or 0))
        source_line = str(local)
        if not args.dry_run:
            lines, how = transcribe(local), "transcribed locally with whisper.cpp"
    else:
        yt = ytdlp()
        meta = run(yt + ["-J", "--no-warnings", "--skip-download", args.source])
        if meta.returncode != 0:
            sys.exit(f"yt-dlp could not read {args.source}:\n{meta.stderr.strip()[:400]}")
        info = json.loads(meta.stdout)
        title = info.get("title") or "untitled"
        channel = info.get("channel") or info.get("uploader") or "**[TODO: channel]**"
        upload = info.get("upload_date") or ""
        day = f"{upload[:4]}-{upload[4:6]}-{upload[6:]}" if len(upload) == 8 else "0000-00-00"
        secs = int(info.get("duration") or 0)
        source_line = args.source
        has_captions = bool(info.get("subtitles") or info.get("automatic_captions"))
        if not args.dry_run:
            with tempfile.TemporaryDirectory() as tmp:
                if has_captions:
                    sub = run(yt + ["--skip-download", "--write-auto-subs", "--write-subs",
                                    "--sub-langs", "en.*", "--sub-format", "vtt", "-o", f"{tmp}/cap", args.source])
                    vtts = sorted(pathlib.Path(tmp).glob("*.vtt"))
                    lines = clean_captions(vtts[0].read_text(errors="replace")) if vtts else []
                    how = "auto-generated captions, de-duplicated"
                    if not lines:
                        err = (sub.stderr or "").strip().splitlines()
                        sys.exit(f"{args.source} has captions but none downloaded. Nothing written.\n"
                                 f"  {err[-1] if err else 'no error reported'}\n"
                                 f"  HTTP 429 means the platform is rate-limiting: wait and re-run.")
                else:
                    # Instagram, TikTok and most reels: no caption track, so download the
                    # audio and transcribe it locally.
                    dl = run(yt + ["--no-warnings", "-f", "ba/b", "-o", f"{tmp}/media.%(ext)s", args.source])
                    media = next(iter(pathlib.Path(tmp).glob("media.*")), None)
                    if dl.returncode != 0 or media is None:
                        sys.exit(f"yt-dlp could not download {args.source}:\n{dl.stderr.strip()[:400]}\n"
                                 f"  Instagram/TikTok often need browser cookies: yt-dlp --cookies-from-browser chrome")
                    lines, how = transcribe(media), "no captions; transcribed locally with whisper.cpp"

    duration = f"{secs // 60}:{secs % 60:02d}" if secs else "**[TODO: duration]**"
    out_dir = REPO / "raw" / "data" / args.dir
    out = out_dir / f"{day}-{kebab(title)}.md"
    if out.exists():
        sys.exit(f"{out.relative_to(REPO)} already exists. raw/ is immutable.")

    if args.dry_run:
        print(f"would write {out.relative_to(REPO)} ({'local file' if is_file else 'url'}, {duration})")
        return

    body = "\n\n".join(paragraphs(lines)) if lines else \
        "**[TODO: nothing transcribable. Summarise by hand.]**"
    doc = f"""# {title}

*Video transcript, farmed by Argus. **[TODO: one line on why this was farmed.]***

| | |
|---|---|
| Source | {source_line} |
| Channel | {channel} |
| Published | {day} |
| Duration | {duration} |
| Transcript | {how} |

## What this covers

**[TODO: what the video establishes, including what was seen on screen, marked seen not heard.]**

## What it does not cover

**[TODO: the coverage limits. This is the half that gets forgotten.]**

## Transcript

{body}
"""
    out_dir.mkdir(parents=True, exist_ok=True)
    out.write_text(doc)
    print(out.relative_to(REPO))


if __name__ == "__main__":
    main()
