#!/usr/bin/env python3
"""videokit: the repeatable parts of a one-person YouTube edit pipeline.

A recording folder holds OBS's three files: MAIN.mov (mic audio), CAM.mp4, SCREEN.mp4.

  videokit.py check   <folder>                 files, durations, cam/screen lag vs MAIN, does MAIN ever leave the face
  videokit.py script  <folder>                 transcript with timestamps -> <folder>/edit/transcript.txt
  videokit.py piece   <folder> a:b [a:b ...]   transcribe candidate takes on their own (proves a cut is clean)
  videokit.py gaps    <folder> a:b [a:b ...]   silences near a cut point
  videokit.py takes   <folder>                 edit/transcript.txt -> DRAFT edit/cutlist.md (last complete take of each thought; needs TYPESAFE_API_KEY)
  videokit.py layers  <folder>                 edit/cutlist.md -> edit/layers.xml for Resolve (bg, screen, cam, frame, mic)
  videokit.py tighten <resolve-export.xml> [--thr -26] [--demo-from SECONDS] [--cuts cuts.json]   cut pauses and breaths on every track
  videokit.py thumbs  <dir>                    any images -> 1280x720 JPGs under 2 MB in <dir>/youtube/

Needs ffmpeg, whisper-cli, numpy, pillow, opencv-python. `takes` calls TypeSafe's Jev (api.typesafe.ai) with the key in TYPESAFE_API_KEY. Import XML in Resolve: File > Import > Timeline.
"""
import copy, glob, json, os, re, subprocess, sys, urllib.parse, urllib.request, wave
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

MODEL = os.environ.get("WHISPER_MODEL", os.path.expanduser("~/ggml-large-v3-turbo.bin"))
FPS = 30
PW, PH, PX, PY = 1300, 731, 60, 174     # screen panel, 16:9
CW, CH, CX, CY = 450, 731, 1410, 174    # face panel
FACE_W = 665                            # 1080-tall camera crop with the face panel's shape


def sh(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, **kw)
    if r.returncode:
        sys.exit(f"failed: {' '.join(map(str, cmd))[:200]}\n{r.stderr[-800:]}")
    return r.stdout


def paths(folder):
    folder = os.path.abspath(os.path.expanduser(folder))
    edit = os.path.join(folder, "edit"); os.makedirs(edit, exist_ok=True)
    return folder, edit, {k: os.path.join(folder, v) for k, v in (("main", "MAIN.mov"), ("cam", "CAM.mp4"), ("scr", "SCREEN.mp4"))}


