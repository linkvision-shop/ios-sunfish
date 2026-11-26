#!/usr/bin/env python3
"""Pack a device-tree DIRECTORY (adb pull /sys/firmware/devicetree/base <dir>) into a .dtb.
Directories become nodes, files become properties. The sysfs pseudo-file 'name' is skipped.
usage: dir2fdt.py <dir> <out.dtb>   then: fdt2profile.py <out.dtb>"""
import os, struct, sys

def pack(root):
    strs, soff = bytearray(), {}
    def sname(k):
        if k not in soff: soff[k] = len(strs); strs.extend(k.encode() + b'\0')
        return soff[k]
    pad = lambda b: b + b'\0' * (-len(b) % 4)
    def node(path, name):
        out = struct.pack('>I', 1) + pad(name.encode() + b'\0')
        ents = sorted(os.listdir(path))
        for e in ents:
            p = os.path.join(path, e)
            if os.path.isfile(p) and e != 'name':
                v = open(p, 'rb').read()
                out += struct.pack('>III', 3, len(v), sname(e)) + pad(v)
        for e in ents:
            if os.path.isdir(os.path.join(path, e)): out += node(os.path.join(path, e), e)
        return out + struct.pack('>I', 2)
    st = node(root, '') + struct.pack('>I', 9)
    off_s = 56; off_str = off_s + len(st); total = off_str + len(strs)
    return struct.pack('>10I', 0xd00dfeed, total, off_s, off_str, 40, 17, 16, 0, len(strs), len(st)) + b'\0' * 16 + st + bytes(strs)

if __name__ == '__main__':
    if len(sys.argv) != 3 or not os.path.isdir(sys.argv[1]): sys.exit(__doc__)
    open(sys.argv[2], 'wb').write(pack(sys.argv[1])); print('wrote', sys.argv[2])
