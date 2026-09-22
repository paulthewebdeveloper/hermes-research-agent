---
name: youtube-video
description: Use when the user asks what to shoot next, hands over an OBS recording folder, or says edit, cut, tighten, thumbnail, publish or post a YouTube video. Covers the whole pipeline - picking the topic from live data, the OBS Split scene that records the finished layout, preflight, take selection with Jev, the Resolve timeline, pause and breath removal, thumbnails, A/B test, end screen, quiz, pinned comment.
---

# YouTube video pipeline

One topic in, one published video out. Two scripts do the mechanical parts; this file is the order
and the judgement:

- `scripts/trends.py` — what to shoot
- `scripts/videokit.py` — everything after the recording exists. Run with no arguments for usage.

A recording folder holds OBS's three files: `MAIN.mov`, `CAM.mp4`, `SCREEN.mp4`. **Only MAIN
carries the mic.** CAM and SCREEN are silent and lag MAIN by a frame or two.

Needs: `ffmpeg`, `whisper-cli` (whisper.cpp) with a model at `$WHISPER_MODEL`, Python 3.10+ with
`numpy pillow opencv-python`, DaVinci Resolve (free). `takes` needs `TYPESAFE_API_KEY`
(console.typesafe.ai) — everything else runs offline.

## 0. Pick the topic (live data, not memory)

```
trends.py                          # this week's uploads across the niche queries, by views
trends.py "claude code obsidian"   # test a specific angle
trends.py --all-time "<query>"     # does anyone own this query outright?
```
Edit `DEFAULT` in `trends.py` for your niche. Read the output for two things:

- **views / subs.** Over 1x means the video travelled past the channel's own audience. A big ratio
  on a tiny channel is a topic anyone can win.
- **An empty intersection.** Two topics that are each huge, and whose combined query returns only
  generic results or sub-2k videos. That gap, plus something you already run, is the pick.

Easy-to-shoot beats popular. The artifact must already exist on your machine: you screen-record
the real thing. Never pick a topic that needs a build first.

## 1. Before you record

- Record in 16:9. **The Split scene only lines up in 16:9** — the frame is 1920x1080.
- **Two OBS scenes: `Split` and `Face`.** Record on **Split** and do not switch. Split bakes the
  finished look into MAIN: dark halftone background, screen in the left panel (1300x731 at 60,174),
  camera in the right (450x731 at 1410,174), rounded corners. `Face` is the full-frame talking
  head, for an intro or outro only.
- Split's layers, bottom to top: Screen, Video Capture Device, **Split frame**. The frame is
  `layout/split-frame.png`, an image with two transparent windows — it is both the background and
  the corner rounding. `layout/make_frame.py` rebuilds it (`dots` default, `grid` for a blueprint
  look; pitch, angle, brightness and the label are constants at the top). Close OBS before
  replacing the PNG — OBS caches it.
- Add a Source Record filter to both the screen and the camera source so OBS also writes
  `CAM.mp4` and `SCREEN.mp4` full-frame; any shot can then be reframed later. It can fail silently:
  the 15-second test below is what catches it.
- 15-second test, then `videokit.py check <folder>`: all three files present, CAM lag measured,
  no clipping. Mic peak near 0 dB means clipping — lower the gain.
- Record an outro and name the next video out loud. End screens alone get no clicks on a small
  channel.

## 2. Preflight and transcript

```
videokit.py check  <folder>      # lag, which scene MAIN shows, clipping
videokit.py script <folder>      # edit/transcript.txt
```

## 3. Choose the takes (Jev does the judging)

You restart sentences many times: keep the **last complete take** of each thought, in spoken
order. Draft it with the tool, then correct it:

```
videokit.py takes <folder>       # edit/transcript.txt -> DRAFT edit/cutlist.md
```

It groups the transcript into thoughts by asking Jev, for each line, whether it repeats the opening
words of one of the six lines before it (a retake); every attempt at a thought is then judged in one
call for whether it finishes its sentence, and the **last finished attempt** is the row. Every
attempt and its probability is listed under the table, so you read the attempts instead of the
transcript. Without a key it says so and exits — pick the takes by hand.

What it leaves to you: `screen` (a visual judgement), the shot names, splitting a long take, and
the `?` rows where no attempt scored as finished. A retake that starts mid-line, or more than six
lines after the thought began, is missed, so two attempts land in one row. Every row is a guess
until `piece` proves it.

