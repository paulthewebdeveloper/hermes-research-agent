#!/usr/bin/env bash
# whisper-stt.sh — local STT for hermes-video-watch, via whisper.cpp.
#
# hermes_video_watch.py looks for `faster-whisper` or a cloud API key and finds
# neither on this Mac, so it silently produces transcript_source: none. This
# wrapper gives it the whisper.cpp binary that IS installed, as a command
# provider. Emits the JSON shape the script's parser expects.
#
#   export HERMES_VIDEO_WATCH_STT_COMMAND="<REPO>/tools/whisper-stt.sh {audio}"
#
# Usage: whisper-stt.sh /path/to/audio.(mp3|wav)
set -euo pipefail

AUDIO="${1:?usage: whisper-stt.sh <audio-file>}"
MODEL="${WHISPER_MODEL:?set WHISPER_MODEL to a ggml model file (see README)}"

[ -f "$MODEL" ] || { echo "model not found: $MODEL" >&2; exit 1; }
command -v whisper-cli >/dev/null || { echo "whisper-cli not on PATH" >&2; exit 1; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# whisper.cpp needs 16kHz mono PCM regardless of what it was handed
ffmpeg -v error -y -i "$AUDIO" -vn -ac 1 -ar 16000 -c:a pcm_s16le "$TMP/a.wav"

whisper-cli -m "$MODEL" -f "$TMP/a.wav" -oj -of "$TMP/out" -l auto -pp >/dev/null 2>&1

# whisper.cpp JSON -> {"segments":[{"start":s,"end":s,"text":"..."}]}
python3 - "$TMP/out.json" <<'PY'
import json, sys

def to_seconds(t):
    """whisper.cpp offsets are ms ints; timestamps are 'HH:MM:SS,mmm'."""
    if isinstance(t, (int, float)):
        return float(t) / 1000.0
    h, m, rest = str(t).split(":")
    s, _, ms = rest.replace(".", ",").partition(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms or 0) / 1000.0

raw = json.load(open(sys.argv[1]))
out = []
for seg in raw.get("transcription", []):
    text = (seg.get("text") or "").strip()
    if not text:
        continue
    off = seg.get("offsets") or {}
    ts = seg.get("timestamps") or {}
    start = off.get("from", ts.get("from", 0))
    end = off.get("to", ts.get("to"))
    out.append({
        "start": to_seconds(start),
        "end": to_seconds(end) if end is not None else None,
        "text": text,
    })
print(json.dumps({"segments": out}))
PY
