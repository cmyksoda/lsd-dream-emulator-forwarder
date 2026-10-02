import sys, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)
from wiilib import *
import tpl as T

w = WAD.load(os.path.join(ROOT, "donor", "FCE Ultra GX - FCEU [Tantric].wad"))
app = w.contents[0]
u8 = U8.load(app[app.find(b'\x55\xAA\x38\x2D'):])

for which in ("icon", "banner"):
    arc = U8.load(unpack_lz77_imd5(u8.get(f"meta/{which}.bin")))
    print(f"===== {which}.bin")
    tot = 0
    for i, p in arc.paths():
        nd = arc.nodes[i]
        if not p.endswith(".tpl"):
            if not nd.is_dir:
                print(f"   {p}  {len(nd.data)}b")
            continue
        for t in T.parse(nd.data):
            tot += len(nd.data)
            print(f"   {p:34} {t['w']}x{t['h']:<4} {T.NAMES[t['fmt']]:7} "
                  f"pal={t['npal']:<4} {len(nd.data)}b")
    print("   tpl bytes total:", tot)
