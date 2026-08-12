import sys, os
sys.path.insert(0,'tools')
from wiilib import *
w=WAD.load("../mGBA-GX-Channel-Forwarder-Project/FCE Ultra GX - FCEU [Tantric].wad")
os.makedirs("extracted",exist_ok=True)
for i,c in enumerate(w.contents): open(f"extracted/content{i}.app","wb").write(c)
app=w.contents[0]; u8=U8.load(app[app.find(b'\x55\xAA\x38\x2D'):])
open("extracted/imet_prefix.bin","wb").write(app[:app.find(b'\x55\xAA\x38\x2D')])
for which in ("icon","banner","sound"):
    raw=u8.get(f"meta/{which}.bin")
    open(f"extracted/{which}.bin","wb").write(raw)
    if which=="sound":
        open("extracted/sound.bns","wb").write(imd5_unwrap(raw)); continue
    dec=unpack_lz77_imd5(raw)
    open(f"extracted/{which}_u8.bin","wb").write(dec)
    arc=U8.load(dec)
    d=f"extracted/{which}"; os.makedirs(d,exist_ok=True)
    for i,p in arc.paths():
        nd=arc.nodes[i]
        if nd.is_dir: continue
        fp=os.path.join(d,os.path.basename(p))
        open(fp,"wb").write(nd.data)
    print(which,"->",len(dec),"bytes uncompressed")
