#!/usr/bin/env python3
"""Validate a sunfish profile. Exit 1 if any required value is missing or implausible.
Dependent steps (building the ADT / shim for the phone) must not run until this passes.
A pass means the values are self-consistent, NOT that they are right for the phone."""
import json, sys

REQ = ['device', 'ram.base', 'ram.size', 'gic.gicd', 'gic.gicd_size', 'gic.gicr', 'gic.gicr_size',
       'timer.freq_hz', 'timer.vtimer_intid', 'fb.base', 'fb.size', 'fb.width', 'fb.height', 'fb.stride',
       'ufs.base', 'ufs.size', 'cpus', 'reserved']

def get(d, path):
    for k in path.split('.'):
        if not isinstance(d, dict) or k not in d: return None
        d = d[k]
    return d

def num(v): return int(v, 0) if isinstance(v, str) else v

def main():
    p = json.load(open(sys.argv[1])); err, warn = [], []
    for k in REQ:
        v = get(p, k)
        if v in (None, '', [], 'FILL'): err.append('INVALID %s: missing' % k)
    if err: return report(err, warn)
    try:
        ram_b, ram_s = num(p['ram']['base']), num(p['ram']['size'])
        gd, gds, gr, grs = (num(p['gic'][k]) for k in ('gicd', 'gicd_size', 'gicr', 'gicr_size'))
        fb = {k: num(p['fb'][k]) for k in ('base', 'size', 'width', 'height', 'stride')}
        res = [(num(r['base']), num(r['size'])) for r in p['reserved'] if r.get('base') and r.get('size')]
        cpus = [num(c) for c in p['cpus']]
    except (ValueError, TypeError, KeyError) as e:
        return report(['INVALID unparsable value: %r' % e], warn)
    if ram_b % 0x4000 or ram_s % 0x4000: err.append('ram base/size not 16K aligned (XNU uses 16K pages)')
    for b, s in res:
        if ram_b < b + s and b < ram_b + ram_s: err.append('ram %#x+%#x overlaps reserved %#x+%#x' % (ram_b, ram_s, b, s))
    if gds != 0x10000: warn.append('gicd_size %#x != 0x10000' % gds)
    if grs % 0x20000: err.append('gicr_size %#x not a multiple of 0x20000' % grs)
    if num(p['timer']['freq_hz']) != 19200000: warn.append('timer freq != 19.2 MHz (Qualcomm default)')
    if num(p['timer']['vtimer_intid']) != 19: warn.append('vtimer INTID != 19 (Qualcomm PPI numbering per ios-sweet NOTES)')
    if fb['base'] % 0x1000: err.append('fb base not 4K aligned')
    if min(fb['width'], fb['height']) <= 0 or fb['stride'] < fb['width'] * 4: err.append('fb stride < width*4 or empty size')
    elif fb['size'] < fb['stride'] * fb['height']: err.append('fb size < stride*height')
    if ram_b < fb['base'] + fb['size'] and fb['base'] < ram_b + ram_s: err.append('fb overlaps kernel RAM')
    if len(set(cpus)) != len(cpus) or cpus[0] != 0: err.append('cpus: duplicate entries or first MPIDR != 0')
    return report(err, warn)

def report(err, warn):
    for e in err: print('ERROR  ', e)
    for w in warn: print('WARN   ', w)
    print('profile check:', 'FAILED' if err else 'passed (self-consistent only; unverified on target)')
    return 1 if err else 0

if __name__ == '__main__': sys.exit(main())