def wav16(src, dst):
    if not os.path.exists(dst):
        sh(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", dst])
    return dst


def envelope_db(path):
    with wave.open(path) as w:
        sr, ch = w.getframerate(), w.getnchannels()
        a = np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, ch)[:, 0].astype(float)
    hop = sr // 100
    return 20 * np.log10(np.abs(a[: len(a) // hop * hop]).reshape(-1, hop).max(1) / 32768 + 1e-6)


def quiet_runs(db, thr, min_len):
    q, out, i = db < thr, [], 0
    while i < len(q):
        if q[i]:
            j = i
            while j < len(q) and q[j]: j += 1
            if (j - i) / 100 >= min_len: out.append((i / 100, j / 100))
            i = j
        else: i += 1
    return out


def whisper(wav, base, fmt="-otxt"):
    subprocess.run(["whisper-cli", "-m", MODEL, "-f", wav, "-l", "en", fmt, "-of", base, "-np"], capture_output=True)


def gray(path, t, w, h):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.2f}", "-i", path, "-frames:v", "1", "-vf", f"scale={w}:{h}", "-f", "rawvideo", "-pix_fmt", "gray", "-"], capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(h, w).copy() if len(raw) == w * h else None


# ---------- check ----------
def motion(path, ss, secs=30, crop=""):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-ss", str(ss), "-t", str(secs), "-i", path, "-vf", f"fps=30,{crop}scale=48:27,format=gray", "-f", "rawvideo", "-"], capture_output=True).stdout
    a = np.frombuffer(raw, np.uint8).reshape(-1, 48 * 27).astype(float)
    return np.abs(np.diff(a, axis=0)).mean(1)


def cmd_check(folder):
    folder, edit, p = paths(folder)
    for k, f in p.items():
        if not os.path.exists(f): sys.exit(f"missing {f}")
        print(k, sh(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=width,height", "-of", "csv=p=0", f]).decode().split())
    dur = float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", p["main"]]))
    c = motion(p["cam"], dur / 2); best = (0, -1, "")
    for where, crop in (("full frame", ""), ("face bubble, bottom left", "crop=677:381:0:699,"),
                        ("Split scene, right panel", "crop=450:731:1410:174,")):   # MAIN may be Face, Screen + Face or Split
        m = motion(p["main"], dur / 2, crop=crop); n = min(len(m), len(c))
        a, b = (m[:n] - m[:n].mean()) / (m[:n].std() + 1e-9), (c[:n] - c[:n].mean()) / (c[:n].std() + 1e-9)
        sc = {k: np.dot(a[max(k, 0):n + min(k, 0)], b[max(-k, 0):n - max(k, 0)]) / (n - abs(k)) for k in range(-12, 13)}
        k = max(sc, key=sc.get)
        if sc[k] > best[1]: best = (k, sc[k], where)
    lag = best[0]
    print(f"CAM lags MAIN by {lag} frame(s), correlation {best[1]:.2f}, measured on the {best[2]}" + ("" if best[1] > 0.8 else "  (weak match: assume 2 frames)"))
    if best[1] <= 0.8: lag = 2
    same = sum(1 for t in np.linspace(5, dur - 5, 40) if (a := gray(p['main'], t, 64, 36)) is not None and (b := gray(p['cam'], t, 64, 36)) is not None and np.abs(a.astype(float) - b).mean() < 12)
    print(f"MAIN matches CAM in {same}/40 samples" + ("  -> MAIN NEVER SWITCHED SCENES: edit from CAM + SCREEN" if same >= 38 else ""))
    peak = envelope_db(wav16(p["main"], f"{edit}/_main16.wav")).max()
    print(f"mic peak {peak:.1f} dB" + ("  (clipping likely)" if peak > -0.2 else ""))
    json.dump({"lag": int(lag)}, open(f"{edit}/check.json", "w"))


# ---------- transcript helpers ----------
def cmd_script(folder):
    folder, edit, p = paths(folder)
    wav = wav16(p["main"], f"{edit}/_main16.wav"); whisper(wav, f"{edit}/_t", "-ojf")
    d = json.load(open(f"{edit}/_t.json"))
    lines = [f"[{s['offsets']['from'] / 1000:7.1f}] {s['text'].strip()}" for s in d["transcription"]]
    open(f"{edit}/transcript.txt", "w").write("\n".join(lines)); print("\n".join(lines))


def cmd_piece(folder, spans):
    folder, edit, p = paths(folder); wav = wav16(p["main"], f"{edit}/_main16.wav")
    for s in spans:
        a, b = map(float, s.split(":"))
        sh(["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-t", str(b - a), "-i", wav, "-af", "apad=pad_dur=0.6", f"{edit}/_p.wav"])
        whisper(f"{edit}/_p.wav", f"{edit}/_p"); print(f"{s:>18} -> {open(f'{edit}/_p.txt').read().strip()}")


def cmd_gaps(folder, spans):
    folder, edit, p = paths(folder); db = envelope_db(wav16(p["main"], f"{edit}/_main16.wav")); thr = np.percentile(db, 60) - 12
    for s in spans:
        a, b = map(float, s.split(":"))
        print(s, "quiet:", ", ".join(f"{a + x:.2f}-{a + y:.2f}" for x, y in quiet_runs(db[int(a * 100):int(b * 100)], thr, 0.08)))


# ---------- layers ----------
def fit169(x, y, w, h, top=150):
    cx, cy = x + w / 2, y + h / 2
    w = max(w, h * 16 / 9); h = w * 9 / 16
    if h > 2160 - top: h = 2160 - top; w = h * 16 / 9
    if w > 3840: w = 3840; h = w * 9 / 16
    return int(min(max(cx - w / 2, 0), 3840 - w)), int(min(max(cy - h / 2, top), 2160 - h)), int(w) // 2 * 2, int(h) // 2 * 2


def screen_crop(scr, t, mode):
    """mode: none | full | auto | x,y,w,h.  auto = biggest bright region (an Excalidraw board, a window), padded, 16:9."""
    if mode == "none": return None
    if mode == "full": return (0, 0, 3840, 2160)
    if "," in mode: return tuple(int(v) for v in mode.split(","))
    import cv2
    g = gray(scr, t, 1920, 1080)
    if g is None or g.mean() < 6: return None                         # black screen: face only
    g[:80] = 0; g[1040:] = 0
    m = cv2.dilate((g > 55).astype(np.uint8), np.ones((5, 5), np.uint8))
    cs, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = max((cv2.boundingRect(c) for c in cs), key=lambda r: r[2] * r[3], default=None)
    if not best or best[2] * best[3] < 0.15 * 1920 * 1080: return (0, 0, 3840, 2160)
    x, y, w, h = [v * 2 for v in best]
    return fit169(x - w * 0.025, y - h * 0.03, w * 1.05, h * 1.06)


def face_x(cam, t):
    import cv2
    g = gray(cam, t, 960, 540)
    if g is None: return None
    f = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml").detectMultiScale(g, 1.1, 5, minSize=(120, 120))
    return (max(f, key=lambda r: r[2] * r[3])[0] + max(f, key=lambda r: r[2] * r[3])[2] / 2) * 2 if len(f) else None


def smooth(vals, tol):
    """Neighbouring clips within tol share one value, so framing does not jump at every cut."""
    out, grp = list(vals), []
    def flush():
        if grp:
            med = np.median([np.array(vals[k], float) for k in grp], axis=0)
            for k in grp: out[k] = med
    for k, v in enumerate(vals):
        if v is None: flush(); grp = []; continue
        if grp and np.max(np.abs(np.array(v, float) - np.array(vals[grp[0]], float))) > tol: flush(); grp = []
        grp.append(k)
    flush(); return out


OBS_FRAME = os.environ.get("OBS_FRAME", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "layout", "split-frame.png"))


def make_assets(edit):
    """The frame OBS records through is the one the rebuild must use, or a reframed shot
    does not match the rest of the video. Built by layout/make_frame.py; only the
    fallback below draws one, for footage shot before that existed."""
    if os.path.exists(OBS_FRAME):
        f = Image.open(OBS_FRAME).convert("RGBA"); f.save(f"{edit}/layout-frame.png")
        flat = Image.new("RGBA", f.size, (0, 0, 0, 255))          # bg track: the frame with no holes
        Image.alpha_composite(flat, f).convert("RGB").save(f"{edit}/_bg.png")
        sh(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", f"{edit}/_bg.png", "-t", "1800", "-r", "30",
            "-vf", "format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-crf", "18",
            "-g", "900", f"{edit}/layout-bg.mp4"])   # long GOP: a textured still with a keyframe a second was 633 MB
        os.remove(f"{edit}/_bg.png"); return
    h, w = 1080, 1920; yy, xx = np.mgrid[0:h, 0:w]; t = ((xx / w) * 0.65 + (yy / h) * 0.35)[..., None]
    img = np.array([38, 22, 74]) * (1 - t) + np.array([74, 36, 18]) * t
    vig = 1 - 0.55 * (((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2)[..., None]
    bg = Image.fromarray(np.clip(img * np.clip(vig, 0.25, 1) * 0.85, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2)).convert("RGBA")
    bg.convert("RGB").save(f"{edit}/_bg.png")
    sh(["ffmpeg", "-v", "error", "-y", "-loop", "1", "-i", f"{edit}/_bg.png", "-t", "1800", "-r", "30", "-vf", "format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "16", "-g", "30", f"{edit}/layout-bg.mp4"])
    shd = Image.new("RGBA", (w, h), (0, 0, 0, 0)); d = ImageDraw.Draw(shd)
    for x, y, pw, ph in ((PX, PY, PW, PH), (CX, CY, CW, CH)): d.rounded_rectangle((x + 6, y + 14, x + pw + 6, y + ph + 14), 34, fill=(0, 0, 0, 150))
    frame = Image.alpha_composite(bg, shd.filter(ImageFilter.GaussianBlur(22)))
    a = Image.new("L", (w * 2, h * 2), 255); da = ImageDraw.Draw(a)
    for x, y, pw, ph in ((PX, PY, PW, PH), (CX, CY, CW, CH)): da.rounded_rectangle((x * 2, y * 2, (x + pw) * 2 - 1, (y + ph) * 2 - 1), 68, fill=0)
    frame.putalpha(a.resize((w, h), Image.LANCZOS)); frame.save(f"{edit}/layout-frame.png"); os.remove(f"{edit}/_bg.png")


def cmd_layers(folder):
    """cutlist.md rows:  | n | name | in | out | screen |   screen = auto (default) | none | full | x,y,w,h"""
    folder, edit, p = paths(folder)
    lag = json.load(open(f"{edit}/check.json"))["lag"] if os.path.exists(f"{edit}/check.json") else 2
    rows = re.findall(r"^\|\s*\d+\s*\|([^|]+)\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|([^|\n]*)", open(f"{edit}/cutlist.md").read(), re.M)
    if not rows: sys.exit("no rows in edit/cutlist.md")
    cuts = [(n.strip(), float(a), float(b), (m.strip() or "auto").replace("yes", "auto")) for n, a, b, m in rows]
    sh(["ffmpeg", "-v", "error", "-y", "-i", p["main"], "-vn", "-af", "highpass=f=70,loudnorm=I=-14:TP=-1.5:LRA=11", "-ar", "48000", "-c:a", "pcm_s16le", f"{edit}/mic.wav"])
    make_assets(edit)
    crops = smooth([screen_crop(p["scr"], (a + b) / 2, m) for _, a, b, m in cuts], 70)
    faces = smooth([[face_x(p["cam"], (a + b) / 2) or 984.0] for _, a, b, _ in cuts], 45)
    files = {"bg": (f"{edit}/layout-bg.mp4", 1920, 1080, 54000, True), "scr": (p["scr"], 3840, 2160, 10 ** 6, True), "cam": (p["cam"], 1920, 1080, 10 ** 6, True),
             "frame": (f"{edit}/layout-frame.png", 1920, 1080, 54000, True), "mic": (f"{edit}/mic.wav", 0, 0, 10 ** 6, False)}
    seen = set()
    def fileref(k):
        f, w, h, dur, vid = files[k]
        if k in seen: return f'<file id="{k}"/>'
        seen.add(k)
        media = f'<video><samplecharacteristics><width>{w}</width><height>{h}</height></samplecharacteristics></video>' if vid else '<audio><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate></samplecharacteristics><channelcount>2</channelcount></audio>'
        return f'<file id="{k}"><name>{os.path.basename(f)}</name><pathurl>file://localhost{urllib.parse.quote(f)}</pathurl><rate><timebase>30</timebase><ntsc>FALSE</ntsc></rate><duration>{dur}</duration><media>{media}</media></file>'
    def place(sw, sh_, crop, px, py, pw, ph):
        x, y, w, h = crop; scale = pw / w * 1.02                       # 2% bleed hides the seam at the window edge
        dx = (px + pw / 2 - 960) - (x + w / 2 - sw / 2) * scale; dy = (py + ph / 2 - 540) - (y + h / 2 - sh_ / 2) * scale
        par = lambda i, v: f'<parameter><parameterid>{i}</parameterid><name>{i}</name><valuemin>0</valuemin><valuemax>100</valuemax><value>{v:.4f}</value></parameter>'
        return ('<filter><effect><name>Basic Motion</name><effectid>basic</effectid><effectcategory>motion</effectcategory><effecttype>motion</effecttype><mediatype>video</mediatype>'
                f'<parameter><parameterid>scale</parameterid><name>Scale</name><valuemin>0</valuemin><valuemax>1000</valuemax><value>{scale * 100 * sw / 1920:.4f}</value></parameter>'   # Resolve scales from the fitted image
                f'<parameter><parameterid>center</parameterid><name>Center</name><value><horiz>{dx / 1920:.6f}</horiz><vert>{dy / 1080:.6f}</vert></value></parameter></effect></filter>'
                '<filter><effect><name>Crop</name><effectid>crop</effectid><effectcategory>motion</effectcategory><effecttype>motion</effecttype><mediatype>video</mediatype>'
                + par("left", x / sw * 100) + par("right", (sw - x - w) / sw * 100) + par("top", y / sh_ * 100) + par("bottom", (sh_ - y - h) / sh_ * 100) + '</effect></filter>')
    tr = {k: [] for k in ("bg", "scr", "cam", "frame", "mic")}; T = 0
    for k, (name, a, b, _) in enumerate(cuts):
        s, n = round(a * FPS), round((b - a) * FPS); vs = max(s - lag, 0)
        def item(key, src, extra="", nm=""):
            return (f'<clipitem id="{key}{k}"><name>{nm or name}</name><duration>{files[key][3]}</duration><rate><timebase>30</timebase><ntsc>FALSE</ntsc></rate>'
                    f'<start>{T}</start><end>{T + n}</end><in>{src}</in><out>{src + n}</out>{fileref(key)}{extra}</clipitem>')
        tr["bg"].append(item("bg", 0, nm="bg"))
        if crops[k] is not None:
            fx = int(min(max(float(faces[k][0]) - FACE_W / 2, 0), 1920 - FACE_W))
            tr["scr"].append(item("scr", vs, place(3840, 2160, tuple(crops[k]), PX, PY, PW, PH)))
            tr["cam"].append(item("cam", vs, place(1920, 1080, (fx, 0, FACE_W, 1080), CX, CY, CW, CH)))
            tr["frame"].append(item("frame", 0, nm="rounded frame"))
        else:
            tr["cam"].append(item("cam", vs))
        tr["mic"].append(item("mic", s)); T += n
    fmt = '<format><samplecharacteristics><width>1920</width><height>1080</height><pixelaspectratio>square</pixelaspectratio><rate><timebase>30</timebase><ntsc>FALSE</ntsc></rate></samplecharacteristics></format>'
    title = os.path.basename(folder)
    xml = (f'<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="5"><sequence id="seq1"><name>{title} layers</name><duration>{T}</duration><rate><timebase>30</timebase><ntsc>FALSE</ntsc></rate><media><video>{fmt}'
           + "".join(f"<track>{''.join(tr[k])}</track>" for k in ("bg", "scr", "cam", "frame")) + f'</video><audio><track>{"".join(tr["mic"])}</track></audio></media></sequence></xmeml>')
    open(f"{edit}/layers.xml", "w").write(xml)
    print(f"{len(cuts)} cuts, {T / FPS / 60:.2f} min, {sum(c is not None for c in crops)} with screen -> {edit}/layers.xml")


# ---------- tighten ----------
def cmd_tighten(xml_path, thr=-26.0, demo_from=None, cuts=None):
    """cuts: a JSON file of [[start_s, end_s], ...] in timeline seconds. Given, those spans are removed
    instead of detected silence (word-level polish from a forced-alignment transcript)."""
    xml_path = os.path.abspath(os.path.expanduser(xml_path)); out = re.sub(r"\.xml$", "", xml_path) + ("-polish.xml" if cuts else "-tight.xml")
    tree = ET.parse(xml_path); seq = tree.getroot().find("sequence"); total = int(seq.find("duration").text)
    a1 = seq.find("media/audio").findall("track")[0].findall("clipitem")
    mic = urllib.parse.unquote(next(f.find("pathurl").text for f in tree.getroot().iter("file") if f.find("pathurl") is not None and f.find("pathurl").text.endswith(".wav"))).replace("file://localhost", "").replace("file://", "")
    with wave.open(mic) as w:
        sr, ch = w.getframerate(), w.getnchannels(); M = np.frombuffer(w.readframes(w.getnframes()), np.int16).reshape(-1, ch)[:, 0]
    play = np.concatenate([M[int(int(c.find("in").text) / FPS * sr):int((int(c.find("in").text) + int(c.find("end").text) - int(c.find("start").text)) / FPS * sr)] for c in a1])
    hop = sr // 100; db = 20 * np.log10(np.abs(play[: len(play) // hop * hop].astype(float)).reshape(-1, hop).max(1) / 32768 + 1e-6)
    demo = float(demo_from) if demo_from is not None else 1e9
    rem = [tuple(c) for c in json.load(open(cuts))] if cuts else []
    for s, e in ([] if cuts else quiet_runs(db, thr, 0.30)):
        if s < demo: rem.append((s + 0.11, e - 0.07))                  # keep the word tail and a short lead-in
        elif e - s >= 0.60: rem.append((s + 0.30, e - 0.20))           # on-screen demos keep longer beats
    rem = sorted((round(a * FPS), round(b * FPS)) for a, b in rem if b - a >= 0.10 and a > 0.2 and b < total / FPS - 0.2)
    keep, t = [], 0
    for a, b in rem:
        if a > t: keep.append((t, a))
        t = max(t, b)
    keep.append((t, total))
    newpos = lambda x: x - sum(min(b, x) - a for a, b in rem if a < x)
    seen, n = set(), 0
    for track in list(seq.find("media/video").findall("track")) + list(seq.find("media/audio").findall("track")):
        items = track.findall("clipitem")
        for it in items: track.remove(it)
        for it in items:
            s, e, i0 = int(it.find("start").text), int(it.find("end").text), int(it.find("in").text)
            for a, b in keep:
                x, y = max(s, a), min(e, b)
                if y - x < 1: continue
                c = copy.deepcopy(it); n += 1; c.set("id", f"k{n}")
                for tag, v in (("start", newpos(x)), ("end", newpos(x) + y - x), ("in", i0 + x - s), ("out", i0 + y - s)): c.find(tag).text = str(v)
                for l in c.findall("link"): c.remove(l)
                f = c.find("file")
                if f is not None:
                    if f.get("id") in seen: [f.remove(ch_) for ch_ in list(f)]
                    elif len(f): seen.add(f.get("id"))
                track.append(c)
    new = newpos(total); seq.find("duration").text = str(new); seq.find("name").text = seq.find("name").text.replace(" (Resolve)", "") + (" polish" if cuts else " tight")
    tree.write(out, encoding="UTF-8", xml_declaration=True)
    body = open(out).read().replace("?>", "?>\n<!DOCTYPE xmeml>", 1)      # read fully before reopening for write
    open(out, "w").write(body)
    # proof: transcribe before and after, words must survive
    base = os.path.dirname(out); res = {}
    for tag, audio in (("before", play), ("after", np.concatenate([play[int(a / FPS * sr):int(b / FPS * sr)] for a, b in keep]))):
        with wave.open(f"{base}/_{tag}.wav", "w") as w: w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(audio.tobytes())
        sh(["ffmpeg", "-v", "error", "-y", "-i", f"{base}/_{tag}.wav", "-ac", "1", "-ar", "16000", f"{base}/_{tag}16.wav"]); whisper(f"{base}/_{tag}16.wav", f"{base}/_{tag}")
        res[tag] = re.findall(r"[a-z0-9']+", open(f"{base}/_{tag}.txt").read().lower())
        for f in (f"{base}/_{tag}.wav", f"{base}/_{tag}16.wav", f"{base}/_{tag}.txt"): os.remove(f)
    import difflib
    print(f"{len(rem)} cuts, removed {(total - new) / FPS:.1f}s, {total / FPS / 60:.2f} -> {new / FPS / 60:.2f} min -> {out}\nwords {len(res['before'])} -> {len(res['after'])}; check these by ear:")
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, res["before"], res["after"], autojunk=False).get_opcodes():
        if tag != "equal": print("  ", tag, "|", " ".join(res["before"][max(i1 - 3, 0):i1]), "[", " ".join(res["before"][i1:i2]), "->", " ".join(res["after"][j1:j2]), "]")


# ---------- takes ----------
JEV_URL, JEV_MODEL, JEV_WINDOW = "https://api.typesafe.ai/v1/systemone", "jev-latest", 6


def jev(state, questions):
    """One TypeSafe System One call: every question is judged over the same state, in parallel, individually scored."""
    key = os.environ.get("TYPESAFE_API_KEY")
    if not key: sys.exit("TYPESAFE_API_KEY is not set. Export it (console.typesafe.ai) or pick the takes by hand: SKILL.md section 3.")
    req = urllib.request.Request(JEV_URL, json.dumps({"state": state, "model": JEV_MODEL, "questions": questions}).encode(),
                                 {"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    try: return json.load(urllib.request.urlopen(req, timeout=120))["answers"]
    except urllib.error.HTTPError as e: sys.exit(f"TypeSafe {e.code}: {e.read()[:500].decode(errors='replace')}")


def noul(q, **data):
    return {"type": "noul", "instructions": {**data, "question": q}}


def group_takes(lines, ask=jev):
    """lines: [(t, text)]. Returns groups: [[(first_line, last_line), ...]] - one group per thought, one span per attempt.
    A line that restarts a sentence begun up to JEV_WINDOW lines back closes the attempt it restarts."""
    restart = {}
    for c0 in range(1, len(lines), 40):                                  # 40 lines x 6 pairs per request
        qs = {f"r{i}_{j}": noul("`later` repeats the opening words of `earlier`, as a retake of the same sentence.", earlier=lines[j][1], later=lines[i][1])
              for i in range(c0, min(c0 + 40, len(lines))) for j in range(max(i - JEV_WINDOW, 0), i)}   # inline text: Jev ignores `lines[i]` index references
        for k, a in ask({}, qs).items():
            i, j = map(int, k[1:].split("_")); restart[i, j] = a["noul"]
    groups, grp, cand = [], [], 0                                         # grp = spans in the current group, cand = start line of the open attempt
    for i in range(1, len(lines)):
        hits = [j for j in range(max(i - JEV_WINDOW, 0), i) if restart.get((i, j), 0) > 0.5]
        if not hits: continue
        j = min(hits)
        if j > cand:                                                      # restarted a later sentence: the open attempt is done, a new thought began at j
            grp.append((cand, j - 1)); groups.append(grp); grp, cand = [], j
        grp.append((cand, i - 1)); cand = i
    grp.append((cand, len(lines) - 1)); groups.append(grp)
    return groups


def score_takes(texts, ask=jev):
    """All attempts at one thought judged in one request; each gets its own probability of being finished.
    ponytail: no 'clean delivery' question - on unpunctuated Whisper text Jev scores every take as stumbly (0.02-0.12), so it separates nothing."""
    a = ask({}, {f"c{k}": noul("Does `take` finish its thought - it ends on a complete sentence instead of trailing off, breaking off mid-sentence, or being abandoned?", take=t) for k, t in enumerate(texts)})
    return [a[f"c{k}"]["noul"] for k in range(len(texts))]


def cmd_takes(folder):
    folder, edit, p = paths(folder)
    lines = [(float(m.group(1)), m.group(2).strip()) for m in re.finditer(r"^\[\s*([\d.]+)\]\s*(.*)$", open(f"{edit}/transcript.txt").read(), re.M)]
    if not lines: sys.exit("no edit/transcript.txt - run: videokit.py script <folder>")
    ends = [s["offsets"]["to"] / 1000 for s in json.load(open(f"{edit}/_t.json"))["transcription"]] if os.path.exists(f"{edit}/_t.json") else [t for t, _ in lines[1:]] + [lines[-1][0] + 5]
    keep = [k for k, (_, t) in enumerate(lines) if len(t.split()) > 2]     # "yeah", "so", "thank you": dead air between attempts, never a take
    lines, ends = [lines[k] for k in keep], [ends[k] for k in keep]
    rows, notes, spans = [], [], []
    for g in group_takes(lines):
        texts = [" ".join(t for _, t in lines[a:b + 1]) for a, b in g]
        sc = score_takes(texts)
        ok = [k for k, c in enumerate(sc) if c > 0.5]
        pick = ok[-1] if ok else max(range(len(g)), key=sc.__getitem__)  # last finished attempt, else the best guess flagged ?
        a, b = g[pick]; t0, t1 = lines[a][0], ends[b]
        rows.append(f"| {len(rows) + 1} | {'' if ok else '? '}{' '.join(texts[pick].split()[:7])} | {t0:.2f} | {t1:.2f} |  |")
        spans.append(f"{t0:.2f}:{t1:.2f}")
        notes.append(f"{len(rows)}. " + "  ".join(f"{'*' if k == pick else ' '}{lines[x][0]:.1f}-{ends[y]:.1f} p{sc[k]:.2f} \"{' '.join(texts[k].split()[:6])}\"" for k, (x, y) in enumerate(g)))
    out = f"{edit}/cutlist-draft.md" if os.path.exists(f"{edit}/cutlist.md") else f"{edit}/cutlist.md"   # never overwrite a cutlist you wrote
    open(out, "w").write("| # | shot | in | out | screen |\n|---|---|---|---|---|\n" + "\n".join(rows) +
                         "\n\nDRAFT from `videokit.py takes`. `?` = no attempt scored as finished, best guess. Fill `screen`, rename shots, then prove every cut:\n\n"
                         f"    videokit.py piece \"{folder}\" {' '.join(spans)}\n\n## Attempts per thought (* = picked, p = probability the attempt is finished)\n\n" + "\n".join(notes) + "\n")
    print(open(out).read()); print(f"-> {out}")


def cmd_thumbs(d):
    d = os.path.abspath(os.path.expanduser(d)); out = os.path.join(d, "youtube"); os.makedirs(out, exist_ok=True)
    for k, f in enumerate(sorted(g for g in glob.glob(f"{d}/*") if g.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))), 1):
        im = Image.open(f).convert("RGB").resize((1280, 720), Image.LANCZOS); q = 92
        while True:
            im.save(f"{out}/thumb-{k}.jpg", quality=q)
            if os.path.getsize(f"{out}/thumb-{k}.jpg") < 1_900_000 or q <= 60: break
            q -= 6
        print(f"thumb-{k}.jpg  <- {os.path.basename(f)}  ({os.path.getsize(f'{out}/thumb-{k}.jpg') // 1024} KB)")


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) < 2: sys.exit(__doc__)
    c = a[0]
    if c == "check": cmd_check(a[1])
    elif c == "script": cmd_script(a[1])
    elif c == "piece": cmd_piece(a[1], a[2:])
    elif c == "gaps": cmd_gaps(a[1], a[2:])
    elif c == "takes": cmd_takes(a[1])
    elif c == "layers": cmd_layers(a[1])
    elif c == "thumbs": cmd_thumbs(a[1])
    elif c == "tighten":
        opt = dict(zip(a[2::2], a[3::2])); cmd_tighten(a[1], float(opt.get("--thr", -26)), opt.get("--demo-from"), opt.get("--cuts"))
    else: sys.exit(__doc__)
