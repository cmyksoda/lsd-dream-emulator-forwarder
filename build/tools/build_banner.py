"""Build banner.bin: one static full-bleed 832x456 image that fades in from
white over 3 seconds when the channel opens.

IMPORTANT -- why this is derived from Tantric's layout rather than written
from scratch. The first attempt emitted a minimal brlyt (lyt1/txl1/mat1/one
pane) and it bricked the System Menu: black screen after the Health & Safety
screen, with the CPU writing bytes to address 0. The minimal file was missing
the `fnl1` and `grp1` sections, and the Menu dereferences the root group
unconditionally. Section list of the working donor:

    lyt1 txl1 fnl1 mat1 <panes...> grp1

So: start from the donor layout, keep every section, and change as little as
possible.

  * BackgroundPicture is resized to the full 832x456 and moved to the origin
  * BackgroundMaterial stops repeating and scrolling (GX_CLAMP, XTrans 0)
  * every other pane is set invisible
  * the RLTS scroll on BackgroundMaterial is flattened to 0 in both brlans
  * unused textures shrink to 4x4 but keep their names, so every txl1 entry
    and every brlan RLTP timg reference still resolves

The white fade-in reuses BarsPicture, which is drawn above the background and
is not animated by either donor brlan. Its texture becomes a 4x4 solid white
stretched over the whole viewport (a flat colour scales exactly), its static
alpha becomes 00, and banner_Start.brlan gets an RLVC pane-alpha track driving
it 255 -> 0 over FADE_FRAMES with zero tangents (smoothstep). Start's
framesize is 1000, so the track then holds at 0; banner_Loop never touches the
pane, and the static alpha 00 keeps it invisible even if the Menu rebinds from
brlyt defaults. BarsMaterial's forecolor/backcolor tint registers are reset to
BackgroundMaterial's neutral pair so the overlay reads pure white.
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
# The banner viewport is 608x456 in 4:3. The Menu renders an anamorphic 640x480
# framebuffer, so a 16:9 TV shows 4/3 more horizontal layout units -- 810.67 --
# while the height is unchanged. A 608-wide pane therefore gets black side bars
# on a widescreen set. 832 is not a guess: Nintendo's own full-bleed panes in
# this donor (StripePicture, TitleBarPicture) are both exactly 832 wide, i.e.
# 810.67 rounded up to the next multiple of 64. 4:3 sees the centre 608.
W, H = 832, 456
SRC = os.path.join(ROOT, "banner", "bg.png")
KEEP_VISIBLE = {"RootPane", "BackgroundPicture", "BarsPicture"}
BG_TEX = "Background.tpl"

# the white fade-in overlay (see module docstring)
FADE_PANE = "BarsPicture"
FADE_MAT = "BarsMaterial"
FADE_TEX = "Bars.tpl"
FADE_FRAMES = 180               # 3.0 s at 60 fps

# Benzin writes self-closing <tag type="pas1" /> markers; a naive block regex
# matches one and then swallows the following pane whole.
TAGBLOCK = r'<tag type="(\w+)"((?:[^>]*[^/>])?)>(.*?)</tag>'


def benzin(*args):
    r = subprocess.run(["wine", "BENZIN.EXE", *args], cwd=BENZIN,
                       capture_output=True, env={**os.environ, "WINEDEBUG": "-all"})
    out = (r.stdout + r.stderr).decode(errors="replace")
    if "Couldn't" in out or r.returncode != 0:
        raise RuntimeError(f"benzin {args}: {out}")


def fix_layout(x):
    def fix(m):
        kind, attrs, body = m.group(1), m.group(2), m.group(3)
        if kind not in ("pan1", "pic1", "txt1", "wnd1"):
            return m.group(0)
        nm = re.search(r'name="([^"]*)"', attrs)
        nm = nm.group(1) if nm else ""
        if nm not in KEEP_VISIBLE:
            body = body.replace("<visible>01</visible>", "<visible>00</visible>")
        if nm in ("BackgroundPicture", FADE_PANE):
            body = re.sub(
                r"(<translate>\s*<x>)[^<]*(</x>\s*<y>)[^<]*(</y>\s*<z>)[^<]*(</z>)",
                r"\g<1>0.0000000000\g<2>0.0000000000\g<3>0.0000000000\g<4>", body)
            body = re.sub(
                r"(<size>\s*<width>)[^<]*(</width>\s*<height>)[^<]*(</height>)",
                rf"\g<1>{W}.000000\g<2>{H}.000000\g<3>", body)
        if nm == FADE_PANE:
            # ships scale x=128 (Tantric stretched an 8px bar across the pane)
            body = re.sub(
                r"(<scale>\s*<x>)[^<]*(</x>\s*<y>)[^<]*(</y>)",
                r"\g<1>1.0000000000\g<2>1.0000000000\g<3>", body)
            # invisible at rest; only the Start animation raises it
            body = re.sub(r"<alpha>\w+</alpha>", "<alpha>00</alpha>", body)
        return f'<tag type="{kind}"{attrs}>{body}</tag>'

    x = re.sub(TAGBLOCK, fix, x, flags=re.S)
    # The background is the only material we touch. Tantric tiled a 512-wide
    # texture across a 1024-wide pane, so it ships wrap_s=GX_MIRROR *and*
    # XScale=2.0 -- the texture matrix samples u over 0..2. Our image is the
    # full 832x456, so both must be neutralised or it renders mirrored and at
    # half width. Match any wrap mode, not just GX_REPEAT.
    def mat(m):
        body = m.group(2)
        if f'<texture name="{BG_TEX}">' in body or m.group(1) == FADE_MAT:
            body = re.sub(r"<wrap_s>\w+</wrap_s>", "<wrap_s>GX_CLAMP</wrap_s>", body)
            body = re.sub(r"<wrap_t>\w+</wrap_t>", "<wrap_t>GX_CLAMP</wrap_t>", body)
            body = re.sub(r"<XTrans>[^<]*</XTrans>", "<XTrans>0.0000000000</XTrans>", body)
            body = re.sub(r"<YTrans>[^<]*</YTrans>", "<YTrans>0.0000000000</YTrans>", body)
            body = re.sub(r"<XScale>[^<]*</XScale>", "<XScale>1.0000000000</XScale>", body)
            body = re.sub(r"<YScale>[^<]*</YScale>", "<YScale>1.0000000000</YScale>", body)
            body = re.sub(r"<Rotate>[^<]*</Rotate>", "<Rotate>0.0000000000</Rotate>", body)
        if m.group(1) == FADE_MAT:
            # BarsMaterial tints via its TEV registers (red fore/back colours);
            # reset both to BackgroundMaterial's neutral pair so white is white
            body = re.sub(r'<forecolor [^/]*/>', '<forecolor r="0" g="0" b="0" a="0" />', body)
            body = re.sub(r'<backcolor [^/]*/>', '<backcolor r="255" g="255" b="255" a="255" />', body)
        return f'<entries name="{m.group(1)}">{body}</entries>'

    return re.sub(r'<entries name="([^"]+)">(.*?)</entries>', mat, x, flags=re.S)


def flatten_scroll(x):
    """Zero the RLTS texture scroll so the background sits still."""
    def pane(m):
        name, body = m.group(1), m.group(3)
        if name == "BackgroundMaterial":
            body = re.sub(r"<value>[^<]*</value>", "<value>0.000000000000000</value>", body)
            body = re.sub(r"<blend>[^<]*</blend>", "<blend>0.000000000000000</blend>", body)
        return f'<pane name="{name}" type="{m.group(2)}">{body}</pane>'

    return re.sub(r'<pane name="([^"]+)" type="(\d)">(.*?)</pane>', pane, x, flags=re.S)


def add_fade(x):
    """Inject the white fade-in: an RLVC pane-alpha track (same type2=16 the
    icon uses) taking FADE_PANE 255 -> 0 over FADE_FRAMES. Zero tangents make
    GX interpolate it as a smoothstep; the value holds at 0 afterwards."""
    L = [f'\t\t\t\t<pane name="{FADE_PANE}" type="0">',
         '\t\t\t\t\t<tag type="RLVC">',
         '\t\t\t\t\t\t<entry type1="0" type2="16">']
    for f, v in ((0, 255), (FADE_FRAMES, 0)):
        L += ['\t\t\t\t\t\t\t<triplet>',
              f'\t\t\t\t\t\t\t\t<frame>{f:.15f}</frame>',
              f'\t\t\t\t\t\t\t\t<value>{v:.15f}</value>',
              '\t\t\t\t\t\t\t\t<blend>0.000000000000000</blend>',
              '\t\t\t\t\t\t\t</triplet>']
    L += ['\t\t\t\t\t\t</entry>', '\t\t\t\t\t</tag>', '\t\t\t\t</pane>']
    assert "</pai1>" in x
    return x.replace("</pai1>", "\n".join(L) + "\n\t\t\t</pai1>")


def main():
    arc = U8.load(unpack_lz77_imd5(open(f"{BUILD}/extracted/banner.bin", "rb").read()))

    open(os.path.join(BENZIN, "b_src.brlyt"), "wb").write(arc.get("/arc/blyt/banner.brlyt"))
    benzin("r", "b_src.brlyt", "b_src.xmlyt")
    x = fix_layout(open(os.path.join(BENZIN, "b_src.xmlyt")).read())
    open(os.path.join(BENZIN, "b_new.xmlyt"), "w").write(x)
    benzin("m", "b_new.xmlyt", "b_new.brlyt")
    arc.replace("/arc/blyt/banner.brlyt",
                open(os.path.join(BENZIN, "b_new.brlyt"), "rb").read())

    for name in ("banner_Start", "banner_Loop"):
        open(os.path.join(BENZIN, f"a_{name}.brlan"), "wb").write(arc.get(f"/arc/anim/{name}.brlan"))
        benzin("r", f"a_{name}.brlan", f"a_{name}.xmlan")
        a = flatten_scroll(open(os.path.join(BENZIN, f"a_{name}.xmlan")).read())
        if name == "banner_Start":
            a = add_fade(a)
        open(os.path.join(BENZIN, f"a_{name}_new.xmlan"), "w").write(a)
        benzin("m", f"a_{name}_new.xmlan", f"a_{name}_new.brlan")
        arc.replace(f"/arc/anim/{name}.brlan",
                    open(os.path.join(BENZIN, f"a_{name}_new.brlan"), "rb").read())

    im = Image.open(SRC).convert("RGB")
    assert im.size == (W, H), f"{SRC} is {im.size}, need {W}x{H}"
    stub = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
    white = Image.new("RGBA", (4, 4), (255, 255, 255, 255))
    kept = fade = 0
    for i, p in list(arc.paths()):
        if not p.endswith(".tpl"):
            continue
        if os.path.basename(p) == BG_TEX:
            arc.replace(p, T.build([(im, T.RGB565, None, im.size)]))
            kept += 1
        elif os.path.basename(p) == FADE_TEX:
            # solid white stretched over the whole pane -- the fade overlay
            arc.replace(p, T.build([(white, T.RGB5A3, None, white.size)]))
            fade += 1
        else:
            arc.replace(p, T.build([(stub, T.RGB5A3, None, stub.size)]))

    assert kept == 1, "background texture not found"
    assert fade == 1, "fade overlay texture not found"
    problems = arc.check_tree()
    assert not problems, problems
    raw = arc.to_bytes()
    packed = pack_lz77_imd5(raw)
    open(f"{BUILD}/out/banner_u8.bin", "wb").write(raw)
    open(f"{BUILD}/out/banner.bin", "wb").write(packed)
    print(f"banner.bin: {len(raw)} uncompressed -> {len(packed)} stored")
    print(f"  budget: {len(raw)/1388896:.1%} of FCEUGX's 1,388,896-byte banner")
    print(f"  textures: {len([1 for i,p in arc.paths() if p.endswith('.tpl')])} "
          f"(1 real, 1 white fade overlay, rest 4x4 stubs keeping their names)")
    print(f"  fade-in: {FADE_PANE} alpha 255 -> 0 over {FADE_FRAMES} frames "
          f"({FADE_FRAMES/60:.1f}s) in banner_Start")


if __name__ == "__main__":
    main()
