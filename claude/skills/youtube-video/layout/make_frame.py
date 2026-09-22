#!/usr/bin/env python3
"""Build the OBS Split overlay: a dark 1920x1080 frame with two transparent windows. The
windows are what the screen and camera show through; everything else is the background, so
this one file is both the backdrop and the corner rounding.

    python3 make_frame.py [cubes|dots|grid] [out.png]

`cubes` (default) is a cubic gradient: bevelled tiles carrying a soft purple glow from the
centre out to near-black. `dots` is a halftone screen over light sweeps. `grid` is the
blueprint sheet: faint rules and registration crosshairs.

Default output is the one OBS points at:
    ~/Documents/YouTube Concepts/obs-layout/split-frame.png
OBS must be closed when this is replaced, or it keeps the old image cached.
"""
import os, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H = 1920, 1080
PW, PH, PX, PY = 1300, 731, 60, 174        # screen panel
CW, CH, CX, CY = 450, 731, 1410, 174       # camera panel
PANELS = ((PX, PY, PW, PH), (CX, CY, CW, CH))
RADIUS = 34

BASE = (10, 10, 12)      # near-black, the reference is almost flat
GRID = 8                 # how much lighter a grid line is than the base
GRID_STEP = 120
TICK = 16                # crosshair arm length
MARGIN = 44              # inset border rectangle
LABEL = "@yourhandle"
MONO = "/System/Library/Fonts/Menlo.ttc"


CELL = 5          # halftone dot pitch in px
ANGLE = 22        # screen angle; off-axis so the dots do not fight the pixel grid
PEAK = 235        # brightest a dot gets


def light_field(w, h):
    """Soft near-black light, bright in the top-left, with two faint sweeps. 0..1."""
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    u, v = x / w, y / h
    f = 1.25 * np.exp(-((u * 1.7) ** 2 + (v * 1.1) ** 2) / 0.10)          # top-left source
    f += 0.55 * np.exp(-((u - 0.30 - 0.45 * v) ** 2) / 0.012)             # diagonal sweep
    f += 0.40 * np.exp(-((u - 0.92) ** 2 + (v - 0.78) ** 2) / 0.05)       # bottom-right glow
    f += 0.07 * np.exp(-((v - 1.02) ** 2) / 0.05)                         # floor lift
    return np.clip(f, 0, 1) ** 1.35


