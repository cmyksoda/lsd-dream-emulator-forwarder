"""Pre-install verification. Reads the finished WAD back off disk and checks
everything that is known to matter -- including the U8 directory parent
indices, which is the one check that catches the System Menu brick that
U8.FromDirectory used to cause, and the banner memory budget, which is the
one that no structural check catches.
"""

import hashlib
import os
import re
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(__file__))

import tpl as T
from wiilib import U8, WAD, imd5_unwrap, imet_titles, imet_verify, unpack_lz77_imd5

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BENZIN = os.path.join(os.path.dirname(__file__), "benzin")
BANNER_BUDGET = 1388896          # FCEUGX's banner; two ~2.5MB banners freeze the Menu

# HARD limit, not a budget. The System Menu compares the icon's uncompressed
# size against 0x19000 at 0x81352488 and refuses to allocate the buffer if it
# is larger; its LZ77 decompressor then writes into address 0 and the Menu
# dies right after the Health & Safety screen. Confirmed by bricking Dolphin
# twice with a 198,976-byte icon. Tantric's are 91,328 / 94,432 / 97,664.
ICON_CAP = 0x19000               # 102,400 bytes

# Actual render targets. Art larger than this is centre-cropped, not scaled.
#
# These are the 16:9 sizes. The Menu renders an anamorphic 640x480 framebuffer,
# so a widescreen TV shows 4/3 more horizontal layout units than the 4:3
# viewport (icon 128x96 -> 170.67, banner 608x456 -> 810.67); the height never
# changes. Panes sized for 4:3 get black side bars on a 16:9 set, so both are
# authored at the next round width up and 4:3 shows their centre.
VIEWPORT = {"icon": (176, 96), "banner": (832, 456)}
SAFE_43 = {"icon": 128, "banner": 608}

TITLE_NAME = "LSD Dream Emulator"

# Title IDs that must not be collided with (system titles + Tantric's channels)
RESERVED = {b"HAEA", b"HABA", b"HACA", b"HAEA", b"HAFA", b"HAAA", b"HABK",
            b"FCEU", b"9XGX", b"VBAG", b"GBGX", b"HCZA", b"HAYA", b"HAZA"}

ok = True


def check(cond, label, detail=""):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    if not cond:
        ok = False
    return cond


def benzin_rip(data, stem, ext):
    src = os.path.join(BENZIN, f"vfy_{stem}.{ext}")
    dst = os.path.join(BENZIN, f"vfy_{stem}.xml{ext[2:]}")
    open(src, "wb").write(data)
    subprocess.run(["wine", "BENZIN.EXE", "r", os.path.basename(src), os.path.basename(dst)],
                   cwd=BENZIN, capture_output=True, env={**os.environ, "WINEDEBUG": "-all"})
    return open(dst, errors="replace").read()


def sections(d):
    """Section magics of a brlyt/brlan, in order."""
    hlen, n = struct.unpack(">HH", d[12:16])
    out, o = [], hlen
    for _ in range(n):
        out.append(d[o:o + 4].decode("ascii", "replace"))
        o += struct.unpack(">I", d[o + 4:o + 8])[0]
    return out


