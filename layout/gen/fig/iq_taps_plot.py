"""Fig. 1b of docs/tile_layout.md: the I/Q-symmetric LO taps (branch iq-symmetry) in the tile GDS.
    python3 layout/gen/fig/a2_trace.py && python3 layout/gen/fig/iq_taps_plot.py   -> docs/img/iq_taps.png
"""
import json, sys, matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Patch
n = json.load(open('build/a2fig/nets.json')); B = json.load(open('build/tile/meta.json'))['blocks']
C = dict(a2=float(sys.argv[1]) if len(sys.argv) > 1 else None, a0=float(sys.argv[2]) if len(sys.argv) > 2 else None)
COL = {'a0': '#1f77b4', 'a2': '#d62728', 'ls': '#ff7f0e', 'lsq': '#bcbd22', 'vq': '#9467bd'}
LAYS = ('m1', 'm2', 'm3', 'm4')


def draw(ax, win, nets, alpha_bg=0.08):
    x0, y0, x1, y1 = win
    for net, sh in n.items():
        c = COL.get(net) if net in nets else None
        for k in LAYS:
            for b in sh[k]:
                if b[2] < x0 or b[0] > x1 or b[3] < y0 or b[1] > y1:
                    continue
                ax.add_patch(Rectangle((b[0], b[1]), b[2] - b[0], b[3] - b[1], fc=c or '#000', ec='none',
                                       alpha=(0.9 if c else alpha_bg), zorder=3 if c else 1))
    for inst, b in B.items():
        bx = b['box']
        if bx[2] < x0 or bx[0] > x1 or bx[3] < y0 or bx[1] > y1:
            continue
        ax.add_patch(Rectangle((bx[0], bx[1]), bx[2] - bx[0], bx[3] - bx[1], fc='none', ec='k', lw=0.8, ls='--', zorder=4))
        ax.text(max(bx[0], x0) + 1, min(bx[3], y1) - 1, inst, fontsize=7, va='top', zorder=5,
                bbox=dict(fc='white', ec='none', alpha=0.7, pad=0.5))
    ax.set_xlim(x0, x1); ax.set_ylim(y0, y1); ax.set_aspect('equal'); ax.set_xlabel('x (µm)'); ax.set_ylabel('y (µm)')


fig, (a, b) = plt.subplots(2, 1, figsize=(13, 13), gridspec_kw=dict(height_ratios=[1, 1.0]))
draw(a, (0, 0, 693.28, 325.36), ['ls', 'lsq', 'vq'], alpha_bg=0.04)
a.add_patch(Rectangle((262, 130), 75, 78, fc='none', ec='r', lw=1.5, zorder=6))
a.set_title('Whole tile: ls (I LO, orange), lsq (Q LO, olive), vq (the Q header supply, purple)', fontsize=10)
draw(b, (262, 130, 337, 208), ['a0', 'a2', 'ls', 'lsq', 'vq'])
lab = lambda k, s: f'{k}: {C[k]:.2f} fF' if C.get(k) else k
b.legend(handles=[Patch(fc=COL['a0'], label=lab('a0', 'a0') + ' (lsdiv abutted, I tap)'),
                  Patch(fc=COL['a2'], label=lab('a2', 'a2') + ' (Q level shifter, Q tap)'),
                  Patch(fc=COL['ls'], label='ls'), Patch(fc=COL['lsq'], label='lsq'), Patch(fc=COL['vq'], label='vq')],
         fontsize=8, loc='upper right', framealpha=0.9)
b.set_title('Zoom (red box): vco_core, lsdiv (bottom) and the mirrored Q level shifter (top) on the ring', fontsize=10)
fig.tight_layout(); fig.savefig('docs/img/iq_taps.png', dpi=120); print('ok')
