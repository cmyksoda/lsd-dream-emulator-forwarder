import sys, hashlib, struct
sys.path.insert(0,'tools')
from wiilib import *
w = WAD.load(sys.argv[1])
print("titleID   ", w.title_id.hex(), repr(w.title_id[4:].decode('ascii',' replace')))
n = struct.unpack(">H", w.tmd[0x1DE:0x1E0])[0]
print("bootIndex ", struct.unpack(">H", w.tmd[0x1E0:0x1E2])[0], " numContents", n)
print("IOS       ", struct.unpack(">Q", w.tmd[0x184:0x18C])[0] & 0xffffffff)
for i,c in enumerate(w.contents):
    e=0x1E4+i*36
    want=w.tmd[e+16:e+36]; got=hashlib.sha1(c).digest()
    print(f"  content{i}: {len(c):>9} bytes  sha1 {'OK' if want==got else 'MISMATCH'}")
# trucha check on donor
print("tmd sha1[0]", hashlib.sha1(w.tmd[0x140:]).digest()[0], " tik sha1[0]", hashlib.sha1(w.tik[0x140:]).digest()[0])
