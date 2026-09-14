# Hermes Video Watch

A Hermes Agent skill for video-aware analysis. It extracts transcripts, frames, contact sheets, and timestamped artifacts from public video URLs or local video files so an agent can answer with evidence from both spoken content and visuals.

Inspired by [`bradautomates/claude-video`](https://github.com/bradautomates/claude-video), adapted for Hermes Agent skill packaging and Hermes-native workflows.

## What it does

- Downloads or clips videos with `yt-dlp`.
- Extracts frames with `ffmpeg`.
- Creates a contact sheet for low-token visual triage.
- Fetches captions/subtitles when available, with optional speech-to-text (STT) fallback.
- Writes `report.md`, `manifest.json`, `frames/`, `contact_sheet.jpg`, and optional `transcript.txt`.
- Supports URL and local-video workflows.
- Supports focused timestamp ranges for long videos.

## Dependencies

Required:

- Python 3.10+
- `ffmpeg` and `ffprobe` on `PATH`
- `yt-dlp` through either:
  - `uvx --from yt-dlp yt-dlp` (preferred when `uvx` is available), or
  - `yt-dlp` installed on `PATH`

Optional:

- ImageMagick (`magick` or `convert`) for annotating frame labels directly onto images.
- Optional STT providers when captions are missing or when `--prefer-stt` is used:
  - Local [`faster-whisper`](https://github.com/SYSTRAN/faster-whisper) installed in the Python environment.
  - Groq Whisper with `GROQ_API_KEY`.
  - OpenAI Whisper with `OPENAI_API_KEY` or `VOICE_TOOLS_OPENAI_KEY`.
  - Mistral Voxtral with `MISTRAL_API_KEY`.
  - Any command-line transcriber via `--stt-command` or `HERMES_VIDEO_WATCH_STT_COMMAND`.

No API key or Whisper install is needed when platform captions are available. STT is optional but recommended when captions are absent or accuracy matters.

Example macOS setup:

```bash
brew install ffmpeg uv
# Optional if you do not want uvx-based yt-dlp:
brew install yt-dlp
# Optional frame annotation:
brew install imagemagick
```

## Install

### Option 1: Manual clone into your Hermes skills directory

Because this skill includes a helper script, install the whole directory rather than only copying `SKILL.md`.

```bash
git clone https://github.com/<owner>/hermes-video-watch.git ./hermes-video-watch
# Then copy or symlink the package into your Hermes skills directory as appropriate for your setup.
```

Then restart Hermes, start a new session, or reload skills in an interactive Hermes session:

```text
/reload-skills
```

Load it explicitly when needed:

```bash
hermes -s hermes-video-watch
```

Or inside a Hermes session:

```text
/skill hermes-video-watch
```

### Option 2: Install from a published registry/tap identifier

If the skill has been published to a Hermes-supported registry or exposed through a tap, install by identifier:

```bash
hermes skills install hermes-video-watch
```

For a tap-backed distribution, users first add the tap:

```bash
hermes skills tap add <owner>/<tap-repo>
hermes skills install hermes-video-watch
```

### Option 3: Direct `SKILL.md` URL only for single-file variants

Hermes supports direct HTTP(S) install from a `SKILL.md` URL:

```bash
hermes skills install https://raw.githubusercontent.com/<owner>/<repo>/<branch>/SKILL.md
```

Do **not** use that mode for this full package unless you intentionally remove the helper script dependency; a raw `SKILL.md` install will not include `scripts/hermes_video_watch.py`.

### Publishing

To publish this skill through a Hermes-supported registry flow, pass the skill directory path:

```bash
hermes skills publish ./hermes-video-watch
# or, for a GitHub target when configured/supported:
hermes skills publish ./hermes-video-watch --to github --repo <owner>/<repo>
```

## Quick start

Focused extraction around a timestamp range:

```bash
python3 scripts/hermes_video_watch.py \
  "https://www.youtube.com/watch?v=VIDEO_ID" \
  --start 00:10:30 \
  --end 00:10:45 \
  --max-frames 6 \
  --resolution 1280 \
  --out-dir /tmp/hermes-video-watch-demo
```

Local file scan:

```bash
python3 scripts/hermes_video_watch.py \
  ./recording.mp4 \
  --max-frames 20 \
  --resolution 768 \
  --out-dir /tmp/hermes-video-watch-local
```

Use STT when captions are unavailable:

```bash
python3 scripts/hermes_video_watch.py \
  ./recording.mp4 \
  --stt-provider auto \
  --stt-language en \
  --out-dir /tmp/hermes-video-watch-stt
```

Prefer a cloud Whisper provider over captions:

```bash
GROQ_API_KEY=*** python3 scripts/hermes_video_watch.py \
  "https://www.youtube.com/watch?v=VIDEO_ID" \
  --prefer-stt \
  --stt-provider groq \
  --stt-model whisper-large-v3-turbo
```

Use a custom command provider. The command may print plain text or JSON with `segments` containing `start`, `end`, and `text` fields:

```bash
python3 scripts/hermes_video_watch.py ./meeting.mp4 \
  --stt-provider command \
  --stt-command 'my-transcriber --json {audio}'
```

Long-video deep mode: first suggest transcript-guided visual ranges, then extract focused screenshots for those ranges:

```bash
python3 scripts/hermes_video_watch.py ./lecture.mp4 \
  --suggest-ranges \
  --stt-provider auto \
  --range-padding 20 \
  --max-ranges 8 \
  --out-dir /tmp/hermes-video-watch-deep

python3 scripts/hermes_video_watch.py ./lecture.mp4 \
  --ranges /tmp/hermes-video-watch-deep/suggested_ranges.json \
  --max-frames 12 \
  --resolution 1280 \
  --out-dir /tmp/hermes-video-watch-deep-focused
```

`suggested_ranges.json` is built from captions/STT transcript cues such as `diagram`, `screen`, `slide`, `chart`, `look at`, `shown here`, `architecture`, `workflow`, `terminal`, `command`, `code`, `demo`, `settings`, `dashboard`, `UI`, and `example`. Override with `--visual-cues "diagram,demo,terminal"`. Multi-range extraction writes per-range artifacts under `ranges/001.../` and a top-level `multi_range_manifest.json`. Manifests include `visual_coverage_mode` (`single_range_or_scan`, `suggested_ranges`, or `multi_range_focused`) so downstream answers do not overclaim coverage.

STT-related environment variables:

- `HERMES_VIDEO_WATCH_STT_PROVIDER`: `none`, `auto`, `local`, `groq`, `openai`, `mistral`, or `command`.
- `HERMES_VIDEO_WATCH_STT_COMMAND`: command provider template with optional `{audio}` placeholder.
- `HERMES_VIDEO_WATCH_STT_MODEL`: default model override.
- `GROQ_API_KEY`, `OPENAI_API_KEY` or `VOICE_TOOLS_OPENAI_KEY`, `MISTRAL_API_KEY`: cloud provider keys.

Transcript behavior:

- Captions are fetched first by default.
- If captions are missing, `--stt-provider auto` tries a configured STT provider.
- `--prefer-stt` transcribes audio even when captions are available and falls back to captions if STT fails.
- `--stt-provider none` disables STT entirely.

Inspect outputs:

```bash
python3 - <<'PY'
import json, pathlib
manifest = pathlib.Path('/tmp/hermes-video-watch-demo/manifest.json')
data = json.loads(manifest.read_text())
print(data['summary'])
for frame in data['frames'][:5]:
    print(frame['timestamp'], frame['path'])
PY
```

## Example prompts

See:

- `examples/youtube-study-guide-prompt.md`
- `examples/screen-recording-qa-prompt.md`
- `examples/timestamp-specific-visual-analysis-prompt.md`

## Public release notes

This repository is intentionally portable:

- No machine-specific absolute paths are required.
- Output paths are caller-provided or temporary.
- `yt-dlp` can run through `uvx` or from `PATH`.
- The helper does not require Whisper or cloud transcription by default.
- The skill does not bypass platform access controls.

## License

MIT. See `LICENSE`.
