---
name: hermes-video-watch
description: Analyze videos, YouTube links, screen recordings, and educational clips in Hermes Agent by extracting transcripts, focused screenshots, contact sheets, and timestamped visual evidence.
version: 1.0.0
author: Hermes Video Watch Contributors
license: MIT
metadata:
  hermes:
    tags: [video, youtube, screenshots, transcript, ffmpeg, yt-dlp, vision, study-guides]
    related_skills: [youtube-content, ocr-and-documents, media-analysis]
---

# Hermes Video Watch

## Overview

Use this skill when a user provides a public video URL or local video file and needs analysis grounded in what is **seen** and **heard**. It is inspired by [`bradautomates/claude-video`](https://github.com/bradautomates/claude-video) and adapted for Hermes Agent conventions and tools.

The core principle: transcripts explain what was said; frames show what mattered visually. For lectures, tutorials, product demos, slides, diagrams, UI walkthroughs, and screen recordings, high-quality answers should combine transcript evidence with selected visual evidence.

## When to Use

Use this skill when:

- A user shares a YouTube, Vimeo, Loom, TikTok, X, Instagram, or other accessible video URL and asks for analysis.
- A user shares a local `.mp4`, `.mov`, `.mkv`, `.webm`, or screen recording.
- A user asks what happens at a specific timestamp or range.
- A user asks for screenshots, diagrams, visual examples, contact sheets, or timestamped visual evidence.
- A user wants a study guide or report from a video whose visuals are important.
- A user wants spoken claims compared with on-screen content.

Do **not** use this skill to bypass access controls, scrape login-only videos, or bulk archive copyrighted video. If a video is not publicly accessible, ask the user for a local export or authorized copy.

## Dependencies

The helper script requires:

- Python 3.10+
- `ffmpeg` and `ffprobe` on `PATH`
- `yt-dlp` either through `uvx --from yt-dlp yt-dlp` or as `yt-dlp` on `PATH`
- Optional: ImageMagick (`magick` or `convert`) for frame label annotation
- Optional STT when captions are unavailable or `--prefer-stt` is requested:
  - local `faster-whisper`, or
  - Groq Whisper (`GROQ_API_KEY`), OpenAI Whisper (`OPENAI_API_KEY` or `VOICE_TOOLS_OPENAI_KEY`), Mistral Voxtral (`MISTRAL_API_KEY`), or
  - a command provider configured with `--stt-command` / `HERMES_VIDEO_WATCH_STT_COMMAND`.

The script prefers `uvx --from yt-dlp yt-dlp` when `uvx` is available because it usually provides a fresh `yt-dlp` without requiring a global install.

## Core Workflow

### 1. Choose extraction mode

For short videos, a sparse or moderate scan is usually acceptable. For long videos, avoid random sampling across the whole file. Instead:

1. Fetch or inspect transcript/captions when available.
2. Identify timestamp clusters where visuals likely matter: diagrams, screens, charts, slides, demos, terminals, settings, workflows, code, or architecture.
3. Extract focused ranges around those timestamps.
4. Inspect the contact sheet first.
5. Analyze only the best individual frames in detail.

### 2. Run the helper script

From an installed skill directory:

```bash
python3 scripts/hermes_video_watch.py \
  "<video-url-or-local-path>" \
  --start 01:08:00 \
  --end 01:09:00 \
  --max-frames 12 \
  --resolution 1280 \
  --out-dir /tmp/hermes-video-watch-example
```

For a short full-video scan:

```bash
python3 scripts/hermes_video_watch.py \
  "<video-url-or-local-path>" \
  --max-frames 40 \
  --resolution 768
```

For readable screenshots from slides, code, or terminal demos:

```bash
python3 scripts/hermes_video_watch.py \
  "$VIDEO_URL" \
  --start 03:47:00 \
  --end 03:48:00 \
  --max-frames 8 \
  --resolution 1280 \
  --keep-video
```

For optional STT fallback when captions are missing:

```bash
python3 scripts/hermes_video_watch.py \
  "<video-url-or-local-path>" \
  --stt-provider auto \
  --stt-language en
```

For long-video deep mode, let the helper find visual-cue transcript clusters, then extract multiple focused ranges instead of doing one sparse 100-frame scan:

```bash
python3 scripts/hermes_video_watch.py "$VIDEO_URL_OR_FILE" \
  --suggest-ranges \
  --stt-provider auto \
  --range-padding 20 \
  --max-ranges 8 \
  --out-dir /tmp/hermes-video-watch-deep

python3 scripts/hermes_video_watch.py "$VIDEO_URL_OR_FILE" \
  --ranges /tmp/hermes-video-watch-deep/suggested_ranges.json \
  --max-frames 12 \
  --resolution 1280 \
  --out-dir /tmp/hermes-video-watch-deep-focused
```

Default visual cues include `diagram`, `screen`, `slide`, `chart`, `look at`, `shown here`, `architecture`, `workflow`, `terminal`, `command`, `code`, `demo`, `settings`, `dashboard`, `UI`, and `example`; override with `--visual-cues`. `--ranges` creates `ranges/001.../` subfolders with their own frames/contact sheet/report/manifest plus a top-level `multi_range_manifest.json`. Treat the manifest `visual_coverage_mode` as a claim boundary: `suggested_ranges` is not visual inspection, and `multi_range_focused` covers only the listed ranges.

To prefer a specific Whisper/Voxtral provider over captions:

```bash
OPENAI_API_KEY=*** python3 scripts/hermes_video_watch.py \
  "$VIDEO_URL" \
  --prefer-stt \
  --stt-provider openai \
  --stt-model whisper-1
```

To use another transcriber configured in the environment:

```bash
python3 scripts/hermes_video_watch.py ./recording.mp4 \
  --stt-provider command \
  --stt-command 'my-transcriber --json {audio}'
```

STT modes:

- `--stt-provider none`: never transcribe audio.
- `--stt-provider auto`: use a configured command, local `faster-whisper`, or available API key.
- `--stt-provider local|groq|openai|mistral|command`: force one provider.
- `--prefer-stt`: try STT even when captions exist; captions remain the fallback if STT fails.
- `--audio-format mp3|wav`: choose extracted audio format for STT.

No key is needed if captions exist or local `faster-whisper` is installed. API keys are optional but often improve accuracy and setup speed.

### 3. Inspect artifacts

The helper creates:

- `report.md` — human-readable summary with source, range, frames, and transcript excerpt.
- `manifest.json` — machine-readable paths, timestamps, metadata, transcript path, and contact sheet path.
- `frames/` — extracted screenshot frames.
- `contact_sheet.jpg` — tiled overview of extracted frames.
- `download/` — downloaded video/clip and metadata for URL sources.
- `transcript.txt` — timestamped transcript from captions/subtitles or configured STT.
- `suggested_ranges.json` — transcript-guided long-video visual range suggestions when `--suggest-ranges` is used.
- `multi_range_manifest.json` plus `ranges/001.../` — focused multi-range artifacts when `--ranges` is used.

Inspect the manifest:

```bash
python3 - <<'PY'
import json, pathlib
m = json.loads(pathlib.Path('/tmp/hermes-video-watch-example/manifest.json').read_text())
print(m['summary'])
print('\n'.join(f"{f['timestamp']} {f['path']}" for f in m['frames'][:10]))
PY
```

### 4. Use Hermes vision selectively

First inspect `contact_sheet.jpg` to choose the frames worth deeper analysis. Then analyze only selected individual frames. Avoid loading dozens of frames when a contact sheet can triage them.

Example vision prompt:

```text
Which frames contain diagrams, slides, terminal demos, UI states, or visual explanations worth preserving? Return frame labels/timestamps and why.
```

Example individual frame prompt:

```text
Describe the diagram and extract any readable labels. Explain why it matters for the study guide.
```

## Failure Modes and Fixes

### Video download returns 403 or fails

Try a fresh `yt-dlp` through `uvx`:

```bash
uvx --from yt-dlp yt-dlp --version
```

If download still fails:

- Try a focused range instead of full download.
- Try a lower-resolution format selector such as `b[height<=720]/best[height<=720]/best`.
- If the platform requires authentication, ask for a local authorized export.

### No transcript available

Continue with frame/contact-sheet analysis and state the limitation clearly:

> Captions and configured STT were unavailable, so the analysis is based on frames only. Provide captions or configure `--stt-provider local|groq|openai|mistral|command` if spoken-word accuracy is required.

If API-backed STT fails, check the matching key (`GROQ_API_KEY`, `OPENAI_API_KEY` / `VOICE_TOOLS_OPENAI_KEY`, or `MISTRAL_API_KEY`) and try a shorter timestamp range.

### Frames are unreadable

Re-run a narrower range with higher resolution:

```bash
--resolution 1280 --max-frames 8 --start <timestamp> --end <timestamp+30s>
```

Increase resolution and narrow the range before increasing frame count.

## Verification Checklist

Before reporting video analysis as complete:

- [ ] `report.md` exists and is non-empty.
- [ ] `manifest.json` exists and parses.
- [ ] Frame count matches the task.
- [ ] `contact_sheet.jpg` exists when frames exist.
- [ ] Transcript availability is stated honestly.
- [ ] Visual artifacts were inspected when the user asked about visuals.
- [ ] Screenshots used in documents have timestamped captions and are placed near relevant explanations.

## References

- `examples/youtube-study-guide-prompt.md`
- `examples/screen-recording-qa-prompt.md`
- `examples/timestamp-specific-visual-analysis-prompt.md`
- `references/blueprint-adaptation-and-smoke-test.md`
- `references/youtube-download-troubleshooting.md`
- `research/hermes-video-watch-public-packaging.md`