`edit/cutlist.md`:

```
| # | shot | in | out | screen |
|---|---|---|---|---|
| 1 | hook + intro | 0.00 | 19.30 | none |
| 2 | two harnesses | 148.10 | 197.50 | auto |
```

`screen`: `auto` finds the board or window and fits it 16:9 · `none` face only · `full` whole
screen · `x,y,w,h` in 3840x2160 pixels.

**Verify every cut point before trusting it.** Whisper word times drift up to a second.
```
videokit.py gaps  <folder> 19:22            # where the real silence is
videokit.py piece <folder> 14.7:20.66       # what that exact span says on its own
```
A take is right when `piece` returns exactly the sentence, no leftover word from the previous
attempt. Never use a disfluency prompt with Whisper: it invents fillers.

## 4. Build the timeline

**Recorded on Split: the layout is already in MAIN. Cut MAIN and skip `layers`.** Rebuild from
CAM + SCREEN only when a shot needs reframing.

```
videokit.py layers <folder>      # edit/layers.xml
```
Resolve: File > Import > Timeline > `layers.xml`. Tracks: V1 background, V2 screen, V3 camera,
V4 rounded frame, A1 levelled mic. Every clip carries its own crop, so you can reframe one clip in
the Inspector. Only FCP7 XML (`.xml`) carries position, scale and crop into free Resolve; FCPXML
and OTIO drop them.

## 5. Edit, then tighten

Touch up the timeline in Resolve, then File > Export > Timeline as `.xml`. Keep that file as the
draft.
```
videokit.py tighten <export.xml> --thr -26 --demo-from <seconds>
```
`--thr -26` dB cuts breaths as well as silence (a quiet room sits about -36 dB; breaths -30 to
-22). `--demo-from` is where the screen demo starts: from there only gaps over 0.6 s are trimmed so
typing and waiting still read. It prints a word-level diff of before and after: spelling swaps
are noise, a missing content word means that cut is wrong. Import `<export>-tight.xml` as a new
timeline. Never overwrite the one you saved.

## 6. Thumbnails and titles

Generate them with an image model from **your own face frame**, never from another creator's
thumbnail (the model reproduces their face). The recipe that works with the Codex CLI:

1. `thumbs/face.png`: one frame from CAM.mp4, eye contact, mid-word
   (`ffmpeg -ss <t> -i CAM.mp4 -frames:v 1 face.png`; grab six, pick by eye).
2. One prompt file per thumbnail from `scripts/thumb-preamble.txt`: fill in who you are and your
   channel look once, then ONE composition paragraph per image. Prose, never JSON.
3. One image per call, in parallel. `-i` is variadic, so the prompt goes after `--`:
   ```
   codex exec --skip-git-repo-check -i face.png -i logo.png -- "$(cat _p-A.txt)" > _codex-A.log 2>&1 &
   ```
4. Zoom every result to 100% and read the logos and every letter. Fix one defect with an edit
   prompt: attach the PNG, "change ONE thing only", same closing line.
5. `videokit.py thumbs thumbs/` for the ≤2 MB JPGs YouTube accepts.

Titles: foreshadow a result, overpromise a little, and the video must pay it off. Three title +
thumbnail pairs for the A/B test, **paired so the thumbnail text never repeats its title.**

`titles.py pool.json --candidates c.txt` scores title shapes against a pool of niche videos
(views / subs), if you keep one.

## 7. Publish

1. Upload. Title, description with chapters timed from the final export.
2. A/B test > Title and thumbnail > the three pairs.
3. End screen: one video plus subscribe, where you point in the outro. Cards are hidden while an
   end screen shows.
4. A quiz at the end of the densest section. It cannot be edited once saved.
5. Verify from outside: `yt-dlp --skip-download -J <url>` — availability, 1080 height, chapters.
6. Pinned comment with the repo link. No file names ending in `.md` in a comment: YouTube links
   them to a .md domain.

Before publishing, transcribe the final export and list every promise the video makes ("the repo
does X", "link below"). Each one must already be true.

## What to say no to

- Rendering a baked video when you want to keep editing: keep the timeline.
- Overwriting anything you saved. New timeline, new file, every time.
- Guessing a number for the video (cost, time, model). Read it off the machine.
- A topic that needs something built first. Shoot what already runs.
