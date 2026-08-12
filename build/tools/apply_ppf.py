"""Apply a PPF3.0 patch, so the ROM can be patched on Linux without the
Windows PPF-o-Matic GUI.

PPF3.0 layout:
    0x00  "PPF30"
    0x05  encoding method (2 = PPF3.0)
    0x06  description, 50 bytes
    0x38  image type   (0 = BIN)
    0x39  block check  (1 = a 1024-byte validation block follows the header)
    0x3A  undo data    (1 = each record carries the original bytes too)
    0x3B  dummy
    then records: u64 LE offset, u8 length, length bytes of new data,
                  followed by length bytes of undo data when undo is set.
    An optional "@BEGIN_FILE_ID.DIZ" trailer may follow the records.
"""

import os
import shutil
import struct
import sys


def parse(ppf):
    assert ppf[:5] == b"PPF30", f"not a PPF3.0 patch: {ppf[:5]!r}"
    assert ppf[5] == 2, f"unexpected encoding method {ppf[5]}"
    desc = ppf[6:56].rstrip(b" \0").decode("latin-1")
    imagetype, blockcheck, undo = ppf[56], ppf[57], ppf[58]
    o = 60 + (1024 if blockcheck else 0)
    end = len(ppf)
    diz = ppf.find(b"@BEGIN_FILE_ID.DIZ")
    if diz != -1:
        end = diz
    records = []
    while o + 9 <= end:
        off = struct.unpack("<Q", ppf[o:o + 8])[0]
        n = ppf[o + 8]
        o += 9
        data = ppf[o:o + n]
        o += n
        if undo:
            o += n
        records.append((off, data))
    return dict(desc=desc, imagetype=imagetype, blockcheck=blockcheck,
                undo=undo, records=records)


def apply(src, ppf_path, dst):
    ppf = open(ppf_path, "rb").read()
    info = parse(ppf)
    print(f"  patch     : {info['desc']}")
    print(f"  records   : {len(info['records']):,}  "
          f"(blockcheck={info['blockcheck']} undo={info['undo']})")
    total = sum(len(d) for _, d in info["records"])
    hi = max(off + len(d) for off, d in info["records"])
    print(f"  changes   : {total:,} bytes, highest offset 0x{hi:x}")
    size = os.path.getsize(src)
    assert hi <= size, f"patch writes past EOF ({hi} > {size}) -- wrong source image"
    if os.path.abspath(src) != os.path.abspath(dst):
        shutil.copyfile(src, dst)
    with open(dst, "r+b") as f:
        for off, data in info["records"]:
            f.seek(off)
            f.write(data)
    return info


if __name__ == "__main__":
    src, ppf_path, dst = sys.argv[1], sys.argv[2], sys.argv[3]
    print(f"applying to {os.path.basename(dst)}")
    apply(src, ppf_path, dst)
    print("  done")