def halftone(w, h):
    """Light field rendered as a rotated dot screen, the way the reference sheet reads."""
    d = int(np.hypot(w, h)) + CELL * 4                                    # rotate-safe canvas
    d -= d % CELL
    f = light_field(d, d)
    yy, xx = np.mgrid[0:d, 0:d]
    cy, cx = yy % CELL, xx % CELL
    c = (CELL - 1) / 2
    r2 = (cy - c) ** 2 + (cx - c) ** 2
    cellval = f[(yy // CELL) * CELL + int(c), (xx // CELL) * CELL + int(c)]   # one value per cell
    rad = (CELL / 2 * 1.08) * np.sqrt(cellval)
    dots = np.where(r2 <= rad ** 2, cellval * PEAK, 0)
    im = Image.fromarray(dots.astype(np.uint8)).rotate(ANGLE, resample=Image.NEAREST)
    left, top = (d - w) // 2, (d - h) // 2
    return np.array(im.crop((left, top, left + w, top + h))).astype(np.int16)


def frame_dots():
    a = np.zeros((H, W, 3), np.int16) + np.array(BASE, np.int16)
    a += halftone(W, H)[..., None]
    a = a + np.random.default_rng(7).normal(0, 1.6, (H, W, 1))            # kills banding on upload
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGBA")
    try:
        f = ImageFont.truetype(MONO, 15)
        ImageDraw.Draw(im).text((MARGIN + 18, H - MARGIN - 30), LABEL, font=f, fill=(96, 96, 102))
    except OSError:
        pass
    return im


TILE = 60                     # cube size; 1920/60 and 1080/60 are whole, so no cut tiles at the edges
GLOW = (124, 72, 255)         # the purple at the very centre
GLOW_GAIN = 0.62              # how far toward GLOW the brightest tile goes. Subtle is 0.4-0.7
GLOW_SX, GLOW_SY = 0.30, 0.46  # spread, as a fraction of width and height. The panels cover the
                              # middle, so SY has to be big enough to bleed out above and below them
BEVEL = 0.16                  # light top-left, dark bottom-right inside each tile, relative to its own colour


def frame_cubes():
    """Cubic gradient: flat tiles, each the colour of a soft purple glow at its own centre,
    fading to near-black at the edges. Bevel and seam are what make them read as cubes."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    tx, ty = (xx // TILE) * TILE + TILE / 2, (yy // TILE) * TILE + TILE / 2      # tile centres
    f = np.exp(-(((tx / W - 0.5) / GLOW_SX) ** 2 + ((ty / H - 0.5) / GLOW_SY) ** 2))
    f = (f ** 1.25) * GLOW_GAIN

    lx, ly = (xx % TILE) / TILE, (yy % TILE) / TILE                              # 0..1 inside the tile
    bevel = 1 + BEVEL * (1 - lx - ly)                                            # >1 top-left, <1 bottom-right
    edge = np.minimum(np.minimum(lx, 1 - lx), np.minimum(ly, 1 - ly)) * TILE     # px to the nearest tile edge
    seam = np.clip(edge / 1.5, 0, 1) * 0.30 + 0.70                               # a dark hairline between tiles
    hi = np.clip(1 - np.minimum(lx, ly) * TILE / 2.0, 0, 1) * 0.10               # lit top and left rim

    base, glow = np.array(BASE, np.float32), np.array(GLOW, np.float32)
    col = base + (glow - base) * f[..., None]
    a = col * (bevel * seam + hi * (f / GLOW_GAIN))[..., None]                   # no rim light where it is dark
    a = a + np.random.default_rng(7).normal(0, 2.0, (H, W, 1))                   # grain: soft gradients band on upload
    im = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGBA")
    try:
        ft = ImageFont.truetype(MONO, 15)
        ImageDraw.Draw(im).text((MARGIN + 18, H - MARGIN - 30), LABEL, font=ft, fill=(104, 100, 118))
    except OSError:
        pass
    return im


def frame():
    im = Image.new("RGB", (W, H), BASE)
    d = ImageDraw.Draw(im)
    line = tuple(c + GRID for c in BASE)

    for x in range(GRID_STEP, W, GRID_STEP):
        d.line([(x, 0), (x, H)], fill=line)
    for y in range(GRID_STEP, H, GRID_STEP):
        d.line([(0, y), (W, y)], fill=line)

    # registration crosshairs, brighter than the grid, at every third intersection
    cross = tuple(c + 26 for c in BASE)
    for x in range(GRID_STEP * 3, W, GRID_STEP * 3):
        for y in range(GRID_STEP * 3, H, GRID_STEP * 3):
            d.line([(x - TICK, y), (x + TICK, y)], fill=cross)
            d.line([(x, y - TICK), (x, y + TICK)], fill=cross)

    d.rectangle([MARGIN, MARGIN, W - MARGIN, H - MARGIN], outline=tuple(c + 18 for c in BASE))

    try:
        f = ImageFont.truetype(MONO, 15)
        d.text((MARGIN + 18, H - MARGIN - 30), LABEL, font=f, fill=(70, 70, 76))
    except OSError:
        pass                                          # ponytail: no font, no label, still a valid frame

    # grain: the reference is matte, and flat black banding on a compressed upload looks cheap
    a = np.array(im).astype(np.int16) + np.random.default_rng(7).normal(0, 2.4, (H, W, 1))
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).convert("RGBA")


def cut_windows(im):
    """Panel shadows, hairline edges, then punch the two windows out of the alpha."""
    sh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ds = ImageDraw.Draw(sh)
    for x, y, pw, ph in PANELS:                        # panels sit above the sheet, so they cast
        ds.rounded_rectangle((x + 4, y + 12, x + pw + 4, y + ph + 12), RADIUS, fill=(0, 0, 0, 190))
    im = Image.alpha_composite(im, sh.filter(ImageFilter.GaussianBlur(26)))

    ed = ImageDraw.Draw(im)                            # hairline edge so a dark panel still reads
    for x, y, pw, ph in PANELS:
        ed.rounded_rectangle((x - 1, y - 1, x + pw, y + ph), RADIUS + 1, outline=(58, 58, 64, 255), width=2)

    mask = Image.new("L", (W * 2, H * 2), 255)         # 2x then down = antialiased corners
    dm = ImageDraw.Draw(mask)
    for x, y, pw, ph in PANELS:
        dm.rounded_rectangle((x * 2, y * 2, (x + pw) * 2 - 1, (y + ph) * 2 - 1), RADIUS * 2, fill=0)
    im.putalpha(mask.resize((W, H), Image.LANCZOS))
    return im


if __name__ == "__main__":
    STYLES = {"cubes": frame_cubes, "dots": frame_dots, "grid": frame}
    style = next((a for a in sys.argv[1:] if a in STYLES), "cubes")
    rest = [a for a in sys.argv[1:] if a not in STYLES]
    out = rest[0] if rest else os.path.expanduser("~/Documents/YouTube Concepts/obs-layout/split-frame.png")
    im = cut_windows(STYLES[style]())
    im.save(out)
    a = np.array(im)
    clear, soft = int((a[..., 3] == 0).sum()), int(((a[..., 3] > 0) & (a[..., 3] < 255)).sum())
    want = PW * PH + CW * CH                       # the corners and the LANCZOS edge eat a little
    assert want - clear < 20000, f"windows are wrong: {clear:,} clear vs {want:,} expected"
    print(f"{out}  {im.size}  {clear:,} transparent px + {soft:,} soft edge "
          f"(windows are {PW}x{PH} and {CW}x{CH})")
