"""Draw a floorplan variant: blocks coloured by supply, zones, decaps, stripes, the top channel and every net as an L
route.
    node tools/floorplan_dump.js layout/floorplan/variants.json <id> > build/fp.json
    python3 tools/floorplan_draw.py build/fp.json build/fp.png [--pins]
"""
import json
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

d = json.load(open(sys.argv[1]))
out = sys.argv[2]
T = d['tile']
fig, ax = plt.subplots(figsize=(15, 7.6))
ax.add_patch(Rectangle((0, 0), T['w'], T['h'], fill=False, lw=1.5))
SUP = {'VAPWR': ('#e3eefb', '#2f6db3'), 'VDPWR': ('#fbe9df', '#b35a2f')}
for c in d['channel']:
    ax.add_patch(Rectangle((c[0], c[1]), c[2], c[3], fc='#999', ec='none', alpha=.25))
for r in d['reserved']:
    x, y, w, h = r['rect']
    ax.add_patch(Rectangle((x, y), w, h, fill=False, ec='#2f6db3', lw=1.2, ls='--', hatch='\\\\', alpha=.6))
    ax.text(x + w / 2, y + h / 2, r['label'], ha='center', va='center', fontsize=9, color='#2f6db3')
for dc in d['decaps']:
    x, y, w, h = dc['rect']
    ax.add_patch(Rectangle((x, y), w, h, fc='#cfd8e6' if dc['net'] == 'VAPWR' else '#ead7cc', ec='#888', lw=.5, hatch='//', alpha=.6))
for s in d['straps']:
    ax.add_patch(Rectangle((s['x'], 5), s['w'], T['h'] - 10, fc={'VAPWR': '#2f6db3', 'VDPWR': '#b35a2f'}.get(s['net'], '#555'), ec='none', alpha=.35))
for n, i in d['inst'].items():
    x, y, w, h = i['rect']
    fc, ec = SUP.get(i['supply'], ('#eee', '#555'))
    if i['halo']:
        hx, hy, hw, hh = i['halo']
        ax.add_patch(Rectangle((hx, hy), hw, hh, fill=False, ec=ec, ls=':', lw=.8))
    ax.add_patch(Rectangle((x, y), w, h, fc=fc, ec=ec, lw=1))
    for zn, z in (i['zones'] or {}).items():
        ax.add_patch(Rectangle((z[0], z[1]), z[2], z[3], fill=False, ec=ec, lw=.4, ls='--'))
        ax.text(z[0] + 1, z[1] + 1, zn, fontsize=5, color=ec)
    ax.text(x + w / 2, y + h / 2, f"{i['label']}\n{i['orient']}", ha='center', va='center', fontsize=7.5 if w > 60 else 6, color='#222', weight='bold')
col = {'rfin': 'red', 'rx': 'teal', 'rxout': 'darkcyan', 'lo': 'magenta', 'clk': 'orange', 'dig': 'gray', 'fine': 'purple', 'en': 'olive', 'tx': 'brown', 'ana': 'green'}
for nt in d['nets']:
    a, b = nt['pa'], nt['pb']
    xs = [nt['segs'][0][0]] + [q[2] for q in nt['segs']]
    ys = [nt['segs'][0][1]] + [q[3] for q in nt['segs']]
    ax.plot(xs, ys, color=col[nt['cls']], lw=.7 if nt['cls'] == 'fine' else 1.1, alpha=.75)
if '--pins' in sys.argv:
    for n, i in d['inst'].items():
        for p, (x, y, est) in i['pins'].items():
            ax.plot(x, y, 'o', ms=2.5, mfc='orange' if est else 'k', mec='none')
            ax.text(x, y, ' ' + p, fontsize=4.5, color='#444')
for k, p in T['pins'].items():
    if k.startswith('ua'):
        x = (p['x0'] + p['x1']) / 2
        ax.add_patch(Rectangle((p['x0'], -2), p['x1'] - p['x0'], 3, fc='k'))
        ax.text(x, -9, k, ha='center', fontsize=7)
ax.set_xlim(-5, T['w'] + 5)
ax.set_ylim(-14, T['h'] + 5)
ax.set_aspect('equal')
ax.set_xticks(range(0, int(T['w']) + 1, 50))
ax.set_yticks(range(0, int(T['h']) + 1, 50))
ax.grid(alpha=.2)
st = ' · '.join(f"{c[0]}:{c[2][0].upper()}" for c in d['checks'] if c[2] in ('pass', 'warn', 'fail'))
ax.set_title(f"{d['name']}   [{st}]", fontsize=9)
plt.tight_layout()
plt.savefig(out, dpi=110)
