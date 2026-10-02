import sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
DONOR = os.path.join(ROOT, "donor", "FCE Ultra GX - FCEU [Tantric].wad")
OUT = os.path.join(ROOT, "build", "extracted")
sys.path.insert(0, HERE)
from wiilib import *

w = WAD.load(DONOR)
os.makedirs(OUT, exist_ok=True)
for i, c in enumerate(w.contents):
    open(os.path.join(OUT, f"content{i}.app"), "wb").write(c)

app = w.contents[0]
u8 = U8.load(app[app.find(b'\x55\xAA\x38\x2D'):])
open(os.path.join(OUT, "imet_prefix.bin"), "wb").write(app[:app.find(b'\x55\xAA\x38\x2D')])

for which in ("icon", "banner", "sound"):
    raw = u8.get(f"meta/{which}.bin")
    open(os.path.join(OUT, f"{which}.bin"), "wb").write(raw)
    if which == "sound":
        open(os.path.join(OUT, "sound.bns"), "wb").write(imd5_unwrap(raw))
        continue
    dec = unpack_lz77_imd5(raw)
    open(os.path.join(OUT, f"{which}_u8.bin"), "wb").write(dec)
    arc = U8.load(dec)
    d = os.path.join(OUT, which)
    os.makedirs(d, exist_ok=True)
    for i, p in arc.paths():
        nd = arc.nodes[i]
        if nd.is_dir:
            continue
        fp = os.path.join(d, os.path.basename(p))
        open(fp, "wb").write(nd.data)
    print(which, "->", len(dec), "bytes uncompressed")
