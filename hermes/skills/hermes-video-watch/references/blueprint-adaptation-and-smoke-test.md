# Blueprint Adaptation and Smoke-Test Notes

## Purpose

This note documents the public, portable design behind `hermes-video-watch`: a Hermes Agent skill for analyzing videos with both transcript and visual evidence.

## Upstream inspiration

Inspired by [`bradautomates/claude-video`](https://github.com/bradautomates/claude-video).

Useful ideas adapted:

- Download video assets with `yt-dlp`.
- Extract frames with `ffmpeg`.
- Pull captions before considering separate speech-to-text workflows.
- Support focused `--start` and `--end` ranges.
- Produce filesystem artifacts an agent can inspect: frames, manifest, report, transcript, and contact sheet.

Claude-specific assumptions not copied:

- Claude-specific environment variables.
- Claude-specific image-reading behavior.
- Slash-command packaging.
- Mandatory cloud transcription setup.

Hermes-oriented replacements:

- Skill entry point: `SKILL.md`.
- Helper script: `scripts/hermes_video_watch.py`.
- Visual triage: contact sheet first, selected frame analysis second.
- Artifacts: `report.md`, `manifest.json`, `frames/`, `contact_sheet.jpg`, and optional `transcript.txt`.

## Smoke-test pattern

A minimal local-video smoke test can be run without relying on network video availability by generating a short test clip:

```bash
TMP=$(mktemp -d)
ffmpeg -y -f lavfi -i testsrc=duration=3:size=320x180:rate=10 "$TMP/input.mp4"
python3 scripts/hermes_video_watch.py "$TMP/input.mp4" --max-frames 3 --resolution 320 --out-dir "$TMP/out" --no-subs
python3 - <<'PY'
import json, os, pathlib
out = pathlib.Path(os.environ['TMP']) / 'out'
manifest = json.loads((out / 'manifest.json').read_text())
print('report_exists', (out / 'report.md').exists())
print('manifest_exists', (out / 'manifest.json').exists())
print('frames_count', len(manifest['frames']))
print('contact_sheet_exists', (out / 'contact_sheet.jpg').exists())
PY
```

## Design choices

### Prefer focused extraction for long videos

For long videos, transcript-guided timestamp selection usually produces better evidence than sparse random sampling. Extract focused segments around diagrams, demos, slides, code, UI screens, and terminal output.

### Contact sheet first

A contact sheet lets the agent choose useful frames before spending context on individual screenshots.

### Captions are optional

Missing captions should not block visual analysis. The helper reports transcript absence honestly and still extracts frames.

### Portable paths

The public helper script accepts caller-provided output directories and otherwise uses a temporary directory. It should not require machine-specific absolute paths.
