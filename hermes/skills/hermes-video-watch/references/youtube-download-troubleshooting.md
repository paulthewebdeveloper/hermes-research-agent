# YouTube Download Troubleshooting

`yt-dlp` and video platforms change frequently. Treat download failures as expected operational issues, not as analysis failures.

## Preferred downloader invocation

The helper checks for `uvx` first and runs:

```bash
uvx --from yt-dlp yt-dlp
```

If `uvx` is unavailable, it falls back to `yt-dlp` on `PATH`.

You can override the downloader command with:

```bash
HERMES_VIDEO_WATCH_YTDLP="/custom/path/to/yt-dlp" python3 scripts/hermes_video_watch.py <video>
```

## Common fixes

### Use a focused range

For long videos, try extracting only the timestamp range needed:

```bash
python3 scripts/hermes_video_watch.py "$URL" \
  --start 00:02:40 \
  --end 00:08:10 \
  --max-frames 20 \
  --resolution 768
```

### Use a lower-resolution format selector

```bash
python3 scripts/hermes_video_watch.py "$URL" \
  --format 'b[height<=720]/best[height<=720]/best'
```

### If captions fail

Run with `--no-subs` and proceed visually:

```bash
python3 scripts/hermes_video_watch.py "$URL" --no-subs
```

### If authentication is required

Do not attempt to bypass access controls. Ask the user for a local authorized export or a publicly accessible link.

## Reporting limitations

When captions or downloads are unavailable, say exactly what worked and what did not. Example:

```text
Captions were unavailable, so spoken-word accuracy is limited. I extracted frames and based the visual analysis on the contact sheet and selected screenshots.
```
