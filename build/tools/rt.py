import sys
sys.path.insert(0,'tools')
from wiilib import *
w = WAD.load(sys.argv[1])
app = w.contents[0]
off,names = imet_titles(app)
print("IMET at",hex(off),"md5 valid:",imet_verify(app),"titles:",names[:2])
u8off = app.find(b'\x55\xAA\x38\x2D')
print("U8 magic at",hex(u8off)," prefix preserved:",u8off)
outer = U8.load(app[u8off:])
rt = outer.to_bytes()
print("outer U8 round-trip byte-exact:", rt == app[u8off:], f"({len(rt)} vs {len(app)-u8off})")
for i,p in outer.paths(): print(f"   [{i}] {'D' if outer.nodes[i].is_dir else 'F'} {p:24} {len(outer.nodes[i].data)}")
for name in ("meta/banner.bin","meta/icon.bin","meta/sound.bin"):
    raw = outer.get(name)
    body = imd5_unwrap(raw)
    print(f"--- {name}: stored {len(raw)}  body magic {body[:4]}")
    if body[:4]==b'LZ77':
        dec = lz77_decompress(body[4:])
        re  = lz77_compress(dec)
        print(f"    uncompressed {len(dec)}   ours {len(re)+4} vs Tantric {len(body)}  ({(len(re)+4)/len(body)-1:+.2%})")
        print(f"    lz77 round-trip: {lz77_decompress(re)==dec}")
        inner = U8.load(dec)
        print(f"    inner U8 round-trip byte-exact: {inner.to_bytes()==dec}")
        print(f"    tree problems: {inner.check_tree() or 'none'}")
        print("    files:", [p for i,p in inner.paths() if not inner.nodes[i].is_dir][:8])
        print("     ...", len([1 for i,p in inner.paths() if not inner.nodes[i].is_dir]), "files total")
