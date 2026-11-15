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
    mult = {'m': 1e3, 'u': 1.0, 'n': 1e-3, 'p': 1e-6, 'f': 1e-9}     # in um (magic writes 0.15912m for 159.12 um)
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


def inst(name):
    """Instance name as a path component: magic writes the layout's 'lo_bi' as Xlo_bi, the sim has xlo / xbi; both
    become lo_bi."""
    return name.lower().lstrip('x')


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
            out += flat(cells, model, dict(zip(sub['pins'], conn)), path + inst(t[0]) + '_')
    return out


def name_auto(lay, ref):
    """Give layout nets without a label (magic names them a_..#, w_..#) the sim name of the net whose devices have
    the same signature: the set of (model, L, role, the device's other nets) with unknown names as '?'. Iterated, so
    one resolved name can resolve its neighbours. Returns the renamed layout devices and the unresolved names."""
    simn = {x for _, n, _ in ref for x in n}
    auto = lambda n: '#' in n or n not in simn          # no sim name (magic's a_..#, or a hierarchical label)
    def sigs(devs, known):
        s = defaultdict(set)
        for model, n, p in devs:
            q = [x if (not auto(x) and (x in known or not known)) else '?' for x in n]
            if model in MOS:
                d, g, src, b = n[:4]
                roles = [(d, 'sd', (q[1], q[2])), (src, 'sd', (q[1], q[0])), (g, 'g', tuple(sorted((q[0], q[2]))))]
            else:
                roles = [(n[0], 'r', (q[1],)), (n[1], 'r', (q[0],))]
            for net, role, oth in roles:
                s[net].add((model, round(p['l'], 1), role, oth))      # L to 0.1 um: magic rounds R lengths
        return s
    names = {x for _, n, _ in lay for x in n}
    for _ in range(4):
        ln = {x for _, n, _ in lay for x in n}
        unres = sorted(x for x in ln if auto(x))
        if not unres:
            break
        known = {x for x in ln if not auto(x)}
        rs = sigs(ref, known)
        ls = sigs(lay, known)
        cand = {k: v for k, v in rs.items() if k not in known}
        ren = {}
        for a in unres:
            hit = [k for k, v in cand.items() if v == ls[a]]
            if len(hit) == 1:
                ren[a] = hit[0]
        if not ren:
            break
        lay = [(m, [ren.get(x, x) for x in n], p) for m, n, p in lay]
    return lay, sorted({x for _, n, _ in lay for x in n if auto(x)})


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
    refd = flat(parse(rx_top.block()), a.cell)
    layd, unres = name_auto(flat(parse(Path(a.lay).read_text()), a.cell), refd)
    if unres:
        print('layout nets without a sim name:', ' '.join(unres))
    ref, lay = groups(refd), groups(layd)
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
