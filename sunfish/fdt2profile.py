#!/usr/bin/env python3
"""Read a flattened device tree (dtb) and emit port CANDIDATES as JSON.

Input : /sys/firmware/fdt pulled from the phone (recovery) -- NOT the stock boot.img dtb,
        which lacks the dtbo fixups (see ios-sweet NOTES.md: "live reserved-memory").
Output: a profile with provenance paths. Everything is a candidate read from that tree;
        nothing here is verified on hardware. Missing facts stay null.
usage : fdt2profile.py live.fdt [-o sunfish.candidates.json]
"""
import argparse, hashlib, json, re, struct, sys

def parse(b):
    (magic, total, off_s, off_str, _r, _v, _l, _bc, sz_str, sz_s) = struct.unpack_from('>10I', b, 0)
    if magic != 0xd00dfeed: raise SystemExit('error: not a dtb (bad magic)')
    if total > len(b): raise SystemExit('error: dtb truncated (%d > %d bytes)' % (total, len(b)))
    strs, pos, end, stack, root = b[off_str:off_str + sz_str], off_s, off_s + sz_s, [], None
    while pos < end:
        tok = struct.unpack_from('>I', b, pos)[0]; pos += 4
        if tok == 1:
            nul = b.index(b'\0', pos); name = b[pos:nul].decode(); pos = (nul + 4) & ~3
            n = {'name': name, 'props': {}, 'kids': [], 'parent': stack[-1] if stack else None}
            if stack: stack[-1]['kids'].append(n)
            else: root = n
            stack.append(n)
        elif tok == 2: stack.pop()
        elif tok == 3:
            ln, no = struct.unpack_from('>II', b, pos); pos += 8
            stack[-1]['props'][strs[no:strs.index(b'\0', no)].decode()] = b[pos:pos + ln]
            pos = (pos + ln + 3) & ~3
        elif tok == 4: continue
        elif tok == 9: break
        else: raise SystemExit('error: bad token %#x at %#x' % (tok, pos - 4))
    if root is None or stack: raise SystemExit('error: unbalanced node structure')
    return root

def walk(n, path=''):
    p = (path + '/' + n['name']) if n['name'] else '/'
    yield p, n
    for k in n['kids']: yield from walk(k, p if p != '/' else '')

def u32s(v): return list(struct.unpack('>%dI' % (len(v) // 4), v[:len(v) // 4 * 4]))
def strs(n, k): return [s.decode() for s in n['props'].get(k, b'').split(b'\0') if s]
def hx(x): return '0x%x' % x
def cells(n):
    par = n['parent']
    if par is None: return 2, 1
    g = lambda k, d: struct.unpack('>I', par['props'][k][:4])[0] if k in par['props'] else d
    return g('#address-cells', 2), g('#size-cells', 1)
def reg(n):
    ac, sc = cells(n); w = u32s(n['props'].get('reg', b'')); out = []
    for i in range(0, len(w) - ac - sc + 1, ac + sc):
        a = 0
        for x in w[i:i + ac]: a = (a << 32) | x
        s = 0
        for x in w[i + ac:i + ac + sc]: s = (s << 32) | x
        out.append((a, s))
    return out

TOUCH = re.compile(r'touch|goodix|focaltech|fts|synaptics|novatek|himax|stm,|elan|ilitek', re.I)

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('fdt'); ap.add_argument('-o')
    a = ap.parse_args(); raw = open(a.fdt, 'rb').read(); root = parse(raw)
    nodes = list(walk(root)); prof = {'schema': 1, 'verified': False,
        'fdt_sha256': hashlib.sha256(raw).hexdigest(), 'device': None}
    prof['device'] = (strs(root, 'model') or [None])[0]; prof['compatible'] = strs(root, 'compatible')
    ram = [(hx(x), hx(s)) for p, n in nodes if n['props'].get('device_type', b'').rstrip(b'\0') == b'memory' for x, s in reg(n)]
    resv = []
    for p, n in nodes:
        if n['parent'] and n['parent']['name'] == 'reserved-memory':
            for x, s in reg(n): resv.append({'path': p, 'base': hx(x), 'size': hx(s), 'no_map': 'no-map' in n['props']})
            if 'reg' not in n['props']:
                sz = u32s(n['props'].get('size', b''))
                resv.append({'path': p, 'base': None, 'size': hx(int.from_bytes(n['props'].get('size', b'\0'), 'big')) if sz else None,
                             'dynamic': True, 'alloc_ranges': [hx(x) for x in u32s(n['props'].get('alloc-ranges', b''))]})
    prof['ram'] = {'banks': [{'base': b, 'size': s} for b, s in ram], 'base': None, 'size': None}
    prof['reserved'] = resv
    prof['splash_candidates'] = [r for r in resv if re.search(r'splash|framebuffer|cont', r['path'], re.I)]
    for p, n in nodes:
        if 'arm,gic-v3' in strs(n, 'compatible'):
            r = reg(n); w = u32s(n['props'].get('redistributor-stride', b''))
            prof['gic'] = {'path': p, 'gicd': hx(r[0][0]), 'gicd_size': hx(r[0][1]),
                           'gicr': hx(r[1][0]) if len(r) > 1 else None, 'gicr_size': hx(r[1][1]) if len(r) > 1 else None,
                           'gicr_stride': hx(w[-1]) if w else None}
        if 'arm,armv8-timer' in strs(n, 'compatible'):
            prof['timer'] = {'path': p, 'freq_hz': u32s(n['props'].get('clock-frequency', b'\0\0\0\0'))[0] or None,
                             'interrupts_raw': u32s(n['props'].get('interrupts', b'')), 'vtimer_intid': None}
        if re.match(r'ufshc', n['name']) or 'qcom,ufshc' in strs(n, 'compatible'):
            r = reg(n)
            if r and 'ufs' not in prof: prof['ufs'] = {'path': p, 'base': hx(r[0][0]), 'size': hx(r[0][1])}
    cpus = [n for p, n in nodes if n['parent'] and n['parent']['name'] == 'cpus' and n['name'].startswith('cpu@')]
    prof['cpus'] = [{'name': n['name'], 'mpidr_reg': hx(reg(n)[0][0]) if reg(n) else None,
                     'compatible': strs(n, 'compatible')} for n in cpus]
    prof['touch_candidates'] = [{'path': p, 'compatible': strs(n, 'compatible'), 'reg': [hx(x) for x, _ in reg(n)],
        'parent': n['parent']['name'] if n['parent'] else None,
        'resource_props': sorted(k for k in n['props'] if re.search(r'supply|reset|irq|int|gpio|vdd|vio', k))}
        for p, n in nodes if n['parent'] and (TOUCH.search(n['name']) or any(TOUCH.search(c) for c in strs(n, 'compatible')))]
    pan = []
    for p, n in nodes:
        k = [x for x in n['props'] if x.startswith('qcom,mdss-dsi-panel-')]
        if k:
            d = {'path': p}
            for x in ('qcom,mdss-dsi-panel-name', 'qcom,mdss-dsi-panel-type'):
                if x in n['props']: d[x] = n['props'][x].rstrip(b'\0').decode(errors='replace')
            for x in ('qcom,mdss-dsi-panel-width', 'qcom,mdss-dsi-panel-height'):
                if x in n['props']: d[x] = u32s(n['props'][x])[0]
            pan.append(d)
    prof['panel_candidates'] = pan
    prof['fb'] = {'base': None, 'size': None, 'width': None, 'height': None, 'stride': None, 'format': None}
    out = json.dumps(prof, indent=2); open(a.o, 'w').write(out + '\n') if a.o else print(out)

if __name__ == '__main__': main()
