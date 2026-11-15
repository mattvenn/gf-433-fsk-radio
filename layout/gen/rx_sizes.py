#!/usr/bin/env python3
"""Device-size diff: an extracted receiver layout against the sim netlister (sim/rx/rx_top.py block()).

    python3 layout/gen/rx_sizes.py <extracted.spice> <cell> [--tol 0.005]

netgen black-boxes the PDK resistors and adds parallel MOS widths, so this diff checks what it can't: every MOS
group (model, L, {drain, source}, gate, bulk for pfets) must have the same total W (W x m summed over fingers) and
every resistor (model, W, {a, b}) the same length, within --tol (0.5 %). Both netlists are flattened; the layout
labels every net with its sim-netlist name (layout/gen/rx_lib.py), so the groups line up by name.
Last line: "SIZES OK (n groups)" or "SIZES FAIL (k of n groups differ)".
"""
import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / 'sim' / 'rx'))

MOS = ('nfet_03v3', 'pfet_03v3')
RES = ('ppolyf_u', 'ppolyf_u_1k')


def num(s):
    s = s.lower()
    mult = {'u': 1.0, 'n': 1e-3, 'p': 1e-6, 'f': 1e-9}
    if s[-1] in mult:
        return float(s[:-1]) * mult[s[-1]]
    return float(s) * 1e6


def parse(text):
    text = re.sub(r'\n\+', ' ', text)
    cells, cur = {}, None
    for ln in text.splitlines():
        t = ln.split()
        if not t or t[0].startswith('*'):
            continue
        if t[0].lower() == '.subckt':
            cur = dict(pins=[x for x in t[2:] if '=' not in x], lines=[])
            cells[t[1]] = cur
        elif t[0].lower() == '.ends':
            cur = None
        elif cur is not None and t[0][0] in 'Xx':
            cur['lines'].append(t)
    return cells


def flat(cells, top, nets=None, path=''):
    """Flattened devices: (model, [nets], {w, l, m})."""
    c = cells[top]
    nets = nets or {p: p for p in c['pins']}
    out = []
    for t in c['lines']:
        kv = dict(x.split('=', 1) for x in t if '=' in x)
        pos = [x for x in t[1:] if '=' not in x]
        model = pos[-1]
        conn = [nets.get(n, path + n) for n in pos[:-1]]
        if model in MOS or model in RES:
            p = {k.lower(): v for k, v in kv.items()}
            if model in MOS:
                out.append((model, conn, dict(w=num(p['w']), l=num(p['l']), m=int(float(p.get('m', 1))))))
            else:
                out.append((model, conn, dict(w=num(p['r_width']), l=num(p['r_length']), m=1)))
        elif model in cells:
            sub = cells[model]
            out += flat(cells, model, dict(zip(sub['pins'], conn)), path + t[0] + '_')
    return out


def groups(devs):
    g = defaultdict(float)
    for model, n, p in devs:
        if model in MOS:
            d, gt, s, b = n[:4]
            key = (model, round(p['l'], 3), tuple(sorted({d, s})), gt, b if model == 'pfet_03v3' else '-')
            g[key] += p['w'] * p['m']
        else:
            a, b = n[:2]
            g[(model, round(p['w'], 3), tuple(sorted({a, b})))] += p['l']
    return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('lay')
    ap.add_argument('cell')
    ap.add_argument('--tol', type=float, default=0.005)
    a = ap.parse_args()
    import rx_top
    ref = groups(flat(parse(rx_top.block()), a.cell))
    lay = groups(flat(parse(Path(a.lay).read_text()), a.cell))
    keys = sorted(set(ref) | set(lay), key=str)
    bad = 0
    for k in keys:
        r, l = ref.get(k), lay.get(k)
        ok = r is not None and l is not None and abs(l - r) <= a.tol * r
        bad += not ok
        print(f"{'ok ' if ok else 'BAD'} {k}  sim {r if r is None else round(r, 4)}  layout "
              f"{l if l is None else round(l, 4)}")
    n = len(keys)
    print(f'SIZES OK ({n} groups)' if not bad else f'SIZES FAIL ({bad} of {n} groups differ)')


if __name__ == '__main__':
    main()
