"""Render the built icon.bin to an animated GIF, driving it from the real
brlan keyframes so the preview reflects what the Wii will actually show.

brlan curves are Hermite (frame, value, slope). Every slope here is 0, which
reduces the segment to a smoothstep -- that is the 'soft' in the soft fade.
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))

from PIL import Image

import tpl as T
from wiilib import U8, unpack_lz77_imd5

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BUILD = os.path.join(ROOT, "build")
BENZIN = os.path.join(os.path.dirname(__file__), "benzin")
STEP = 3            # sample every 3rd frame -> 20 fps preview
PANE = (176, 96)    # the 16:9 icon pane; 4:3 shows its centre 128
SAFE_43 = 128


def hermite(p0, p1, f):
    (f0, v0, m0), (f1, v1, m1) = p0, p1
    if f1 == f0:
        return v1
    dt = f1 - f0
    t = (f - f0) / dt
    h00 = 2 * t ** 3 - 3 * t ** 2 + 1
    h10 = t ** 3 - 2 * t ** 2 + t
    h01 = -2 * t ** 3 + 3 * t ** 2
    h11 = t ** 3 - t ** 2
    return h00 * v0 + h10 * m0 * dt + h01 * v1 + h11 * m1 * dt


def sample(curve, f):
    if f <= curve[0][0]:
        return curve[0][1]
    if f >= curve[-1][0]:
        return curve[-1][1]
    for a, b in zip(curve, curve[1:]):
        if a[0] <= f <= b[0]:
            return hermite(a, b, f)
    return curve[-1][1]


def main():
    arc = U8.load(unpack_lz77_imd5(open(f"{BUILD}/out/icon.bin", "rb").read()))
    open(os.path.join(BENZIN, "prev.brlan"), "wb").write(arc.get("/arc/anim/icon.brlan"))
    subprocess.run(["wine", "BENZIN.EXE", "r", "prev.brlan", "prev.xmlan"], cwd=BENZIN,
                   capture_output=True, env={**os.environ, "WINEDEBUG": "-all"})
    an = open(os.path.join(BENZIN, "prev.xmlan")).read()
    frames_total = int(re.search(r'framesize="(\d+)"', an).group(1))

    curves = {}
    for m in re.finditer(r'<pane name="([^"]+)" type="0">(.*?)</pane>', an, re.S):
        trips = [(float(a), float(b), float(c)) for a, b, c in re.findall(
            r"<frame>([-\d.]+)</frame>\s*<value>([-\d.]+)</value>\s*<blend>([-\d.]+)</blend>",
            m.group(2))]
        curves[m.group(1)] = trips

    def tex(name):
        """Decode a texture and scale it to the pane size. Black.tpl is a 4x4
        solid colour stretched across its pane; the photos are CI8."""
        raw = arc.get(f"/arc/timg/{name}")
        t = T.parse(raw)[0]
        img = T.decode(raw[t["data_off"]:], t["w"], t["h"], t["fmt"], t["pal"])
        img = img.convert("RGBA")
        if img.size != PANE:
            img = img.resize(PANE, Image.NEAREST)
        return img

    black = tex("Black.tpl")
    layers = [(tex(f"Bg{i}.tpl"), curves[f"Bg{i}Picture"]) for i in (1, 2, 3)]

    out = []
    for f in range(0, frames_total, STEP):
        comp = black.copy()
        for img, curve in layers:
            a = max(0.0, min(255.0, sample(curve, f)))
            if a <= 0.5:
                continue
            lay = img.copy()
            lay.putalpha(int(round(a)))
            comp = Image.alpha_composite(comp, lay)
        out.append(comp.convert("P", palette=Image.ADAPTIVE))
    dur = int(round(1000 * STEP / 60))
    out[0].save(f"{BUILD}/out/icon_preview.gif", save_all=True, append_images=out[1:],
                duration=dur, loop=0, disposal=2)
    print(f"icon_preview.gif: {len(out)} frames, {dur} ms each "
          f"({frames_total / 60:.2f}s loop)  {PANE[0]}x{PANE[1]}, as 16:9 shows it")

    # The same animation as a 4:3 set shows it: the centre SAFE_43 columns.
    # Anything that has to stay legible on a CRT has to live inside this crop.
    x0 = (PANE[0] - SAFE_43) // 2
    crop = [f.crop((x0, 0, x0 + SAFE_43, PANE[1])) for f in out]
    crop[0].save(f"{BUILD}/out/icon_preview_4_3.gif", save_all=True,
                 append_images=crop[1:], duration=dur, loop=0, disposal=2)
    print(f"icon_preview_4_3.gif: centre {SAFE_43}x{PANE[1]} crop, as 4:3 shows it")
    for name, curve in curves.items():
        pts = " ".join(f"{int(f)}:{int(v)}" for f, v, _ in curve)
        print(f"  {name}: {pts}")


if __name__ == "__main__":
    main()
