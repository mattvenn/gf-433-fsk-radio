#!/usr/bin/env python3
"""Gap 5: the coupling budget from the comparator outputs (q_i / q_q = uo_out[4] / uo_out[5]) back into the baseband.

1. Transimpedance, extracted blocks (layout/pex/rx_*_c.spice): pads + LNA + mixers with the LO held static (one switch
   pair on: at baseband the mixer output then sees the LNA's output resistance, as it does in both LO phases) + both
   baseband arms + limiters, in .ac at the FSK deviation (100 kHz). A 1 A AC current is injected at one node at a time
   (every net of rx_bb / rx_lim and the mixer outputs) and the differential voltage at each comparator input
   (xl?.gcp - xl?.gcn) is read: Z_t(n).
2. The signal: a differential current pair at the I mixer output gives H = V(comparator) / V(mixer out); the -105 dBm
   signal at the mixer output is the tile's -95 dBm value (rxs_c_tt_-95_p, mix_i_v) - 10 dB.
3. Budget per node: the coupling C from a 0 / 3.3 V square at 100 kHz (fundamental 4 / pi x 1.65 V) that puts 1 / 10 of
   the -105 dBm signal on a comparator input: C_b(n) = 0.1 V_sig / (|Z_t(n)| 2 pi f V_q1), the worse comparator.
4. Every capacitor in layout/pex/tile_c.spice from uo_out[4] / uo_out[5] to another net: named nets take their own
   budget; unnamed tile nets are matched to the block nets by their device connections (model, W, L, terminal: an
   LVS-like signature); a net that matches nothing in rx_bb / rx_lim / the mixer outputs is outside the baseband.
   Pass: every coupling <= its budget. Output build/verify/coupling/budget.json.

    python3 sim/verify/coupling.py [--mut]      # --mut: a cap of 10 x the budget added (the check must FAIL)
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for p in ('sim/verify', 'sim/rx'):
    sys.path.insert(0, str(REPO / p))
import rxc  # noqa: E402
import rx_top  # noqa: E402
import rx_chain  # noqa: E402
import chain_x as X  # noqa: E402

OUT = REPO / 'build' / 'verify' / 'coupling'
TILE = REPO / 'layout' / 'pex' / 'tile_c.spice'
F = 100e3
VQ1 = 4 / np.pi * rxc.VDD / 2
AGG = ('uo_out[4]', 'uo_out[5]')


def victims():
    """(instance-qualified net, cell, net) for every net of the baseband side."""
    out = [(n, 'top', n) for n in ('bi_p', 'bi_n', 'bq_p', 'bq_n', 'oi_p', 'oi_n', 'oq_p', 'oq_n')]
    for cell, insts in (('rx_bb', ('xbbi', 'xbbq')), ('rx_lim', ('xli', 'xlq'))):
        sub = re.search(rf'(?ms)^\.subckt {cell} (.*?)$(.*?)^\.ends', X.pex(cell))
        ports = sub.group(1).split()
        nets = set()
        for ln in sub.group(2).splitlines():
            if ln.startswith('X'):
                nets.update(x for x in ln.split()[1:5] if '=' not in x)
        for n in sorted(nets - set(ports) - {'VDD', 'VSS'}):
            out += [(f'{i}.{n}', cell, n) for i in insts]
    return out


def ac_deck(vic):
    body = rx_chain.front(None, None, tone=(100e3, -200)) + rx_chain.chain_body()
    # the LO held: lo on, lob off for both arms (the B sources of chain_body replaced by DC)
    body = re.sub(r'(?m)^B(loi|loq) (\S+) 0 V=.*$', rf'V\1 \2 0 {rxc.VDD}', body)
    body = re.sub(r'(?m)^B(lobi|lobq) (\S+) 0 V=.*$', r'V\1 \2 0 0', body)
    inj = ''.join(f'Ij{k} 0 {n} dc 0 ac 0\n' for k, (n, _, _) in enumerate(vic))
    inj += 'Isp 0 bi_p dc 0 ac 0\nIsn bi_n 0 dc 0 ac 0\n'
    loop = ''
    for k in range(len(vic)):
        loop += (f'alter ij{k} acmag=1\nac lin 1 {F} {F}\n'
                 f'let zi = mag(v(xli.gcp)-v(xli.gcn))\nlet zq = mag(v(xlq.gcp)-v(xlq.gcn))\n'
                 f'echo "ZT {k} $&zi[0] $&zq[0]"\nalter ij{k} acmag=0\ndestroy all\n')
    loop += (f'alter isp acmag=1\nalter isn acmag=1\nac lin 1 {F} {F}\n'
             'let h = mag(v(xli.gcp)-v(xli.gcn))/mag(v(bi_p)-v(bi_n))\necho "HSIG $&h[0]"\n')
    deck = f"""* coupling budget: transimpedance to the comparator inputs, extracted blocks, LO held
{rxc.hdr('typical', pad=True)}{rx_top.block()}
VDD VDD 0 {rxc.VDD}
VSS VSS 0 0
Ven en 0 {rxc.VDD}
{body}{inj}.control
option temp=27
op
{loop}.endc
.end
"""
    return X.swap_pex(deck)


# ---------------------------------------------------------------------------------------------- net signatures
def parse_devs(text):
    devs = []
    for ln in re.sub(r'\n\+', ' ', text).splitlines():
        if not ln.startswith('X'):
            continue
        f = ln.split()
        mdl = next((x for x in f[5:7] if 'fet' in x or 'ppolyf' in x), None)
        if mdl is None:
            continue
        w = re.search(r'\bw=(\S+)', ln) or re.search(r'r_width=(\S+)', ln)
        l = re.search(r'\bl=(\S+)', ln) or re.search(r'r_length=(\S+)', ln)
        devs.append((mdl, w.group(1) if w else '', l.group(1) if l else '', f[1:5] if 'fet' in mdl else f[1:3]))
    return devs


def signatures(devs, roles=('d', 'g', 's', 'b')):
    sig = defaultdict(Counter)
    for mdl, w, l, nets in devs:
        for r, n in zip(roles if 'fet' in mdl else ('r', 'r'), nets):
            if r in ('d', 's'):
                r = 'sd'
            sig[n][(mdl, w, l, r)] += 1
    return {n: frozenset(c.items()) for n, c in sig.items()}


def block_sigs():
    out = defaultdict(list)
    for cell in ('rx_bb', 'rx_lim'):
        sub = re.search(rf'(?ms)^\.subckt {cell} (.*?)$(.*?)^\.ends', X.pex(cell))
        for n, s in signatures(parse_devs(sub.group(2))).items():
            if n not in ('VDD', 'VSS'):
                out[s].append((cell, n))
    return out


def tile_caps():
    txt = TILE.read_text()
    caps = []
    for m in re.finditer(r'(?m)^C\S+ (\S+) (\S+) (\S+)', txt):
        a, b, v = m.groups()
        v = float(v.rstrip('f')) * 1e-15 if v.endswith('f') else float(v)
        caps.append((a, b, v))
    sub = re.search(r'(?ms)^\.subckt \S+ (.*?)$(.*?)^\.ends', re.sub(r'\n\+', ' ', txt))
    return caps, signatures(parse_devs(sub.group(2)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--mut', action='store_true')
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    vic = victims()
    d, log, fl = X.run('../coupling/ac', ac_deck(vic))
    zt = {int(r[0]): (r[1], r[2]) for r in rxc.tag(log, 'ZT')}
    h = rxc.tag(log, 'HSIG')
    r = dict(flags=fl, f_hz=F, vq1=VQ1)
    if len(zt) != len(vic) or not h:
        r['error'] = f'ac: {len(zt)} of {len(vic)} nodes, HSIG {bool(h)}'
        (OUT / 'budget.json').write_text(json.dumps(r, indent=1))
        print(r)
        sys.exit(1)
    rs = json.loads((REPO / 'build/tile_sims_nb/rxs_c_tt_-95_p/result.json').read_text())
    vmix = rs['mix_i_v'] * 10 ** (-10 / 20)                        # -105 dBm at the mixer output (V, amplitude)
    vsig = h[0][0] * vmix
    r.update(h_sig=h[0][0], v_mix_105=vmix, v_sig_cmp_105=vsig)
    budget = {}
    for k, (n, cell, net) in enumerate(vic):
        z = max(zt[k])
        budget[n] = dict(cell=cell, net=net, zt_ohm=z, budget_f=0.1 * vsig / (z * 2 * np.pi * F * VQ1) if z > 0 else 1.0)
    r['budget'] = budget
    # block net -> the smallest budget of its instances (I / Q arm)
    by_net = defaultdict(lambda: 1.0)
    for n, b in budget.items():
        by_net[(b['cell'], b['net'])] = min(by_net[(b['cell'], b['net'])], b['budget_f'])
    caps, tsig = tile_caps()
    bsig = block_sigs()
    rows = []
    for x, y, c in caps:
        if x in AGG or y in AGG:
            agg, v = (x, y) if x in AGG else (y, x)
            if v in AGG or v in ('VDPWR', 'VAPWR', 'VGND', '0'):
                continue
            if v in budget:
                cand = [('top', v)]
                bud = budget[v]['budget_f']
            else:
                cand = bsig.get(tsig.get(v), [])
                bud = min((by_net[cn] for cn in cand), default=None)
            rows.append(dict(agg=agg, net=v, c_f=c, match=[f'{a_}.{b_}' for a_, b_ in cand], budget_f=bud,
                             margin=(bud / c if bud and c > 0 else None)))
    if a.mut:                 # planted: 10 x the budget from uo_out[4] to the most sensitive matched node
        mm = min((x for x in rows if x['budget_f']), key=lambda x: x['budget_f'])
        rows.append(dict(agg='uo_out[4]', net=mm['net'], c_f=10 * mm['budget_f'], match=mm['match'],
                         budget_f=mm['budget_f'], margin=0.1, planted=True))
    r['couplings'] = sorted(rows, key=lambda x: (x['margin'] if x['margin'] else 1e9))
    inb = [x for x in rows if x['budget_f']]
    r['n_couplings'], r['n_in_baseband'] = len(rows), len(inb)
    r['worst'] = r['couplings'][:8]
    r['pass'] = all(x['c_f'] <= x['budget_f'] for x in inb) and not fl
    # the most sensitive baseband node that has a tile name (for the tile mutation run mut_rx0_ccoup)
    named = {}
    for v, s in tsig.items():
        for cn in bsig.get(s, []):
            named.setdefault(cn, v)
    best = min(((by_net[cn], cn) for cn in named), default=None)
    if best:
        r['tile_most_sensitive'] = dict(block_net=f'{best[1][0]}.{best[1][1]}', tile_node=f'xtile.{named[best[1]]}',
                                        budget_f=best[0])
    r['min_budget'] = min(b['budget_f'] for b in budget.values())
    name = 'budget_mut.json' if a.mut else 'budget.json'
    (OUT / name).write_text(json.dumps(r, indent=1, default=float))
    print(json.dumps({k: v for k, v in r.items() if k not in ('budget', 'couplings')}, indent=1, default=float))
    print('PASS' if r['pass'] else 'FAIL')


if __name__ == '__main__':
    main()
