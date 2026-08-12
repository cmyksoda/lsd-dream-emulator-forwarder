"""Patch Tantric's FCE Ultra GX forwarder (content 2) for this channel.

Four changes, all in place -- the DOL keeps its original 934,656-byte size:

1. 4:3 splash PNG at 0x081700  (165,683 bytes of room)
2. 16:9 splash PNG at 0x0A9E40 (157,270 bytes of room)
3. The app path. Tantric's `%s:/apps/fceugx/boot.dol` has only 3 spare bytes
   before the next string, so `LSD_Dream_Emulator` cannot be patched in place.
   The string is relocated into dead space and its single lis/addi reference
   is repointed.
4. Autoboot. WiiStation boots a game directly when it receives argc >= 3, with
   argv[1] giving the directory to search and argv[2] matched (by strcasestr)
   against its ISO list. Tantric's forwarder builds a one-entry command line,
   so the code that
   mallocs and strcpys it is replaced with a pointer to a static blob holding
   three NUL-separated strings. devkitPPC's build_argv() re-derives argc/argv
   from commandLine+length, so only those two fields have to be right.

Relocated data lives in the tail of the 16:9 splash region: libpng stops at
the IEND chunk, so bytes after the replacement PNG are never read.
"""

import os
import struct
import subprocess
import sys

from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BUILD = os.path.join(ROOT, "build")
SRC_DOL = os.path.join(ROOT, "mGBA-GX-Channel-Forwarder-Project",
                       "mGBA-GX-forwarder-working-dir", "Splash-reference",
                       "fceu_forwarder_content2.app")
SPLASH = os.path.join(ROOT, "images", "channel", "splash", "4_3_splash.png")

APP_DIR = "LSD_Dream_Emulator"
DEVICE = "sd:/"          # argv[0]: where the forwarder finds WiiStation's DOL
# argv[1] is NOT a device name. menu_loop() strncpy's it, whole, over the ISO
# browser's current directory (0x80015f5c: strncpy(isoDir->name, argv[1], 256)),
# so it has to be the full directory to search. The separate strstr(argv[1],
# "sd:/") at 0x800ee328 only decides SD vs USB, and a full path still satisfies
# it. Passing bare "sd:/" made WiiStation list the card root, match nothing,
# and fall through to loading a junk entry -- a black screen.
ISO_DIR = "sd:/wiisxrx/isos"   # argv[1]: matches WiiStation's own default
GAME_MATCH = "LSD"       # argv[2]: strcasestr'd against the ISO list entries

SPLASH43 = (0x081700, 165683)
SPLASH169 = (0x0A9E40, 157270)

DOFF, DADDR = 0x81700, 0x812b15e0        # data7: file offset, load address
PATH_REF_LIS, PATH_REF_LO = 0x8124b4b0, 0x8124b4c0
ARGV_START = 0x8124b5ac                  # strlen/malloc/strcpy block
ARGV_ARGC = 0x8124b5e4                   # li r0,1  -> li r0,3
ARGV_NOPS = (0x8124b5e0, 0x8124b5e8)     # buffer fix-ups that must not run
TOFF, TADDR, TSIZE = 0x100, 0x81230000, 0x815e0


def addr_of(fo):
    return DADDR + (fo - DOFF)


def file_of(addr):
    return DOFF + (addr - DADDR)


# ------------------------------------------------------------- tiny assembler

def lis(rd, imm):
    return (15 << 26) | (rd << 21) | (imm & 0xFFFF)


def addi(rd, ra, imm):
    return (14 << 26) | (rd << 21) | (ra << 16) | (imm & 0xFFFF)


def stw(rs, d, ra):
    return (36 << 26) | (rs << 21) | (ra << 16) | (d & 0xFFFF)


NOP = 0x60000000


def hi_lo(addr):
    """Split an address for a lis/addi pair (addi sign-extends its immediate)."""
    lo = addr & 0xFFFF
    hi = (addr >> 16) & 0xFFFF
    if lo & 0x8000:
        hi = (hi + 1) & 0xFFFF
    return hi, lo - 0x10000 if lo & 0x8000 else lo


# ------------------------------------------------------------------- splashes

# The replacement PNG must fit the original's byte budget and stay colortype 2:
# PNGU (Tantric's decoder) rejects palette PNGs outright. This scan is a dense
# dithered pattern that costs ~609 KB stored losslessly, so it has to be
# de-noised first. Kuwahara is edge-preserving, so the logo and text survive;
# despeckle then posterize flattens what is left without banding on noise.
# Ladder runs best-quality first and stops at the first entry that fits.
LADDER = [(2, 24), (2, 20), (2, 16), (3, 24), (3, 16), (4, 24), (4, 16), (5, 12)]


