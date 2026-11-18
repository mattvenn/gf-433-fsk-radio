#!/usr/bin/env python3
"""Clock check alongside eqy. eqy's strategies treat every flop as clocked by one implicit global clock, so they
never look at which clock net, or which edge, a flop uses. This checks that: each flop (found by its output name,
as eqy matches it) must be clocked from the same source with the same edge in the RTL and in the netlist. A source
is a port (clk, ck), a clock gate's output (by instance name) or another flop's output (the ripple divider), found
by walking back through buffers and inverters (each inverter flips the edge). The asynchronous reset is checked
the same way (source and polarity).
Usage: clocks.py gold.json gate.json"""
import collections
import json
import sys

TOP = 'tx_fine'
ICG = 'gf180mcu_fd_sc_mcu7t5v0__icgtp_1'


def load(path):
    mod = json.load(open(path))['modules'][TOP]
    names = collections.defaultdict(set)
    for n, d in mod['netnames'].items():
        if n.startswith('$'):
            continue
        for i, b in enumerate(d['bits']):
            names[b].add(n if len(d['bits']) == 1 else f'{n}[{i}]')
    for p, d in mod['ports'].items():
        for i, b in enumerate(d['bits']):
            names[b].add(p if len(d['bits']) == 1 else f'{p}[{i}]')
    drv = {}                                   # bit -> (kind, cell, input bit)
    for cn, c in mod['cells'].items():
        t = c['type']
        for p, sig in c['connections'].items():
            if c.get('port_directions', {}).get(p) == 'output' or (t.startswith('$') and p in ('Y', 'Q')):
                for b in sig:
                    drv[b] = (t, cn, c)

    def source(b, pol):
        for _ in range(50):
            if b not in drv:
                return frozenset(names[b]) or frozenset([str(b)]), pol
            t, cn, c = drv[b]
            if t in ('$_NOT_', '$not', '$logic_not'):
                b, pol = c['connections']['A'][0], 1 - pol
            elif t in ('$_BUF_', '$pos'):
                b = c['connections']['A'][0]
            elif t == ICG:
                return frozenset([cn]), pol
            else:
                return frozenset(names[b]) or frozenset([f'{t}:{cn}']), pol
        return frozenset(['loop']), pol

    flops = {}
    for cn, c in mod['cells'].items():
        t = c['type']
        if t in ('$adff', '$dff'):
            cp = int(str(c['parameters']['CLK_POLARITY']), 2)
            ap = int(str(c['parameters'].get('ARST_POLARITY', '1')), 2) if t == '$adff' else None
            arst = c['connections'].get('ARST', [None])[0]
        elif t.startswith('$_DFF_'):
            cp = 1 if t[6] == 'P' else 0
            ap = (1 if t[7] == 'P' else 0) if len(t) > 8 else None
            arst = c['connections'].get('R', [None])[0]
        else:
            continue
        clk = source((c['connections'].get('CLK') or c['connections']['C'])[0], cp)
        rst = source(arst, ap) if arst is not None else None
        for b in c['connections']['Q']:
            for n in names[b]:
                flops[n] = (clk, rst)
    return flops


gold, gate = load(sys.argv[1]), load(sys.argv[2])
common = sorted(set(gold) & set(gate))
bad = []
by = collections.Counter()
for n in common:
    (gc, gr), (tc, tr) = gold[n], gate[n]
    ok = bool(gc[0] & tc[0]) and gc[1] == tc[1]
    okr = (gr is None and tr is None) or (gr and tr and bool(gr[0] & tr[0]) and gr[1] == tr[1])
    if not (ok and okr):
        bad.append((n, gold[n], gate[n]))
    by[('pos ' if gc[1] else 'neg ') + sorted(gc[0])[0]] += 1
print(f'clocks: {len(common)} flop output names on both sides; same clock source, edge and reset on '
      f'{len(common) - len(bad)}; {len(bad)} mismatched; sources {dict(sorted(by.items()))}')
for n, g, t in bad[:20]:
    print(f'  mismatch: {n}: gold clk {sorted(g[0][0])} edge {g[0][1]} rst {g[1] and (sorted(g[1][0]), g[1][1])}; '
          f'gate clk {sorted(t[0][0])} edge {t[0][1]} rst {t[1] and (sorted(t[1][0]), t[1][1])}')
sys.exit(1 if bad or not common else 0)
