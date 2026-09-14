#!/usr/bin/env python3
"""Hermes-native video watch helper.

Downloads or clips a video, extracts frames/contact sheet, pulls captions when
available, and writes report.md + manifest.json for Hermes agents.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse

VIDEO_EXTS = {".mp4", ".mkv", ".webm", ".mov", ".m4v", ".avi", ".flv", ".wmv"}
DEFAULT_VISUAL_CUES = [
    "diagram", "screen", "slide", "chart", "look at", "shown here",
    "architecture", "workflow", "terminal", "command", "code", "demo",
    "settings", "dashboard", "ui", "example",
]


def eprint(*args):
    print(*args, file=sys.stderr)


def run(cmd: list[str], *, check: bool = False, cwd: Path | None = None) -> subprocess.CompletedProcess:
    eprint("[run]", " ".join(str(c) for c in cmd))
    return subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True, check=check)


def is_url(source: str) -> bool:
    p = urlparse(source)
    return p.scheme in ("http", "https") and bool(p.netloc)


def parse_time(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    s = str(value).strip()
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s)
    parts = s.split(":")
    if not 1 <= len(parts) <= 3:
        raise SystemExit(f"Invalid time: {value}")
    parts_f = [float(x) for x in parts]
    if len(parts_f) == 1:
        return parts_f[0]
    if len(parts_f) == 2:
        return parts_f[0] * 60 + parts_f[1]
    return parts_f[0] * 3600 + parts_f[1] * 60 + parts_f[2]


def fmt_time(seconds: float | int | None) -> str:
    if seconds is None:
        return "unknown"
    seconds = max(0, float(seconds))
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    if h:
        return f"{h:02d}:{m:02d}:{s:05.2f}"
    return f"{m:02d}:{s:05.2f}"


def time_arg(seconds: float | int | None) -> str | None:
    if seconds is None:
        return None
    return fmt_time(seconds).replace(".00", "")


def safe_time_for_name(seconds: float | int | None) -> str:
    if seconds is None:
        return "unknown"
    seconds = int(max(0, float(seconds)))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}h{m:02d}m{s:02d}s"


def pick_ytdlp() -> list[str]:
    override = os.environ.get("HERMES_VIDEO_WATCH_YTDLP")
    if override:
        return override.split()
    uvx = shutil.which("uvx")
    if uvx:
        return [uvx, "--from", "yt-dlp", "yt-dlp"]
    ytdlp = shutil.which("yt-dlp")
    if ytdlp:
        return [ytdlp]
    raise SystemExit("yt-dlp unavailable. Install with `brew install yt-dlp` or install uv (`brew install uv`).")


def require_binary(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise SystemExit(f"Required binary missing: {name}")
    return path


def ffprobe_duration(path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=nokey=1:noprint_wrappers=1", str(path)
    ]
    p = run(cmd)
    if p.returncode != 0:
        eprint(p.stderr.strip())
        return 0.0
    try:
        return float(p.stdout.strip())
    except Exception:
        return 0.0


def ffprobe_stream(path: Path) -> dict:
    cmd = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,codec_name", "-of", "json", str(path)
    ]
    p = run(cmd)
    if p.returncode != 0:
        return {}
    try:
        data = json.loads(p.stdout)
        return (data.get("streams") or [{}])[0]
    except Exception:
        return {}


def auto_fps(duration: float, max_frames: int, focused: bool) -> float:
    if duration <= 0:
        return 1.0
    if focused:
        if duration <= 30:
            target = min(max_frames, max(6, int(duration * 2)))
        elif duration <= 90:
            target = min(max_frames, 60)
        else:
            target = min(max_frames, 80)
    else:
        if duration <= 30:
            target = min(max_frames, 30)
        elif duration <= 60:
            target = min(max_frames, 40)
        elif duration <= 180:
            target = min(max_frames, 60)
        elif duration <= 600:
            target = min(max_frames, 80)
        else:
            target = min(max_frames, 100)
    return min(2.0, max(0.01, target / duration))


def find_video_file(directory: Path) -> Path | None:
    candidates: list[Path] = []
    for ext in VIDEO_EXTS:
        candidates.extend(directory.glob(f"*.{ext.lstrip('.')}"))
    candidates = sorted(set(candidates), key=lambda p: p.stat().st_size if p.exists() else 0, reverse=True)
    return candidates[0] if candidates else None


def download_subtitles(source: str, out_dir: Path) -> Path | None:
    if not is_url(source):
        return None
    subdir = out_dir / "subtitles"
    subdir.mkdir(parents=True, exist_ok=True)
    tmpl = str(subdir / "subs.%(ext)s")
    cmd = pick_ytdlp() + [
        "--skip-download", "--write-subs", "--write-auto-subs",
        "--sub-langs", "en,en-US,en-GB,en-orig", "--sub-format", "vtt",
        "--convert-subs", "vtt", "--no-playlist", "--ignore-errors",
        "-o", tmpl, "--", source,
    ]
    p = run(cmd)
    if p.returncode != 0:
        eprint("[warn] subtitle fetch failed:", (p.stderr or p.stdout)[-1000:])
    candidates = sorted(subdir.glob("*.vtt"))
    preferred = [c for c in candidates if ".en" in c.name or c.name.endswith("en.vtt")]
    return (preferred or candidates or [None])[0]


def timestamp_to_seconds(ts: str) -> float:
    left = ts.replace(",", ".")
    parts = left.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return float(parts[0])


def parse_vtt(vtt: Path, start: float | None, end: float | None) -> list[dict]:
    segments: list[dict] = []
    lines = vtt.read_text(errors="ignore").splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if "-->" not in line:
            i += 1
            continue
        a, b = [x.strip().split()[0] for x in line.split("-->", 1)]
        s = timestamp_to_seconds(a)
        e = timestamp_to_seconds(b)
        i += 1
        text_lines = []
        while i < len(lines) and lines[i].strip():
            t = re.sub(r"<[^>]+>", "", lines[i].strip())
            if t and not t.startswith("NOTE"):
                text_lines.append(t)
            i += 1
        text = " ".join(text_lines)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        if start is not None and e < start:
            continue
        if end is not None and s > end:
            continue
        if segments and segments[-1]["text"] == text:
            continue
        segments.append({"start": s, "end": e, "timestamp": fmt_time(s), "text": text})
    return segments


def download_video(source: str, out_dir: Path, start: float | None, end: float | None, fmt: str) -> Path:
    if not is_url(source):
        p = Path(source).expanduser().resolve()
        if not p.exists():
            raise SystemExit(f"Local video not found: {p}")
        return p
    dl = out_dir / "download"
    dl.mkdir(parents=True, exist_ok=True)
    tmpl = str(dl / "video.%(ext)s")
    cmd = pick_ytdlp() + [
        "-N", "8", "-f", fmt, "--merge-output-format", "mp4",
        "--write-info-json", "--no-playlist", "--ignore-errors", "-o", tmpl,
    ]
    if start is not None or end is not None:
        sec = "*"
        sec += fmt_time(start or 0).replace(".00", "")
        sec += "-"
        if end is not None:
            sec += fmt_time(end).replace(".00", "")
        cmd += ["--download-sections", sec, "--force-keyframes-at-cuts"]
    cmd += ["--", source]
    p = run(cmd)
    if p.returncode != 0:
        eprint("[warn] video download command returned non-zero:", (p.stderr or p.stdout)[-2000:])
    video = find_video_file(dl)
    if not video:
        raise SystemExit(f"yt-dlp did not produce a video file in {dl}. Last stderr:\n{(p.stderr or p.stdout)[-2000:]}")
    return video


def clip_local_if_needed(video: Path, out_dir: Path, start: float | None, end: float | None) -> Path:
    if is_url(str(video)) or (start is None and end is None):
        return video
    # URL clips are already section-downloaded. Local files need clipping.
    clipped = out_dir / "clip.mp4"
    cmd = ["ffmpeg", "-y"]
    if start is not None:
        cmd += ["-ss", str(start)]
    cmd += ["-i", str(video)]
    if end is not None:
        duration = end - (start or 0)
        if duration > 0:
            cmd += ["-t", str(duration)]
    cmd += ["-c", "copy", str(clipped)]
    p = run(cmd)
    if p.returncode == 0 and clipped.exists():
        return clipped
    eprint("[warn] stream-copy clip failed; using original video")
    return video


def extract_audio(video: Path, out_dir: Path, audio_format: str) -> Path:
    """Extract mono speech-friendly audio for optional STT providers."""
    audio_dir = out_dir / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    ext = "wav" if audio_format == "wav" else "mp3"
    audio = audio_dir / f"audio.{ext}"
    cmd = ["ffmpeg", "-y", "-i", str(video), "-vn", "-ac", "1", "-ar", "16000"]
    if ext == "mp3":
        cmd += ["-codec:a", "libmp3lame", "-b:a", "64k"]
    else:
        cmd += ["-f", "wav"]
    cmd.append(str(audio))
    p = run(cmd)
    if p.returncode != 0 or not audio.exists() or audio.stat().st_size == 0:
        raise RuntimeError(f"ffmpeg audio extraction failed:\n{p.stderr[-2000:]}")
    return audio


def _normalize_stt_segments(data, absolute_offset: float = 0.0) -> list[dict]:
    """Accept common STT JSON shapes and return report-ready segments."""
    if isinstance(data, str):
        text = re.sub(r"\s+", " ", data).strip()
        return [{"start": absolute_offset, "end": None, "timestamp": fmt_time(absolute_offset), "text": text}] if text else []
    if not isinstance(data, dict):
        return []
    raw_segments = data.get("segments") or data.get("chunks") or data.get("results") or []
    segments: list[dict] = []
    if isinstance(raw_segments, list) and raw_segments:
        for item in raw_segments:
            if not isinstance(item, dict):
                continue
            text = item.get("text") or item.get("transcript") or item.get("sentence") or ""
            text = re.sub(r"\s+", " ", str(text)).strip()
            if not text:
                continue
            start = item.get("start", item.get("start_time", item.get("timestamp", 0)))
            end = item.get("end", item.get("end_time"))
            if isinstance(start, (list, tuple)) and start:
                end = start[1] if len(start) > 1 else end
                start = start[0]
            try:
                start_f = float(start or 0) + absolute_offset
            except Exception:
                start_f = absolute_offset
            try:
                end_f = float(end) + absolute_offset if end is not None else None
            except Exception:
                end_f = None
            segments.append({"start": start_f, "end": end_f, "timestamp": fmt_time(start_f), "text": text})
    if segments:
        return segments
    text = data.get("text") or data.get("transcript") or data.get("translation") or ""
    text = re.sub(r"\s+", " ", str(text)).strip()
    return [{"start": absolute_offset, "end": None, "timestamp": fmt_time(absolute_offset), "text": text}] if text else []


def _curl_json_multipart(url: str, api_key: str, audio: Path, fields: dict[str, str]) -> dict:
    require_binary("curl")
    auth_header = "Authorization: Bearer " + api_key
    cmd = ["curl", "-sS", "-X", "POST", url, "-H", auth_header]
    safe_cmd = ["curl", "-sS", "-X", "POST", url, "-H", "Authorization: Bearer ***"]
    for key, value in fields.items():
        if value is not None and value != "":
            cmd += ["-F", f"{key}={value}"]
            safe_cmd += ["-F", f"{key}={value}"]
    cmd += ["-F", f"file=@{audio}"]
    safe_cmd += ["-F", f"file=@{audio}"]
    eprint("[run]", " ".join(str(c) for c in safe_cmd))
    p = subprocess.run(cmd, text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout)[-2000:])
    try:
        data = json.loads(p.stdout)
    except Exception as exc:
        raise RuntimeError(f"provider returned non-JSON response: {p.stdout[:500]}") from exc
    if isinstance(data, dict) and data.get("error"):
        raise RuntimeError(json.dumps(data.get("error"), ensure_ascii=False))
    return data


def transcribe_local(audio: Path, model: str | None, language: str | None, absolute_offset: float) -> tuple[list[dict], str]:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except Exception as exc:
        raise RuntimeError("local STT requires `faster-whisper` to be installed") from exc
    model_name = model or os.environ.get("HERMES_VIDEO_WATCH_STT_MODEL") or "small"
    whisper = WhisperModel(model_name, device="auto", compute_type="auto")
    kwargs = {"vad_filter": True}
    if language:
        kwargs["language"] = language
    raw_segments, _info = whisper.transcribe(str(audio), **kwargs)
    segments = []
    for seg in raw_segments:
        start = float(seg.start) + absolute_offset
        end = float(seg.end) + absolute_offset
        text = re.sub(r"\s+", " ", seg.text).strip()
        if text:
            segments.append({"start": start, "end": end, "timestamp": fmt_time(start), "text": text})
    return segments, model_name


def transcribe_openai(audio: Path, model: str | None, language: str | None, absolute_offset: float) -> tuple[list[dict], str]:
    key = os.environ.get("OPENAI_API_KEY") or os.environ.get("VOICE_TOOLS_OPENAI_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY or VOICE_TOOLS_OPENAI_KEY is required for OpenAI STT")
    model_name = model or os.environ.get("HERMES_VIDEO_WATCH_STT_MODEL") or "whisper-1"
    fields = {"model": model_name, "response_format": "verbose_json"}
    if language:
        fields["language"] = language
    data = _curl_json_multipart("https://api.openai.com/v1/audio/transcriptions", key, audio, fields)
    return _normalize_stt_segments(data, absolute_offset), model_name


def transcribe_groq(audio: Path, model: str | None, language: str | None, absolute_offset: float) -> tuple[list[dict], str]:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is required for Groq STT")
    model_name = model or os.environ.get("HERMES_VIDEO_WATCH_STT_MODEL") or "whisper-large-v3-turbo"
    fields = {"model": model_name, "response_format": "verbose_json"}
    if language:
        fields["language"] = language
    data = _curl_json_multipart("https://api.groq.com/openai/v1/audio/transcriptions", key, audio, fields)
    return _normalize_stt_segments(data, absolute_offset), model_name


def transcribe_mistral(audio: Path, model: str | None, language: str | None, absolute_offset: float) -> tuple[list[dict], str]:
    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        raise RuntimeError("MISTRAL_API_KEY is required for Mistral STT")
    model_name = model or os.environ.get("HERMES_VIDEO_WATCH_STT_MODEL") or "voxtral-mini-latest"
    fields = {"model": model_name}
    if language:
        fields["language"] = language
    data = _curl_json_multipart("https://api.mistral.ai/v1/audio/transcriptions", key, audio, fields)
    return _normalize_stt_segments(data, absolute_offset), model_name


def transcribe_command(audio: Path, command: str | None, absolute_offset: float) -> tuple[list[dict], str]:
    cmd_template = command or os.environ.get("HERMES_VIDEO_WATCH_STT_COMMAND")
    if not cmd_template:
        raise RuntimeError("--stt-command or HERMES_VIDEO_WATCH_STT_COMMAND is required for command STT")
    if "{audio}" in cmd_template:
        cmd = cmd_template.replace("{audio}", shlex.quote(str(audio)))
    else:
        cmd = f"{cmd_template} {shlex.quote(str(audio))}"
    eprint("[run]", cmd)
    p = subprocess.run(cmd, shell=True, text=True, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout)[-2000:])
    stdout = p.stdout.strip()
    try:
        data = json.loads(stdout)
        segments = _normalize_stt_segments(data, absolute_offset)
    except Exception:
        segments = _normalize_stt_segments(stdout, absolute_offset)
    return segments, "command"


def resolve_stt_provider(provider: str) -> str | None:
    if provider == "none":
        return None
    if provider != "auto":
        return provider
    if os.environ.get("HERMES_VIDEO_WATCH_STT_COMMAND"):
        return "command"
    try:
        import faster_whisper  # noqa: F401
        return "local"
    except Exception:
        pass
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    if os.environ.get("OPENAI_API_KEY") or os.environ.get("VOICE_TOOLS_OPENAI_KEY"):
        return "openai"
    if os.environ.get("MISTRAL_API_KEY"):
        return "mistral"
    return None


def transcribe_audio(audio: Path, provider: str, args, absolute_offset: float) -> tuple[list[dict], str, str]:
    if provider == "local":
        segments, model = transcribe_local(audio, args.stt_model, args.stt_language, absolute_offset)
    elif provider == "groq":
        segments, model = transcribe_groq(audio, args.stt_model, args.stt_language, absolute_offset)
    elif provider == "openai":
        segments, model = transcribe_openai(audio, args.stt_model, args.stt_language, absolute_offset)
    elif provider == "mistral":
        segments, model = transcribe_mistral(audio, args.stt_model, args.stt_language, absolute_offset)
    elif provider == "command":
        segments, model = transcribe_command(audio, args.stt_command, absolute_offset)
    else:
        raise RuntimeError(f"unknown STT provider: {provider}")
    return segments, provider, model


def parse_visual_cues(value: str | None) -> list[str]:
    if not value:
        return DEFAULT_VISUAL_CUES[:]
    cues = [c.strip().lower() for c in re.split(r"[,|]", value) if c.strip()]
    return cues or DEFAULT_VISUAL_CUES[:]


def segment_cues(text: str, cues: list[str]) -> list[str]:
    text_l = text.lower()
    found = []
    for cue in cues:
        pattern = re.escape(cue.lower())
        if re.search(rf"(?<!\w){pattern}(?!\w)", text_l):
            found.append(cue)
    return found


def suggest_ranges_from_transcript(
    segments: list[dict],
    cues: list[str],
    padding: float,
    max_ranges: int,
    duration: float | None = None,
) -> list[dict]:
    windows: list[dict] = []
    for seg in segments:
        matches = segment_cues(str(seg.get("text", "")), cues)
        if not matches:
            continue
        try:
            seg_start = float(seg.get("start") or 0)
        except Exception:
            seg_start = 0.0
        try:
            seg_end = float(seg.get("end")) if seg.get("end") is not None else seg_start + 4.0
        except Exception:
            seg_end = seg_start + 4.0
        start = max(0.0, seg_start - padding)
        end = max(start + 1.0, seg_end + padding)
        if duration and duration > 0:
            end = min(duration, end)
        windows.append({
            "start": start,
            "end": end,
            "score": len(matches),
            "cues": sorted(set(matches)),
            "segments": [{
                "start": seg_start,
                "end": seg_end,
                "timestamp": fmt_time(seg_start),
                "text": seg.get("text", ""),
                "cues": sorted(set(matches)),
            }],
        })
    if not windows:
        return []
    windows.sort(key=lambda r: (r["start"], r["end"]))
    merged: list[dict] = []
    for win in windows:
        if merged and win["start"] <= merged[-1]["end"]:
            cur = merged[-1]
            cur["end"] = max(cur["end"], win["end"])
            cur["score"] += win["score"]
            cur["cues"] = sorted(set(cur["cues"]) | set(win["cues"]))
            cur["segments"].extend(win["segments"])
        else:
            merged.append(win)
    top = sorted(merged, key=lambda r: (-r["score"], r["start"]))[:max(1, max_ranges)]
    top.sort(key=lambda r: r["start"])
    for idx, item in enumerate(top, 1):
        item["index"] = idx
        item["start"] = round(item["start"], 3)
        item["end"] = round(item["end"], 3)
        item["start_timestamp"] = fmt_time(item["start"])
        item["end_timestamp"] = fmt_time(item["end"])
        item["reason"] = f"Transcript visual cues: {', '.join(item['cues'])}"
    return top


def write_suggested_ranges(out_dir: Path, source: str, transcript_segments: list[dict], transcript_source: str, cues: list[str], args, duration: float | None = None) -> Path:
    ranges = suggest_ranges_from_transcript(
        transcript_segments,
        cues,
        float(args.range_padding),
        int(args.max_ranges),
        duration,
    )
    payload = {
        "visual_coverage_mode": "suggested_ranges",
        "source": source,
        "transcript_source": transcript_source,
        "transcript_segments": len(transcript_segments),
        "cue_phrases": cues,
        "range_padding_seconds": float(args.range_padding),
        "max_ranges": int(args.max_ranges),
        "ranges": ranges,
        "note": "Ranges are transcript-guided suggestions for focused visual extraction; inspect resulting frames before making visual claims.",
    }
    path = out_dir / "suggested_ranges.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if transcript_segments:
        (out_dir / "transcript.txt").write_text("\n".join(f"[{s['timestamp']}] {s['text']}" for s in transcript_segments), encoding="utf-8")
    return path


def load_ranges(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        ranges = data.get("ranges") or data.get("suggested_ranges") or []
    elif isinstance(data, list):
        ranges = data
    else:
        raise SystemExit(f"Unsupported ranges JSON shape: {path}")
    parsed = []
    for idx, item in enumerate(ranges, 1):
        if not isinstance(item, dict):
            continue
        start = parse_time(str(item.get("start", item.get("start_timestamp", ""))))
        end = parse_time(str(item.get("end", item.get("end_timestamp", ""))))
        if start is None or end is None or end <= start:
            eprint(f"[warn] skipping invalid range #{idx}: {item}")
            continue
        item = dict(item)
        item["start"] = start
        item["end"] = end
        item.setdefault("index", idx)
        parsed.append(item)
    return parsed


def _annotate_frame(path: Path, label: str) -> None:
    """Burn a small index/timestamp label into a frame for contact-sheet triage.

    Prefer ImageMagick when available. Some ffmpeg builds (including the one on
    this machine) omit drawtext, so annotation must be best-effort.
    """
    magick = shutil.which("magick") or shutil.which("convert")
    if not magick:
        return
    tmp = path.with_suffix(".annotated.jpg")
    p = run([
        magick, str(path),
        "-gravity", "SouthWest",
        "-pointsize", "28",
        "-fill", "white",
        "-undercolor", "#00000099",
        "-annotate", "+12+12", label,
        str(tmp),
    ])
    if p.returncode == 0 and tmp.exists():
        tmp.replace(path)
    else:
        # Annotation is optional. Some machines have ImageMagick without usable fonts.
        # Keep raw frames and rely on timestamped filenames + manifest.json.
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


def extract_frames(video: Path, out_dir: Path, fps: float, resolution: int, max_frames: int, absolute_offset: float) -> list[dict]:
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    pattern = frames_dir / "frame_%04d.jpg"
    vf = f"fps={fps},scale={resolution}:-2"
    cmd = ["ffmpeg", "-y", "-i", str(video), "-vf", vf, "-frames:v", str(max_frames), "-q:v", "2", str(pattern)]
    p = run(cmd)
    if p.returncode != 0:
        raise SystemExit(f"ffmpeg frame extraction failed:\n{p.stderr[-2000:]}")
    files = sorted(frames_dir.glob("frame_*.jpg"))
    frames = []
    for idx, path in enumerate(files):
        ts = absolute_offset + (idx / fps if fps > 0 else 0)
        new_name = f"{idx+1:03d}_{safe_time_for_name(ts)}.jpg"
        new_path = frames_dir / new_name
        path.rename(new_path)
        label = f"{idx+1:03d}  {fmt_time(ts)}"
        _annotate_frame(new_path, label)
        frames.append({"index": idx + 1, "timestamp_seconds": round(ts, 3), "timestamp": fmt_time(ts), "path": str(new_path)})
    return frames


def make_contact_sheet(frames: list[dict], out_dir: Path) -> Path | None:
    if not frames:
        return None
    cols = min(5, max(1, math.ceil(math.sqrt(len(frames)))))
    rows = math.ceil(len(frames) / cols)
    sheet = out_dir / "contact_sheet.jpg"
    inputs = [f["path"] for f in frames]
    # ffmpeg tile requires same dimensions; frames already same scale.
    list_file = out_dir / "frames_for_contact_sheet.txt"
    list_file.write_text("".join(f"file '{Path(p).as_posix()}'\n" for p in inputs))
    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
        "-vf", f"tile={cols}x{rows}:padding=6:margin=6", "-frames:v", "1", str(sheet)
    ]
    p = run(cmd)
    if p.returncode != 0:
        eprint("[warn] contact sheet failed:", p.stderr[-1000:])
        return None
    return sheet if sheet.exists() else None


def write_report(out_dir: Path, source: str, video: Path, frames: list[dict], transcript_segments: list[dict], subtitle_path: Path | None, contact_sheet: Path | None, meta: dict, args) -> None:
    transcript_txt = out_dir / "transcript.txt"
    if transcript_segments:
        transcript_txt.write_text("\n".join(f"[{s['timestamp']}] {s['text']}" for s in transcript_segments), encoding="utf-8")

    transcript_source = meta.get("transcript_source", "none")
    stt_provider = meta.get("stt_provider")
    stt_model = meta.get("stt_model")
    summary = {
        "source": source,
        "video_path": str(video),
        "frame_count": len(frames),
        "transcript_segments": len(transcript_segments),
        "transcript_source": transcript_source,
        "stt_provider": stt_provider,
        "stt_model": stt_model,
        "contact_sheet": str(contact_sheet) if contact_sheet else None,
        "start": args.start,
        "end": args.end,
        "resolution": args.resolution,
        "max_frames": args.max_frames,
        "visual_coverage_mode": meta.get("visual_coverage_mode", "single_range_or_scan"),
    }
    manifest = {
        "summary": summary,
        "metadata": meta,
        "frames": frames,
        "transcript_path": str(transcript_txt) if transcript_segments else None,
        "subtitle_path": str(subtitle_path) if subtitle_path else None,
        "transcript_source": transcript_source,
        "stt_provider": stt_provider,
        "stt_model": stt_model,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    lines = [
        "# Hermes Video Watch Report", "",
        f"- **Source:** {source}",
        f"- **Working directory:** `{out_dir}`",
        f"- **Video file:** `{video}`",
        f"- **Frames:** {len(frames)}",
        f"- **Contact sheet:** `{contact_sheet}`" if contact_sheet else "- **Contact sheet:** not created",
        f"- **Transcript:** {len(transcript_segments)} segments ({transcript_source})" if transcript_segments else "- **Transcript:** none available",
        f"- **STT provider:** {stt_provider or 'not used'}" + (f" ({stt_model})" if stt_model else ""),
        f"- **Resolution:** {args.resolution}px wide",
        f"- **Range:** {args.start or 'start'} → {args.end or 'end'}",
        f"- **Visual coverage mode:** {meta.get('visual_coverage_mode', 'single_range_or_scan')}",
        "", "## Next Hermes Steps", "",
        "1. Use `vision_analyze` on the contact sheet to choose important frames.",
        "2. Use `vision_analyze` on selected individual frames for detailed visual interpretation.",
        "3. If creating a document, copy selected frames into a stable `assets/` folder and insert with timestamped captions.",
        "", "## Frames", "",
    ]
    for f in frames:
        lines.append(f"- `{f['path']}` — t={f['timestamp']}")
    lines += ["", "## Transcript Excerpt", ""]
    if transcript_segments:
        for s in transcript_segments[:200]:
            lines.append(f"[{s['timestamp']}] {s['text']}")
        if len(transcript_segments) > 200:
            lines.append(f"\n... {len(transcript_segments)-200} more segments in transcript.txt")
    else:
        lines.append("No transcript/captions were available. Analyze frames only or provide captions/Whisper workflow separately.")
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def process_single(args, out_dir: Path, start: float | None, end: float | None, visual_coverage_mode: str = "single_range_or_scan") -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    eprint(f"[info] out_dir={out_dir}")

    subtitle_path = None if args.no_subs else download_subtitles(args.source, out_dir)
    caption_segments = parse_vtt(subtitle_path, start, end) if subtitle_path else []
    transcript_segments = caption_segments
    transcript_source = "captions" if caption_segments else "none"
    stt_provider_used = None
    stt_model_used = None
    stt_error = None

    video = download_video(args.source, out_dir, start, end, args.format)
    if not is_url(args.source) and (start is not None or end is not None):
        video = clip_local_if_needed(video, out_dir, start, end)

    should_try_stt = args.prefer_stt or not caption_segments
    selected_stt_provider = resolve_stt_provider(args.stt_provider)
    if should_try_stt and selected_stt_provider:
        try:
            audio = extract_audio(video, out_dir, args.audio_format)
            stt_segments, stt_provider_used, stt_model_used = transcribe_audio(audio, selected_stt_provider, args, start or 0)
            if stt_segments:
                transcript_segments = stt_segments
                transcript_source = "stt"
            elif not caption_segments:
                transcript_source = "none"
        except Exception as exc:
            stt_error = str(exc)
            eprint(f"[warn] STT failed with provider {selected_stt_provider}: {stt_error}")
            if caption_segments:
                transcript_segments = caption_segments
                transcript_source = "captions"
    elif should_try_stt and args.stt_provider != "none":
        eprint("[info] no STT provider configured; continuing without STT")

    duration = ffprobe_duration(video)
    stream = ffprobe_stream(video)
    focused = start is not None or end is not None
    effective_duration = duration if duration > 0 else ((end or 0) - (start or 0) if focused else 0)
    fps = min(2.0, args.fps) if args.fps else auto_fps(effective_duration, args.max_frames, focused)
    absolute_offset = start or 0
    frames = extract_frames(video, out_dir, fps, args.resolution, args.max_frames, absolute_offset)
    contact_sheet = make_contact_sheet(frames, out_dir)

    meta = {
        "clip_duration_seconds": duration,
        "stream": stream,
        "focused": focused,
        "transcript_source": transcript_source,
        "stt_provider": stt_provider_used,
        "stt_model": stt_model_used,
        "stt_requested_provider": args.stt_provider,
        "stt_error": stt_error,
        "visual_coverage_mode": visual_coverage_mode,
    }
    write_report(out_dir, args.source, video, frames, transcript_segments, subtitle_path, contact_sheet, meta, args)
    return {
        "out_dir": str(out_dir),
        "report": str(out_dir / "report.md"),
        "manifest": str(out_dir / "manifest.json"),
        "contact_sheet": str(contact_sheet) if contact_sheet else None,
        "frames_dir": str(out_dir / "frames"),
        "frames": len(frames),
        "transcript_segments": len(transcript_segments),
        "transcript_source": transcript_source,
        "stt_provider": stt_provider_used,
        "visual_coverage_mode": visual_coverage_mode,
        "start": start,
        "end": end,
    }


def acquire_transcript_for_suggestions(args, out_dir: Path, start: float | None, end: float | None) -> tuple[list[dict], str, Path | None, Path | None, float]:
    subtitle_path = None if args.no_subs else download_subtitles(args.source, out_dir)
    caption_segments = parse_vtt(subtitle_path, start, end) if subtitle_path else []
    transcript_segments = caption_segments
    transcript_source = "captions" if caption_segments else "none"
    video = download_video(args.source, out_dir, start, end, args.format)
    if not is_url(args.source) and (start is not None or end is not None):
        video = clip_local_if_needed(video, out_dir, start, end)
    should_try_stt = args.prefer_stt or not caption_segments
    selected_stt_provider = resolve_stt_provider(args.stt_provider)
    if should_try_stt and selected_stt_provider:
        try:
            audio = extract_audio(video, out_dir, args.audio_format)
            stt_segments, _, _ = transcribe_audio(audio, selected_stt_provider, args, start or 0)
            if stt_segments:
                transcript_segments = stt_segments
                transcript_source = "stt"
        except Exception as exc:
            eprint(f"[warn] STT failed with provider {selected_stt_provider}: {exc}")
            if caption_segments:
                transcript_segments = caption_segments
                transcript_source = "captions"
    elif should_try_stt and args.stt_provider != "none":
        eprint("[info] no STT provider configured; continuing without STT")
    return transcript_segments, transcript_source, subtitle_path, video, ffprobe_duration(video)


def run_multi_range(args, out_dir: Path, ranges_path: Path) -> dict:
    ranges = load_ranges(ranges_path)[: max(1, int(args.max_ranges))]
    if not ranges:
        raise SystemExit(f"No valid ranges found in {ranges_path}")
    results = []
    ranges_root = out_dir / "ranges"
    for idx, item in enumerate(ranges, 1):
        start = float(item["start"])
        end = float(item["end"])
        subdir = ranges_root / f"{idx:03d}_{safe_time_for_name(start)}-{safe_time_for_name(end)}"
        child = argparse.Namespace(**vars(args))
        child.start = time_arg(start)
        child.end = time_arg(end)
        result = process_single(child, subdir, start, end, "multi_range_focused")
        result["range"] = item
        results.append(result)
    manifest = {
        "visual_coverage_mode": "multi_range_focused",
        "source": args.source,
        "ranges_path": str(ranges_path),
        "out_dir": str(out_dir),
        "max_frames_per_range": args.max_frames,
        "range_count": len(results),
        "results": results,
        "note": "Multi-range focused extraction covers only the listed ranges; inspect frames/contact sheets before making visual claims.",
    }
    path = out_dir / "multi_range_manifest.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description="Hermes-native video analysis artifact extractor")
    ap.add_argument("source", help="Video URL or local video path")
    ap.add_argument("--start", help="Start time SS, MM:SS, or HH:MM:SS")
    ap.add_argument("--end", help="End time SS, MM:SS, or HH:MM:SS")
    ap.add_argument("--max-frames", type=int, default=40, help="Maximum frames to extract (default 40, capped 100)")
    ap.add_argument("--resolution", type=int, default=768, help="Frame width in pixels (default 768)")
    ap.add_argument("--fps", type=float, help="Override frame extraction FPS (capped at 2)")
    ap.add_argument("--out-dir", help="Output directory; default temp dir")
    ap.add_argument("--format", default="bv*[height<=720]+ba/b[height<=720]/best[height<=720]/best", help="yt-dlp format selector")
    ap.add_argument("--keep-video", action="store_true", help="Keep downloaded video/clip; default always keeps for now because artifacts reference it")
    ap.add_argument("--no-subs", action="store_true", help="Skip subtitle/caption fetch")
    ap.add_argument("--stt-provider", choices=["none", "auto", "local", "groq", "openai", "mistral", "command"], default=os.environ.get("HERMES_VIDEO_WATCH_STT_PROVIDER", "auto"), help="Optional speech-to-text fallback provider (default: env HERMES_VIDEO_WATCH_STT_PROVIDER or auto)")
    ap.add_argument("--prefer-stt", action="store_true", help="Prefer STT over captions when both are available")
    ap.add_argument("--stt-model", default=os.environ.get("HERMES_VIDEO_WATCH_STT_MODEL"), help="STT model override (provider-specific)")
    ap.add_argument("--stt-language", help="Optional language hint such as en")
    ap.add_argument("--stt-command", default=os.environ.get("HERMES_VIDEO_WATCH_STT_COMMAND"), help="Command STT provider; use {audio} as the audio path placeholder")
    ap.add_argument("--audio-format", choices=["mp3", "wav"], default="mp3", help="Extracted audio format for STT (default: mp3)")
    ap.add_argument("--suggest-ranges", action="store_true", help="Write suggested_ranges.json from transcript/STT visual cue phrases and exit")
    ap.add_argument("--ranges", help="JSON ranges file for multi-range focused extraction (for example suggested_ranges.json)")
    ap.add_argument("--range-padding", type=float, default=20.0, help="Seconds to pad around transcript visual cue hits when suggesting ranges (default 20)")
    ap.add_argument("--max-ranges", type=int, default=8, help="Maximum suggested/extracted ranges for long-video deep mode (default 8)")
    ap.add_argument("--visual-cues", help="Comma-separated visual cue phrases for --suggest-ranges")
    args = ap.parse_args()

    require_binary("ffmpeg")
    require_binary("ffprobe")
    args.max_frames = max(1, min(args.max_frames, 100))
    start = parse_time(args.start)
    end = parse_time(args.end)
    if start is not None and end is not None and end <= start:
        raise SystemExit("--end must be greater than --start")

    out_dir = Path(args.out_dir).expanduser().resolve() if args.out_dir else Path(tempfile.mkdtemp(prefix="hermes-video-watch-"))
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.suggest_ranges:
        cues = parse_visual_cues(args.visual_cues)
        transcript_segments, transcript_source, _subtitle_path, _video, duration = acquire_transcript_for_suggestions(args, out_dir, start, end)
        path = write_suggested_ranges(out_dir, args.source, transcript_segments, transcript_source, cues, args, duration)
        print(f"suggested_ranges: {path}")
        print("visual_coverage_mode: suggested_ranges")
        print(f"ranges: {len(json.loads(path.read_text(encoding='utf-8')).get('ranges', []))}")
        print(f"transcript_segments: {len(transcript_segments)}")
        print(f"transcript_source: {transcript_source}")
        return 0

    if args.ranges:
        manifest = run_multi_range(args, out_dir, Path(args.ranges).expanduser().resolve())
        print(f"multi_range_manifest: {out_dir / 'multi_range_manifest.json'}")
        print("visual_coverage_mode: multi_range_focused")
        print(f"ranges: {manifest['range_count']}")
        for result in manifest["results"]:
            print(f"range_report: {result['report']}")
        return 0

    result = process_single(args, out_dir, start, end, "single_range_or_scan")
    print(f"report: {result['report']}")
    print(f"manifest: {result['manifest']}")
    if result.get("contact_sheet"):
        print(f"contact_sheet: {result['contact_sheet']}")
    print(f"frames_dir: {result['frames_dir']}")
    print(f"frames: {result['frames']}")
    print(f"transcript_segments: {result['transcript_segments']}")
    print(f"transcript_source: {result['transcript_source']}")
    print(f"visual_coverage_mode: {result['visual_coverage_mode']}")
    if result.get("stt_provider"):
        print(f"stt_provider: {result['stt_provider']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