def encode_png(im, limit, tag):
    src = os.path.join(BUILD, "out", f"_splash_src_{tag}.png")
    dst = os.path.join(BUILD, "out", f"_splash_{tag}.png")
    im.save(src, "PNG")
    for kuwahara, posterize in LADDER:
        subprocess.run(
            ["magick", src, "-kuwahara", str(kuwahara), "-despeckle",
             "-posterize", str(posterize), "-depth", "8",
             "-define", "png:color-type=2",
             "-define", "png:compression-level=9", "-strip", f"PNG24:{dst}"],
            check=True, capture_output=True)
        b = open(dst, "rb").read()
        if len(b) <= limit:
            assert b[:8] == b"\x89PNG\r\n\x1a\n" and b[25] == 2, "not colortype 2"
            print(f"    (kuwahara {kuwahara}, posterize {posterize})")
            return b
    raise RuntimeError(f"no splash setting fits {limit} bytes")


def make_16_9(im):
    """Pre-squash to 75% width so the Wii's 4:3->16:9 stretch restores the
    aspect, then fill the 80px side bars by replicating each row's edge pixel."""
    w, h = im.size
    inner = im.resize((int(w * 0.75), h), Image.LANCZOS)
    out = Image.new("RGB", (w, h))
    x0 = (w - inner.width) // 2
    out.paste(inner, (x0, 0))
    px, ip = out.load(), inner.load()
    for y in range(h):
        left, right = ip[0, y], ip[inner.width - 1, y]
        for x in range(x0):
            px[x, y] = left
        for x in range(x0 + inner.width, w):
            px[x, y] = right
    return out


def main():
    d = bytearray(open(SRC_DOL, "rb").read())
    orig_len = len(d)

    im = Image.open(SPLASH).convert("RGB")
    assert im.size == (640, 480), f"splash is {im.size}, need 640x480"

    png43 = encode_png(im, SPLASH43[1], "43")
    png169 = encode_png(make_16_9(im), SPLASH169[1], "169")
    for (off, room), png, name in ((SPLASH43, png43, "4:3"), (SPLASH169, png169, "16:9")):
        d[off:off + room] = png + b"\0" * (room - len(png))
        print(f"  {name} splash: {len(png)} bytes into {room} "
              f"({room - len(png)} left null-padded)")

    # ---- relocated data, parked in the dead tail of the 16:9 region
    path_str = f"%s:/apps/{APP_DIR}/boot.dol\0".encode()
    cmdline = (f"{DEVICE}apps/{APP_DIR}/boot.dol\0".encode()
               + ISO_DIR.encode() + b"\0" + GAME_MATCH.encode() + b"\0" + b"\0")
    blob = path_str + cmdline
    blob_off = (SPLASH169[0] + SPLASH169[1] - len(blob) - 16) & ~0xF
    assert blob_off > SPLASH169[0] + len(png169), "blob would overwrite the PNG"
    d[blob_off:blob_off + len(blob)] = blob
    path_addr = addr_of(blob_off)
    cmd_addr = addr_of(blob_off + len(path_str))
    print(f"  relocated data at file 0x{blob_off:x} / addr 0x{path_addr:08x} "
          f"({len(blob)} bytes)")
    print(f"    path fmt : {path_str!r}")
    print(f"    cmdline  : {cmdline!r}  (length {len(cmdline)})")

    def poke(addr, word):
        fo = TOFF + (addr - TADDR)
        struct.pack_into(">I", d, fo, word)

    # ---- 3. repoint the app-path string
    hi, lo = hi_lo(path_addr)
    old_lis = struct.unpack_from(">I", d, TOFF + (PATH_REF_LIS - TADDR))[0]
    poke(PATH_REF_LIS, lis((old_lis >> 21) & 31, hi))
    old_lo = struct.unpack_from(">I", d, TOFF + (PATH_REF_LO - TADDR))[0]
    poke(PATH_REF_LO, addi((old_lo >> 21) & 31, (old_lo >> 16) & 31, lo))

    # ---- 4. static three-argument command line
    hi, lo = hi_lo(cmd_addr)
    seq = [lis(9, hi), addi(9, 9, lo), stw(9, 20, 1),
           addi(0, 0, len(cmdline)), stw(0, 24, 1),
           NOP, NOP, NOP, NOP]
    for i, w in enumerate(seq):
        poke(ARGV_START + i * 4, w)
    for a in ARGV_NOPS:
        poke(a, NOP)
    poke(ARGV_ARGC, addi(0, 0, 3))       # li r0,3 -> argc

    assert len(d) == orig_len, f"size changed: {len(d)} != {orig_len}"
    os.makedirs(f"{BUILD}/out", exist_ok=True)
    open(f"{BUILD}/out/forwarder.app", "wb").write(bytes(d))
    print(f"  forwarder.app: {len(d)} bytes (unchanged)")
    print(f"  looks for: {DEVICE}apps/{APP_DIR}/boot.dol")
    print(f"  autoboot : argv[1]={ISO_DIR!r} argv[2]={GAME_MATCH!r}")


if __name__ == "__main__":
    main()
