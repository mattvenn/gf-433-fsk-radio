"""Figures for sim/power/results.md: the VAPWR drop map (RX + ring on) and the worst drop per block and supply.

    python3 sim/power/figs.py   -> docs/img/power/vapwr_map.png, docs/img/power/drop_bars.png
"""
import json
import os

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
B = os.path.join(ROOT, 'build', 'power', 'res_p0.5')
IMG = os.path.join(ROOT, 'docs', 'img', 'power')
META = json.load(open(os.path.join(ROOT, 'build', 'tile', 'meta.json')))


def drop_map():
    z = np.load(os.path.join(B, 'map_A_VAPWR.npz'))
    v, ids = z['v'] * 1e3, z['ids']
    P = 0.5
    img = np.full(ids.shape[1:], np.nan)
    for k in range(ids.shape[0]):            # show the lowest layer present (where the devices are)
        m = (ids[k] >= 0) & np.isnan(img)
        img[m] = v[ids[k][m]]
    fig, ax = plt.subplots(figsize=(10, 5.2))
    ny, nx = img.shape
    im = ax.imshow(img, origin='lower', extent=[0, nx * P, 0, ny * P], cmap='viridis', interpolation='nearest')
    for b, d in META['blocks'].items():
        x0, y0, x1, y1 = d['box']
        ax.add_patch(plt.Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, lw=0.6, ec='0.4'))
        if (x1 - x0) * (y1 - y0) > 2000:
            ax.text((x0 + x1) / 2, (y0 + y1) / 2, b, ha='center', va='center', fontsize=7, color='0.15')
    ax.set_xlabel('x (µm)')
    ax.set_ylabel('y (µm)')
    ax.set_xlim(0, 693.28)
    ax.set_ylim(0, 325.36)
    cb = fig.colorbar(im, ax=ax, shrink=0.8)
    cb.set_label('drop below the chip VAPWR (mV)')
    vsw = float(z['vsw']) * 1e3
    ax.set_title(f'VAPWR, receiver and ring on (7.97 mA), case A; {vsw:.1f} mV of it in the TT switch')
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, 'vapwr_map.png'), dpi=130)


def bars():
    r = json.load(open(os.path.join(B, 'result.json')))
    rows = []
    for net, mo in (('VAPWR', 'all'), ('VDPWR', 'all'), ('VGND', 'all')):
        ca = r['cases']['A'][net]['modes'][mo]
        cb = r['cases']['B'][net]['modes'][mo]
        import currents  # noqa: E402
        loaded = currents.mode(mo)[net]
        for b in sorted(loaded):
            if b not in ca['blocks']:
                continue
            wa, wb = ca['blocks'][b]['worst_mV'], cb['blocks'][b]['worst_mV']
            rows.append((f'{b} {net}', max(wa, wb), ca['switch_mV'], net))
    rows.sort(key=lambda t: (t[3], -t[1]))
    fig, ax = plt.subplots(figsize=(9, 6))
    col = {'VAPWR': '#4C72B0', 'VDPWR': '#DD8452', 'VGND': '#55A868'}
    y = np.arange(len(rows))
    sw = [t[2] for t in rows]
    grid = [t[1] - t[2] for t in rows]
    ax.barh(y, sw, color='0.75', label='TT power switch')
    ax.barh(y, grid, left=sw, color=[col[t[3]] for t in rows], label='tile grid (VAPWR / VDPWR / VGND colours)')
    for k, t in enumerate(rows):
        ax.text(t[1] * 1.06, k, f'{t[1]:.1f}', va='center', fontsize=7)
    ax.set_yticks(y)
    ax.set_yticklabels([t[0] for t in rows], fontsize=8)
    ax.invert_yaxis()
    ax.set_xscale('symlog', linthresh=10)
    ax.set_xlabel('worst drop (VAPWR, VDPWR) or rise (VGND) at the block, mV, all blocks on, worse of cases A / B')
    ax.legend(loc='lower right', fontsize=8)
    fig.tight_layout()
    fig.savefig(os.path.join(IMG, 'drop_bars.png'), dpi=130)


if __name__ == '__main__':
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    os.makedirs(IMG, exist_ok=True)
    drop_map()
    bars()
