"""Assemble the final channel WAD from the pieces built by the other scripts.

Content 0 is the banner archive (IMET header + a U8 holding banner.bin,
icon.bin and sound.bin), content 1 is Tantric's untouched NAND loader stub,
content 2 is the patched forwarder.
"""

import hashlib
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(__file__))

from wiilib import U8, WAD, imd5_unwrap, imet_titles, imet_set, imet_verify, unpack_lz77_imd5

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BUILD = os.path.join(ROOT, "build")
DONOR = os.path.join(ROOT, "donor",
                     "FCE Ultra GX - FCEU [Tantric].wad")

TITLE_ID = "LSDE"
TITLE = "LSD Dream Emulator"
AUTHOR = "cmyksoda"
WAD_NAME = f"{TITLE} - {TITLE_ID} [{AUTHOR}].wad"
OUT = os.path.join(ROOT, WAD_NAME)


def main():
    w = WAD.load(DONOR)
    app = w.contents[0]
    u8off = app.find(b"\x55\xAA\x38\x2D")
    prefix, outer = app[:u8off], U8.load(app[u8off:])

    parts = {}
    for name in ("banner", "icon", "sound"):
        parts[name] = open(f"{BUILD}/out/{name}.bin", "rb").read()
        outer.replace(f"meta/{name}.bin", parts[name])

    problems = outer.check_tree()
    assert not problems, problems

    # IMET records the *uncompressed* payload size of each part
    sizes = (len(unpack_lz77_imd5(parts["icon"])),
             len(unpack_lz77_imd5(parts["banner"])),
             len(imd5_unwrap(parts["sound"])))
    app = prefix + outer.to_bytes()
    app = imet_set(app, TITLE, sizes)
    assert imet_verify(app), "IMET md5 failed"

    w.contents[0] = app
    w.contents[2] = open(f"{BUILD}/out/forwarder.app", "rb").read()
    w.set_title_id(TITLE_ID)
    size = w.save(OUT)

    print(f"wrote {OUT}")
    print(f"  {size:,} bytes")
    print(f"  title id   {w.title_id.hex()}  ({w.title_id[4:].decode()})")
    print(f"  IMET sizes icon={sizes[0]:,} banner={sizes[1]:,} sound={sizes[2]:,}")
    print(f"  title      {imet_titles(app)[1][1]!r}")
    for i, c in enumerate(w.contents):
        print(f"  content{i}   {len(c):,} bytes  sha1 {hashlib.sha1(c).hexdigest()[:16]}")


if __name__ == "__main__":
    main()
