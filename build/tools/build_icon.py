"""Build icon.bin: bg1 / bg2 / bg3 on a black backdrop, each held 2s with a
0.5s soft dip to black between them, looping forever.

Layer stack (bottom to top): BlackPicture (always opaque), then Bg1/Bg2/Bg3
pictures whose pane alpha is animated by RLVC (type2=16). Because each layer
returns to alpha 0 before the next rises, the composite passes through pure
black at the hand-off, which is the dip.

Timing at 60 fps, framesize 450 (7.5 s):
    slot i starts at i*150 -> 15f fade in, 120f (2.0s) hold, 15f fade out
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))

from PIL import Image

import tpl as T
from wiilib import U8, pack_lz77_imd5, unpack_lz77_imd5

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BUILD = os.path.join(ROOT, "build")
BENZIN = os.path.join(os.path.dirname(__file__), "benzin")
IMG = os.path.join(ROOT, "icon")

FPS = 60
HOLD = 120          # 2.0 s fully visible
FADE = 15           # 0.25 s each side -> 0.5 s dip between slots
SLOT = FADE + HOLD + FADE       # 150

# Hard limit enforced by the System Menu (cmpw against 0x19000 at 0x81352488).
# Going over means the icon buffer is never allocated and the Menu brick-loops.
ICON_CAP = 0x19000              # 102,400 bytes

# The Wii icon viewport is 128x96 in 4:3 -- but the Menu renders an anamorphic
# 640x480 framebuffer, so a 16:9 TV shows 4/3 more horizontal layout units:
# 170.67x96. Height never changes. Art only 128 wide therefore gets black side
# bars on a widescreen set, so the pane and the textures are 176 wide (170.67
# rounded up to a multiple of 16) and the 4:3 crop is their centre 128.
#
# Art authored larger than the pane is centre-cropped, not scaled -- Tantric's
# 256x96 Background.tpl misleads here because it is a scrolling tiled pattern,
# so losing half of it is invisible. His real content (120x48 logo, 36x36
# sprites) all fits inside 128x96.
ICON_W, ICON_H = 176, 96

# 4:3 sees only the middle of that, so keep anything that must be legible here.
SAFE_W = 128
FRAMES = SLOT * 3               # 270 = 4.5 s

# old name -> new name
TEX = {"Background.tpl": "Black.tpl", "Logo00.tpl": "Bg1.tpl",
       "Mario00.tpl": "Bg2.tpl", "Goomba00.tpl": "Bg3.tpl"}
MAT = {"BackgroundMaterial": "BlackMaterial", "Logo00Material": "Bg1Material",
       "Mario00Material": "Bg2Material", "Goomba00Material": "Bg3Material"}
PANE = {"BackgroundPicture": "BlackPicture",
        "Logo00Pane": "Bg1Pane", "Logo00Picture": "Bg1Picture",
        "Mario00Pane": "Bg2Pane", "Mario00Picture": "Bg2Picture",
        "Goomba00Pane": "Bg3Pane", "Goomba00Picture": "Bg3Picture"}
SRC = {"Black.tpl": "black.png", "Bg1.tpl": "bg1.png",
       "Bg2.tpl": "bg2.png", "Bg3.tpl": "bg3.png"}
DROP = ["Logo01.tpl", "Mario01.tpl", "Mario02.tpl", "Goomba01.tpl", "Goomba02.tpl"]


def benzin(*args):
    r = subprocess.run(["wine", "BENZIN.EXE", *args], cwd=BENZIN,
                       capture_output=True, env={**os.environ, "WINEDEBUG": "-all"})
    out = (r.stdout + r.stderr).decode(errors="replace")
    if "Couldn't" in out or r.returncode != 0:
        raise RuntimeError(f"benzin {args}: {out}")


# Benzin emits self-closing <tag type="pas1" /> markers between panes. A naive
# `<tag ...>(.*?)</tag>` matches one of those and then swallows the whole next
# pane block, so the attribute part must be forbidden from ending in '/'.
TAGBLOCK = r'<tag type="(\w+)"((?:[^>]*[^/>])?)>(.*?)</tag>'


def fix_layout(x):
    # texture list + material texture references + material names
    for old, new in TEX.items():
        x = x.replace(f"<name>{old}</name>", f"<name>{new}</name>")
        x = x.replace(f'<texture name="{old}">', f'<texture name="{new}">')
    for old, new in MAT.items():
        x = x.replace(f'<entries name="{old}">', f'<entries name="{new}">')
        x = x.replace(f'<material name="{old}" />', f'<material name="{new}" />')
    # the stock background scrolls (REPEAT + animated XTrans); ours must not
    x = x.replace("<wrap_s>GX_REPEAT</wrap_s>", "<wrap_s>GX_CLAMP</wrap_s>")
    x = x.replace("<XTrans>0.6000000238</XTrans>", "<XTrans>0.0000000000</XTrans>")

    # every pane: full-screen, centred, no offset
    def fix(m):
        kind, attrs, body = m.group(1), m.group(2), m.group(3)
        if kind not in ("pan1", "pic1"):
            return m.group(0)
        name = re.search(r'name="([^"]*)"', attrs)
        name = name.group(1) if name else ""
        if name == "RootPane":
            return m.group(0)
        body = re.sub(
            r"(<translate>\s*<x>)[^<]*(</x>\s*<y>)[^<]*(</y>\s*<z>)[^<]*(</z>)",
            r"\g<1>0.0000000000\g<2>0.0000000000\g<3>0.0000000000\g<4>", body)
        body = re.sub(
            r"(<size>\s*<width>)[^<]*(</width>\s*<height>)[^<]*(</height>)",
            rf"\g<1>{ICON_W}.000000\g<2>{ICON_H}.000000\g<3>", body)
        # Logo00Pane ships alpha=b4 (180). Pane alpha multiplies down the tree,
        # so inheriting it would cap that layer at 70% and break the fade.
        body = re.sub(r"<alpha>\w+</alpha>", "<alpha>ff</alpha>", body)
        attrs = re.sub(r'userdata="[^"]*"', 'userdata=""', attrs)
        return f'<tag type="{kind}"{attrs}>{body}</tag>'

    x = re.sub(TAGBLOCK, fix, x, flags=re.S)
    for old, new in PANE.items():
        x = x.replace(f'name="{old}"', f'name="{new}"')
    return x


def palettize(im):
    """Reduce a photo to a 256-entry index map + palette for CI8.

    tpl.quantize() only collapses images that are *already* inside the colour
    limit, so it cannot take a screenshot; median cut with Floyd-Steinberg
    dithering does. Palette entries are stored as RGB5A3, i.e. RGB555 when
    opaque, so the encoder rounds these again -- the comparison that justified
    CI8 was made after a full build/decode round trip, with that included.
    """
    q = im.convert("RGB").quantize(colors=256, method=Image.MEDIANCUT,
                                   dither=Image.FLOYDSTEINBERG)
    raw = q.getpalette()
    pal = [(raw[i * 3], raw[i * 3 + 1], raw[i * 3 + 2], 255) for i in range(256)]
    px = q.load()
    idx = [[px[x, y] for x in range(im.width)] for y in range(im.height)]
    return idx, pal


def keyframes(slot):
    """Alpha curve for one background. Zero tangents everywhere, which makes
    Benzin/GX interpolate as a smoothstep -- the 'soft' part of the fade."""
    s = slot * SLOT
    pts = [(0, 0)] if s > 0 else []
    pts += [(s, 0), (s + FADE, 255), (s + FADE + HOLD, 255), (s + SLOT, 0)]
    if s + SLOT < FRAMES:
        pts.append((FRAMES, 0))
    # de-duplicate frames while preserving order
    seen, out = set(), []
    for f, v in pts:
        if f in seen:
            continue
        seen.add(f)
        out.append((f, v))
    return out


def make_anim():
    L = ['<?xml version="1.0" encoding="utf-8"?>',
         '\t\t<xmlan version="2.1.12BETA" brlan_version="0008">',
         f'\t\t\t<pai1 framesize="{FRAMES}" flags="01">']
    for i, pane in enumerate(("Bg1Picture", "Bg2Picture", "Bg3Picture")):
        L.append(f'\t\t\t\t<pane name="{pane}" type="0">')
        L.append('\t\t\t\t\t<tag type="RLVC">')
        L.append('\t\t\t\t\t\t<entry type1="0" type2="16">')
        for f, v in keyframes(i):
            L.append('\t\t\t\t\t\t\t<triplet>')
            L.append(f'\t\t\t\t\t\t\t\t<frame>{f:.15f}</frame>')
            L.append(f'\t\t\t\t\t\t\t\t<value>{v:.15f}</value>')
            L.append('\t\t\t\t\t\t\t\t<blend>0.000000000000000</blend>')
            L.append('\t\t\t\t\t\t\t</triplet>')
        L.append('\t\t\t\t\t\t</entry>')
        L.append('\t\t\t\t\t</tag>')
        L.append('\t\t\t\t</pane>')
    L.append('\t\t\t</pai1>')
    L.append('\t\t</xmlan>')
    return "\n".join(L) + "\n"


def main():
    arc = U8.load(unpack_lz77_imd5(open(f"{BUILD}/extracted/icon.bin", "rb").read()))

    # --- layout
    src_lyt = os.path.join(BENZIN, "icon.brlyt")
    open(src_lyt, "wb").write(arc.get("/arc/blyt/icon.brlyt"))
    benzin("r", "icon.brlyt", "icon.xmlyt")
    x = fix_layout(open(os.path.join(BENZIN, "icon.xmlyt")).read())
    open(os.path.join(BENZIN, "icon_new.xmlyt"), "w").write(x)
    benzin("m", "icon_new.xmlyt", "icon_new.brlyt")

    # --- animation
    open(os.path.join(BENZIN, "icon_new.xmlan"), "w").write(make_anim())
    benzin("m", "icon_new.xmlan", "icon_new.brlan")

    arc.replace("/arc/blyt/icon.brlyt", open(os.path.join(BENZIN, "icon_new.brlyt"), "rb").read())
    arc.replace("/arc/anim/icon.brlan", open(os.path.join(BENZIN, "icon_new.brlan"), "rb").read())

    # --- textures
    #
    # icon.bin has a HARD 102,400-byte (0x19000) uncompressed cap, enforced by
    # the System Menu at 0x81352488. Exceed it and the buffer is never
    # allocated, so its LZ77 decompressor writes into address 0 and the Menu
    # dies right after the Health & Safety screen. Four 256x96 RGB565 layers
    # came to 196,864 bytes and did exactly that.
    #
    # Widening to 176 for 16:9 puts RGB565 over the line too: 3 x 33,792 =
    # 101,376 of texture leaves under 1 KB for everything else. So the photos
    # are CI8 with their own 256-entry palette -- 17,472 bytes each rather than
    # 33,856, which brings the whole archive to about half the cap. At this
    # size the quantisation is not visible; a decode-and-compare against the
    # sources showed no difference worth having the extra bytes for.
    #
    # The backdrop stays a 4x4 solid black texture stretched over its pane
    # (a flat colour scales exactly), which costs 96 bytes at any pane width.
    for old, new in TEX.items():
        arc.rename(f"/arc/timg/{old}", new)
        if new == "Black.tpl":
            # a flat colour scales exactly, so 4x4 stretched over the pane is
            # indistinguishable from a full-size black texture and costs 96 bytes
            im = Image.new("RGB", (4, 4), (0, 0, 0))
            tex = T.build([(im, T.RGB565, None, im.size)])
        else:
            im = Image.open(os.path.join(IMG, SRC[new])).convert("RGB")
            assert im.size == (ICON_W, ICON_H), \
                f"{SRC[new]} is {im.size}, need {ICON_W}x{ICON_H} (the Wii icon pane)"
            idx, pal = palettize(im)
            tex = T.build([(idx, T.CI8, pal, im.size)])
        arc.replace(f"/arc/timg/{new}", tex)
    for d in DROP:
        i = arc.find(f"/arc/timg/{d}")
        arc.nodes.pop(i)
        for nd in arc.nodes:                     # keep directory ranges correct
            if nd.is_dir and nd.last > i:
                nd.last -= 1

    raw = arc.to_bytes()
    problems = arc.check_tree()
    assert not problems, problems
    assert len(raw) <= ICON_CAP, (
        f"icon.bin is {len(raw)} bytes, over the System Menu's {ICON_CAP}-byte "
        f"cap -- this bricks the Menu after the Health & Safety screen")
    open(f"{BUILD}/out/icon_u8.bin", "wb").write(raw)
    packed = pack_lz77_imd5(raw)
    open(f"{BUILD}/out/icon.bin", "wb").write(packed)
    print(f"icon.bin: {len(raw)} uncompressed -> {len(packed)} stored "
          f"({len(raw)/ICON_CAP:.0%} of the {ICON_CAP:,}-byte cap)")
    print("  files:", [p for i, p in arc.paths() if not arc.nodes[i].is_dir])
    for i, pane in enumerate(("Bg1", "Bg2", "Bg3")):
        print(f"  {pane}: " + " ".join(f"{f}@{v}" for f, v in keyframes(i)))


if __name__ == "__main__":
    os.makedirs(f"{BUILD}/out", exist_ok=True)
    main()
