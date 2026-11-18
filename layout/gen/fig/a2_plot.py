import json, matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
n = json.load(open('build/a2fig/nets.json')); B = json.load(open('build/tile/meta.json'))['blocks']
COL = {'a2': '#d62728', 'ls': '#ff7f0e', 'lsq': '#bcbd22', 'oi_p': '#1f77b4', 'oi_n': '#1f77b4', 'oq_p': '#17becf',
       'oq_n': '#17becf', 'VGND': '#404040', 'VAPWR': '#2ca02c', 'vg': '#9467bd', 'enb': '#8c564b'}
LAYS = ('m1', 'm2', 'm3', 'm4')
def draw(ax, win, nets, alpha_bg=0.10, lw=0):
    x0, y0, x1, y1 = win
    for net, sh in n.items():
        c = COL.get(net) if net in nets else None
        for k in LAYS:
            for b in sh[k]:
                if b[2] < x0 or b[0] > x1 or b[3] < y0 or b[1] > y1: continue
                if c: ax.add_patch(Rectangle((b[0], b[1]), b[2]-b[0], b[3]-b[1], fc=c, ec='none',
                                             alpha=0.95 if net in ('a2', 'ls') else 0.55, zorder=3 if net in ('a2','ls') else 2))
                else: ax.add_patch(Rectangle((b[0], b[1]), b[2]-b[0], b[3]-b[1], fc='#000', ec='none', alpha=alpha_bg, zorder=1))
    for inst, b in B.items():
        bx = b['box']
        if bx[2] < x0 or bx[0] > x1 or bx[3] < y0 or bx[1] > y1: continue
        ax.add_patch(Rectangle((bx[0], bx[1]), bx[2]-bx[0], bx[3]-bx[1], fc='none', ec='k', lw=0.8, ls='--', zorder=4))
        ax.text(max(bx[0], x0)+1, min(bx[3], y1)-1, inst, fontsize=7, va='top', zorder=5,
                bbox=dict(fc='white', ec='none', alpha=0.7, pad=0.5))
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect('equal'); ax.set_xlabel('x (µm)'); ax.set_ylabel('y (µm)')
import klayout.db as kdb
_l=kdb.Layout(); _l.read('gds/tt_um_mattvenn_gf433_vco.gds'); BB=_l.top_cell().dbbox()
fig, (a, b) = plt.subplots(2, 1, figsize=(13, 15), gridspec_kw=dict(height_ratios=[1, 1.15]))
draw(a, (0, 0, BB.right, BB.top), ['a2', 'ls', 'lsq', 'oi_p', 'oi_n', 'oq_p', 'oq_n'], alpha_bg=0.05)
a.add_patch(Rectangle((240, 140), 95, 45, fc='none', ec='r', lw=1.5, zorder=6))
a.set_title('Whole tile: a2 (red), ls (orange), lsq (olive), baseband oi (blue) / oq (cyan)', fontsize=10)
draw(b, (240, 140, 335, 185), ['a2', 'ls', 'VGND', 'VAPWR', 'vg', 'enb', 'oi_n', 'oq_p', 'oi_p', 'lsq'])
b.set_title('Zoom (red box): a2 and its neighbours, Metal1-Metal4', fontsize=10)
from matplotlib.patches import Patch
b.legend(handles=[Patch(fc=COL[k], label=l) for k, l in [
    ('a2', 'a2: 19.0 fF in all (ring nodes ~3.3 fF)'), ('VAPWR', 'VAPWR: 4.9 fF (VGND 6.3 fF: mostly to the substrate)'),
    ('vg', 'vg: 1.4 fF'), ('enb', 'enb: 1.3 fF'), ('oi_n', 'oi_n / oi_p: 0.8 fF (oi_n)'), ('oq_p', 'oq_p: 0.8 fF'),
    ('ls', 'ls (I LO, 59 fF)'), ('lsq', 'lsq')]], fontsize=7.5, loc='lower right', framealpha=0.9)
kw = dict(fontsize=9, color='#a00000', zorder=7, bbox=dict(fc='white', ec='#a00000', alpha=0.9, pad=2))
b.annotate('1: in vco_core, Metal2, 52 µm\nring node (x 323) to the west-edge pin,\nbeside the VAPWR rail and over its plate', (300, 171), (285, 180), arrowprops=dict(arrowstyle='->', color='#a00000'), **kw)
b.annotate('2: tile route, Metal3 / Metal2,\n29 µm, crossing the baseband\npairs, enb and VAPWR stripes', (264, 162.5), (241, 174), arrowprops=dict(arrowstyle='->', color='#a00000'), **kw)
b.annotate('3: rx_lsq input\ncoupling capacitor\n(about 2 fF, intended)', (256, 154), (243, 142.5), arrowprops=dict(arrowstyle='->', color='#a00000'), **kw)
fig.tight_layout(); fig.savefig('docs/img/a2_route.png', dpi=130); print('ok')