def check_arc(arc, kind, donor, fade=None):
    """fade = (pane, material, texture, frames): a white overlay pane that
    rests at static alpha 00 and is driven 255 -> 0 by the Start animation."""
    print(f"\n-- {kind}.bin internals")
    check(not arc.check_tree(), "U8 directory parent indices sane",
          str(arc.check_tree() or ""))

    # A minimal hand-built brlyt that omitted fnl1/grp1 bricked the System Menu
    # (black screen after Health & Safety). The Menu dereferences the root
    # group unconditionally, so the section list must match the working donor.
    for p in ("/arc/blyt/%s.brlyt" % kind,):
        ours, theirs = sections(arc.get(p)), sections(donor.get(p))
        check(ours == theirs, f"{kind}.brlyt section list matches donor",
              f"{len(ours)} sections" if ours == theirs
              else f"missing {[s for s in theirs if s not in ours]}")
    check("grp1" in sections(arc.get(f"/arc/blyt/{kind}.brlyt")),
          f"{kind}.brlyt has a grp1 root group")
    for i, p in arc.paths():
        if p.endswith(".brlan"):
            check(sections(arc.get(p)) == sections(donor.get(p)),
                  f"{os.path.basename(p)} section list matches donor")
    files = {os.path.basename(p) for i, p in arc.paths() if not arc.nodes[i].is_dir}
    tpls = {f for f in files if f.endswith(".tpl")}

    lyt = benzin_rip(arc.get(f"/arc/blyt/{kind}.brlyt"), f"{kind}_lyt", "brlyt")
    txl = re.findall(r"<name>([^<]+\.tpl)</name>", lyt)
    mats = set(re.findall(r'<entries name="([^"]+)"', lyt))
    panes = set(re.findall(r'<tag type="(?:pan1|pic1|txt1|wnd1)" name="([^"]*)"', lyt))
    check(set(txl) <= tpls, "every texture the layout names exists",
          f"missing {set(txl)-tpls}" if set(txl) - tpls else f"{len(txl)} textures")
    matrefs = set(re.findall(r'<material name="([^"]+)" />', lyt))
    check(matrefs <= mats, "every pane's material is defined",
          f"missing {matrefs-mats}" if matrefs - mats else f"{len(matrefs)} refs")
    # Pane names live in a fixed 16-byte field that spills into the 8-byte
    # userdata field. Tantric's own panes already do this (BackgroundPicture ->
    # userdata "e") and work fine, so only flag overflows we introduced.
    spill = lambda t: {n for n, u in re.findall(
        r'<tag type="(?:pan1|pic1)" name="([^"]*)" userdata="([^"]*)"', t) if u}
    dlyt = benzin_rip(donor.get(f"/arc/blyt/{kind}.brlyt"), f"{kind}_dlyt", "brlyt")
    new_spill = spill(lyt) - spill(dlyt)
    check(not new_spill, "no pane name we added overflows its 16-byte field",
          f"{sorted(new_spill)}" if new_spill else
          f"{len(spill(lyt))} inherited from donor")

    # Render geometry. Panes must be exactly the 16:9 viewport (icon 176x96,
    # banner 832x456): larger art gets silently centre-cropped, which is what
    # made the first working build look "zoomed", and smaller art leaves black
    # side bars on a widescreen set. And Tantric's BackgroundMaterial tiles a
    # half-width texture via GX_MIRROR + XScale=2.0, so any full-bleed
    # replacement needs an identity texture matrix and CLAMP.
    vw, vh = VIEWPORT[kind]
    vis = [(n, b) for n, _u, b in re.findall(
        r'<tag type="pic1" name="([^"]*)" userdata="([^"]*)"((?:[^>]*[^/>])?>.*?)</tag>',
        lyt, re.S) if "<visible>01</visible>" in b]
    for name, body in vis:
        sz = re.search(r"<width>([\d.]+)</width>\s*<height>([\d.]+)</height>", body)
        got = (float(sz.group(1)), float(sz.group(2)))
        check(got == (vw, vh), f"{name} matches the {kind} viewport",
              f"{got[0]:.0f}x{got[1]:.0f} vs {vw}x{vh}")
        al = re.search(r"<alpha>(\w+)</alpha>", body).group(1)
        if fade and name == fade[0]:
            # the fade overlay must be invisible at rest -- only the Start
            # animation raises it, so a rebind can never leave white stuck on
            check(al == "00", f"{name} (fade overlay) rests at alpha 00", al)
        else:
            check(al == "ff", f"{name} is at full alpha", al)
    shown = {re.search(r'<material name="([^"]+)"', b).group(1) for _, b in vis
             if re.search(r'<material name="([^"]+)"', b)}
    for m in re.finditer(r'<entries name="([^"]+)">(.*?)</entries>', lyt, re.S):
        if m.group(1) not in shown:
            continue
        b = m.group(2)
        wrap = re.search(r"<wrap_s>(\w+)</wrap_s>\s*<wrap_t>(\w+)</wrap_t>", b)
        srt = re.search(r"<XTrans>([-\d.]+)</XTrans>\s*<YTrans>([-\d.]+)</YTrans>"
                        r"\s*<Rotate>([-\d.]+)</Rotate>\s*<XScale>([-\d.]+)</XScale>"
                        r"\s*<YScale>([-\d.]+)</YScale>", b)
        check(wrap.group(1) == "GX_CLAMP" and wrap.group(2) == "GX_CLAMP",
              f"{m.group(1)} clamps (no tiling/mirroring)",
              f"{wrap.group(1)}/{wrap.group(2)}")
        vals = [float(srt.group(i)) for i in (1, 2, 3, 4, 5)]
        check(vals == [0.0, 0.0, 0.0, 1.0, 1.0],
              f"{m.group(1)} has an identity texture matrix",
              f"trans=({vals[0]},{vals[1]}) scale=({vals[3]},{vals[4]})")

    anims = [p for i, p in arc.paths() if p.endswith(".brlan")]
    ripped = {}
    for ap in anims:
        an = benzin_rip(arc.get(ap), os.path.basename(ap)[:-6] + "_an", "brlan")
        ripped[os.path.basename(ap)] = an
        apanes = set(re.findall(r'<pane name="([^"]+)" type="0"', an))
        amats = set(re.findall(r'<pane name="([^"]+)" type="1"', an))
        atimg = set(re.findall(r'<timg name="([^"]+)" />', an))
        check(apanes <= panes, f"{os.path.basename(ap)}: animated panes exist in layout",
              f"missing {apanes-panes}" if apanes - panes else f"{len(apanes)} panes")
        check(amats <= mats, f"{os.path.basename(ap)}: animated materials exist",
              f"missing {amats-mats}" if amats - mats else "none")
        check(atimg <= tpls, f"{os.path.basename(ap)}: RLTP textures exist",
              f"missing {atimg-tpls}" if atimg - tpls else "none")

    if fade:
        fpane, fmat, ftex, fframes = fade
        start = ripped.get(f"{kind}_Start.brlan", "")
        blk = re.search(rf'<pane name="{fpane}" type="0">(.*?)</pane>', start, re.S)
        keys = []
        if blk and "RLVC" in blk.group(1):
            keys = [(float(f), float(v)) for f, v in re.findall(
                r"<frame>([\d.]+)</frame>\s*<value>([\d.]+)</value>", blk.group(1))]
        check(keys and keys[0] == (0.0, 255.0) and keys[-1] == (float(fframes), 0.0),
              f"Start drives {fpane} 255 -> 0 over {fframes} frames ({fframes/60:.1f}s)",
              str(keys))
        loop = ripped.get(f"{kind}_Loop.brlan", "")
        check(f'<pane name="{fpane}"' not in loop,
              f"Loop leaves {fpane} alone (fade stays finished)")
        # the overlay texture must be solid opaque white, or the "fade from
        # white" is a fade from whatever colour is actually in the tile
        info = T.parse(arc.get(f"/arc/timg/{ftex}"))[0]
        px = T.decode(arc.get(f"/arc/timg/{ftex}")[info["data_off"]:],
                      info["w"], info["h"], info["fmt"]).getdata()
        check(all(p == (255, 255, 255, 255) for p in px),
              f"{ftex} is solid opaque white", f"{info['w']}x{info['h']}")
        fm = re.search(rf'<entries name="{fmat}">(.*?)</entries>', lyt, re.S).group(1)
        fore = re.search(r'<forecolor r="(\d+)" g="(\d+)" b="(\d+)" a="(\d+)"', fm).groups()
        back = re.search(r'<backcolor r="(\d+)" g="(\d+)" b="(\d+)" a="(\d+)"', fm).groups()
        check(fore == ("0", "0", "0", "0") and back == ("255", "255", "255", "255"),
              f"{fmat} tint registers are neutral", f"fore={fore} back={back}")

    for i, p in arc.paths():
        if not p.endswith(".tpl"):
            continue
        for t in T.parse(arc.nodes[i].data):
            check(t["w"] % 4 == 0 and t["h"] % 4 == 0,
                  f"{os.path.basename(p)} dimensions 4-aligned",
                  f"{t['w']}x{t['h']} {T.NAMES[t['fmt']]}")


