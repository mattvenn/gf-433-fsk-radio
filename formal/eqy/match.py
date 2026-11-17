#!/usr/bin/env python3
"""Write eqy's [match] and [partition] sections: match only the ports, every name of each flop's output, and the
clock-gate (black-box) cells. Internal combinational nets are left unmatched, so eqy doesn't cut there (a cut on
an internal net makes it a free input to the logic that reads it, while the netlist may compute that logic from
other signals, which gives false failures).
Usage: match.py gold.json gate.json > match.txt   (the designs after the [gold] / [gate] scripts)
Only names present on both sides are listed (the rest would be eqy warnings)."""
import collections
import json
import sys

TOP = 'tx_fine'
ICG = 'gf180mcu_fd_sc_mcu7t5v0__icgtp_1'
mod = json.load(open(sys.argv[1]))['modules'][TOP]
gate = json.load(open(sys.argv[2]))['modules'][TOP]
gate_ids = set(gate['netnames']) | set(gate['cells'])
names = collections.defaultdict(set)          # bit -> every public name of it
for n, d in mod['netnames'].items():
    if n.startswith('$'):
        continue
    bits = d['bits']
    for i, b in enumerate(bits):
        names[b].add(n if len(bits) == 1 else f'{n}[{i}]')


def is_ff(t):
    return t in ('$dff', '$adff') or t.startswith('$_DFF_')


def base(x):
    return x.split('[')[0] if x.split('[')[0] in mod['ports'] else x


keep = set(mod['ports'])
cells = []
qbits = []
for cname, c in mod['cells'].items():
    if is_ff(c['type']):
        for b in c['connections']['Q']:
            keep |= {base(x) for x in names[b]}
            qbits.append(b)
    elif c['type'] == ICG:
        cells.append(cname)
    elif c['type'].startswith('$') and 'Q' in c['connections'] and c['type'] != '$scopeinfo':
        sys.exit(f'unexpected state element {cname} ({c["type"]})')

both = sorted(n for n in keep | set(cells) if n in gate_ids)
print(f'[match {ICG}]\ngold-match *\n')
print(f'[match {TOP}]\nnodefault')
for n in both:
    print('gold-match', n.replace('[', '\\[').replace(']', '\\]'))
# combinational outputs that the design also reads inside (rx_en = ctrl[4], dbg_sel = dbg, ck_o, div*) are amended
# into the partitions that use them, so they are not cut points
qs = set(qbits)
comb_out = sorted(p for p, d in mod['ports'].items()
                  if d['direction'] == 'output' and not all(b in qs for b in d['bits']))
print(f'\n[partition {TOP}]')
for p in comb_out:
    print('amend', p)
n_named = sum(1 for b in qbits if any(base(x) in gate_ids for x in names[b]))
print(f'# gold: {len(qbits)} flop bits, {n_named} with a name in the netlist; {len(cells)} clock gates; '
      f'{len(both)} names matched; combinational outputs (amended): {" ".join(comb_out)}', file=sys.stderr)