def main():
    path = sys.argv[1]
    print(f"== {os.path.basename(path)}  ({os.path.getsize(path):,} bytes)")

    w = WAD.load(path)
    print("\n-- container")
    n = struct.unpack(">H", w.tmd[0x1DE:0x1E0])[0]
    for i, c in enumerate(w.contents):
        e = 0x1E4 + i * 36
        check(hashlib.sha1(c).digest() == w.tmd[e + 16:e + 36],
              f"content{i} SHA-1 matches TMD", f"{len(c):,} bytes")
    check(hashlib.sha1(w.tmd[0x140:]).digest()[0] == 0, "TMD is fakesigned (trucha)")
    check(hashlib.sha1(w.tik[0x140:]).digest()[0] == 0, "ticket is fakesigned (trucha)")
    tid = w.title_id
    check(tid[:4] == bytes.fromhex("00010001"), "title type is 0x00010001 (channel)")
    check(tid[4:] not in RESERVED, "channel ID unused by system/known homebrew",
          tid[4:].decode())
    check(w.tik[0x1DC:0x1E4] == tid, "ticket title ID matches TMD")
    boot = struct.unpack(">H", w.tmd[0x1E0:0x1E2])[0]
    check(boot == 1, "boot index points at the NAND loader stub", f"index {boot}")
    ios = struct.unpack(">Q", w.tmd[0x184:0x18C])[0] & 0xFFFFFFFF
    print(f"  [info] boot IOS {ios}, {n} contents")

    print("\n-- banner archive (content 0)")
    app = w.contents[0]
    check(imet_verify(app), "IMET md5 valid")
    off, names = imet_titles(app)
    filled = [x for x in names if x]
    check(len(filled) == 10 and len(set(filled)) == 1,
          "all 10 language slots set", repr(filled[0]) if filled else "")
    u8 = U8.load(app[app.find(b"\x55\xAA\x38\x2D"):])
    check(not u8.check_tree(), "outer U8 tree sane")
    sizes = struct.unpack(">III", app[off + 0x0C:off + 0x18])
    parts = {k: u8.get(f"meta/{k}.bin") for k in ("icon", "banner", "sound")}
    actual = (len(unpack_lz77_imd5(parts["icon"])), len(unpack_lz77_imd5(parts["banner"])),
              len(imd5_unwrap(parts["sound"])))
    check(sizes == actual, "IMET sizes match the real payloads", f"{sizes}")
    check(actual[0] <= ICON_CAP, "icon within the System Menu's HARD 0x19000 cap",
          f"{actual[0]:,} / {ICON_CAP:,} ({actual[0]/ICON_CAP:.0%})")
    check(actual[1] <= BANNER_BUDGET, "banner within the Wii Menu memory budget",
          f"{actual[1]:,} / {BANNER_BUDGET:,} ({actual[1]/BANNER_BUDGET:.0%})")

    dw = WAD.load(os.path.join(ROOT, "donor",
                               "FCE Ultra GX - FCEU [Tantric].wad"))
    dapp = dw.contents[0]
    dono = U8.load(dapp[dapp.find(b"\x55\xAA\x38\x2D"):])
    for kind in ("icon", "banner"):
        check_arc(U8.load(unpack_lz77_imd5(parts[kind])), kind,
                  U8.load(unpack_lz77_imd5(dono.get(f"meta/{kind}.bin"))),
                  fade=("BarsPicture", "BarsMaterial", "Bars.tpl", 180)
                       if kind == "banner" else None)

    print("\n-- banner sound")
    b = imd5_unwrap(parts["sound"])
    check(b[:4] == b"BNS ", "BNS magic")
    check(struct.unpack(">I", b[8:12])[0] == len(b), "BNS fileSize matches")
    i = b.find(b"INFO")
    total = struct.unpack(">I", b[i + 20:i + 24])[0]
    dat = b.find(b"DATA")
    dsz = struct.unpack(">I", b[dat + 4:dat + 8])[0]
    check(b[i + 9] == 0, "loop flag off (plays once)")
    check(abs(total / (dsz - 8) - 1.75) < 1e-6, "DSP ADPCM ratio is 1.75 samples/byte")
    print(f"  [info] {total:,} samples @ {struct.unpack('>H', b[i+12:i+14])[0]} Hz "
          f"= {total/struct.unpack('>H', b[i+12:i+14])[0]:.2f}s mono")

    print("\n-- forwarder (content 2)")
    d = w.contents[2]
    check(len(d) == 934656, "size unchanged from Tantric's", f"{len(d):,}")
    DOFF, DADDR = 0x81700, 0x812b15e0
    TOFF, TADDR = 0x100, 0x81230000
    fo = lambda a: DOFF + (a - DADDR)
    to = lambda a: TOFF + (a - TADDR)

    def lis_addi(a_hi, a_lo):
        """Recover the address a lis/addi pair builds, so the checks below
        follow the pointers the code actually uses rather than baked-in
        offsets that move whenever the relocated blob changes size."""
        hi = struct.unpack(">H", d[to(a_hi) + 2:to(a_hi) + 4])[0]
        lo = struct.unpack(">h", d[to(a_lo) + 2:to(a_lo) + 4])[0]
        return ((hi << 16) + lo) & 0xFFFFFFFF

    path_addr = lis_addi(0x8124b4b0, 0x8124b4c0)
    cmd_addr = lis_addi(0x8124b5ac, 0x8124b5b0)
    pathstr = d[fo(path_addr):d.find(b"\0", fo(path_addr))].decode()
    check(pathstr == "%s:/apps/LSD_Dream_Emulator/boot.dol", "app path string", pathstr)
    WANT_ARGS = ["sd:/apps/LSD_Dream_Emulator/boot.dol", "sd:/wiisxrx/isos", "LSD"]
    CMDLEN = sum(len(a) + 1 for a in WANT_ARGS) + 1
    check(cmd_addr == path_addr + len(pathstr) + 1,
          "command line sits right after the path string",
          f"0x{cmd_addr:08x} vs 0x{path_addr:08x}")
    blob = d[fo(cmd_addr):fo(cmd_addr) + CMDLEN]
    args = [x.decode() for x in blob.split(b"\0") if x]
    check(args == WANT_ARGS, "command line holds the 3 autoboot arguments", str(args))
    check(blob[-2:] == b"\0\0", "command line double-NUL terminated")
    # argv[1] is strncpy'd over WiiStation's ISO directory, so it must be a real
    # directory containing "sd:/" -- not a bare device name. See patch_forwarder.
    check(args[1].startswith("sd:/") and "/" in args[1][4:],
          "argv[1] is a full ISO directory, not a bare device", args[1])
    # The length the forwarder stores must match, or build_argv() mis-splits.
    stored = struct.unpack(">H", d[to(0x8124b5b8) + 2:to(0x8124b5b8) + 4])[0]
    check(stored == CMDLEN, "forwarder's stored command-line length",
          f"{stored} (expected {CMDLEN})")
    for name, (o, room) in (("4:3", (0x081700, 165683)), ("16:9", (0x0A9E40, 157270))):
        png = d[o:o + room]
        end = png.find(b"IEND") + 8
        check(png[:8] == b"\x89PNG\r\n\x1a\n" and png[25] == 2,
              f"{name} splash is a colortype-2 PNG", f"{end:,} bytes used of {room:,}")
        wpx, hpx = struct.unpack(">II", png[16:24])
        check((wpx, hpx) == (640, 480), f"{name} splash is 640x480", f"{wpx}x{hpx}")
    check(b"fceugx" in d and True, "note: dead original path string left in place (0 refs)")

    # The SD-card app folder ships alongside the WAD. The Homebrew Channel
    # silently falls back to the directory name and "no description available"
    # if meta.xml will not parse -- a raw '&' did exactly that here.
    print("\n-- apps/ meta.xml (Homebrew Channel)")
    import xml.etree.ElementTree as ET
    meta = os.path.join(ROOT, "SD", "apps", "LSD_Dream_Emulator", "meta.xml")
    raw = open(meta, "rb").read()
    check(all(b < 128 for b in raw), "meta.xml is pure ASCII",
          "HBC's parser is fragile with multi-byte characters")
    bad = re.findall(rb"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", raw)
    check(not bad, "no unescaped & in meta.xml", f"{len(bad)} found" if bad else "")
    try:
        root = ET.fromstring(raw.decode("ascii"))
        parsed = True
    except Exception as e:
        parsed = False
        print(f"  [FAIL] meta.xml is well-formed XML  {e}")
    check(parsed, "meta.xml is well-formed XML")
    if parsed:
        check(root.findtext("name") == TITLE_NAME, "meta.xml name",
              repr(root.findtext("name")))
        args = [a.text for a in root.findall("./arguments/arg")]
        check(args == ["sd:/wiisxrx/isos", "LSD"],
              "meta.xml passes the autoboot arguments", str(args))

    print("\n" + ("== ALL CHECKS PASSED" if ok else "== FAILURES ABOVE"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
