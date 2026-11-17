#!/usr/bin/env python3
"""Figures for sim/top/tile_results.md from build/tile_sims/ -> docs/img/tile_sims/*.png

    python3 sim/top/tb_tile_figs.py
Each figure is drawn only when its runs are finished.
"""
import json
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / 'tools'))
import tb_tile as T  # noqa: E402
from rawread import read_raw  # noqa: E402

IMG = REPO / 'docs/img/tile_sims'
C1, C2, C3, C4 = '#2a78d6', '#eb6834', '#1baf7a', '#eda100'    # categorical slots 1-4, fixed order
INK, MUTED, GRID = '#1f1f1e', '#6b6a63', '#e4e3dc'
plt.rcParams.update({'font.size': 9, 'axes.edgecolor': MUTED, 'axes.labelcolor': INK, 'xtick.color': MUTED,
                     'ytick.color': MUTED, 'axes.grid': True, 'grid.color': GRID, 'grid.linewidth': 0.6,
                     'axes.spines.top': False, 'axes.spines.right': False, 'lines.linewidth': 1.5,
                     'legend.frameon': False, 'figure.dpi': 130})


def res(n):
    p = T.OUT / n / 'result.json'
    return json.loads(p.read_text()) if p.exists() else None


def raw(n):
    return read_raw(T.OUT / n / 'out.raw')[0]['vars']


def fig_vco():
    """Tile f against the vco_top reference at every (corner, code, word) point."""
    pts = []
    for n, c in T.cases().items():
        if not n.startswith('vco_c_') or n.endswith('_rx') or '_v3' in n:
            continue
        t, r = res(n), res('ref_' + n[len('vco_c_'):])
        if t and r and 'error' not in t and 'error' not in r:
            pts.append((n[len('vco_c_'):].replace('_', ' '), r['f_a0'] / 1e6, t['f_a2'] / 1e6))
    if not pts:
        return None
    fig, ax = plt.subplots(1, 2, figsize=(9, 3.6), gridspec_kw=dict(width_ratios=[1.3, 1]))
    x = np.arange(len(pts))
    ax[0].plot(x, [p[1] for p in pts], 'o', ms=6, color=C1, label='vco_top + mdac (block extraction)')
    ax[0].plot(x, [p[2] for p in pts], 's', ms=6, color=C2, label='tile extraction')
    ax[0].axhline(433.92, color=MUTED, lw=0.8, ls='--')
    ax[0].text(len(pts) - 0.5, 433.92, '433.92 MHz', color=MUTED, ha='right', va='bottom')
    ax[0].set_xticks(x, [p[0] for p in pts], rotation=60, ha='right', fontsize=7)
    ax[0].set_ylabel('f (MHz)')
    ax[0].legend(loc='upper left', fontsize=8)
    sh = [(p[2] / p[1] - 1) * 100 for p in pts]
    ax[1].bar(x, sh, color=C2, width=0.6)
    ax[1].set_xticks(x, [p[0] for p in pts], rotation=60, ha='right', fontsize=7)
    ax[1].set_ylabel('tile / block - 1 (%)')
    ax[1].axhline(0, color=MUTED, lw=0.8)
    fig.tight_layout()
    fig.savefig(IMG / 'vco_tile_vs_block.png')
    plt.close(fig)
    return float(np.mean(sh)), float(min(sh)), float(max(sh))


def fig_tx():
    r = res('tx_c_tt_on')
    if not r or 'error' in r:
        return None
    pl = raw('tx_c_tt_on')
    t = pl['time']
    m = t > t[-1] - 12e-9
    fig, ax = plt.subplots(2, 1, figsize=(7, 4.2), sharex=True)
    tn = (t[m] - t[m][0]) * 1e9
    ax[0].plot(tn, pl['v(ua3)'][m], color=C1, label='ua[3] (out_p, tile side of the pad)')
    ax[0].plot(tn, pl['v(ua2)'][m], color=C2, label='ua[2] (out_n)')
    ax[0].set_ylabel('V')
    ax[0].legend(loc='upper right', fontsize=7, ncol=2)
    ax[1].plot(tn, (pl['v(pin3)'] - pl['v(dmid)'])[m], color=C3, label='across the 73 ohm')
    ax[1].set_ylabel('V')
    ax[1].set_xlabel('time (ns, last 12 ns of the run)')
    ax[1].legend(loc='upper right', fontsize=7)
    fig.tight_layout()
    fig.savefig(IMG / 'tx_tt.png')
    plt.close(fig)
    return r['p1_dbm']


def fig_rx(name='rx_c_tt_-70_p'):
    r = res(name)
    if not r or 'error' in r:
        return None
    pl = raw(name)
    t = pl['time']
    m = t > T.RX_TSKIP
    tu = t[m] * 1e6
    fig, ax = plt.subplots(2, 1, figsize=(7, 4.2), sharex=True)
    ax[0].plot(tu, (pl['v(oi_p)'] - pl['v(oi_n)'])[m], color=C1, label='baseband I (oi_p - oi_n)')
    ax[0].plot(tu, (pl['v(oq_p)'] - pl['v(oq_n)'])[m], color=C2, label='baseband Q (oq_p - oq_n)')
    ax[0].set_ylabel('V')
    ax[0].legend(loc='upper right', fontsize=7, ncol=2)
    ax[1].plot(tu, pl['v(uo_out4)'][m], color=C1, label='q_i (uo_out[4])')
    ax[1].plot(tu, pl['v(uo_out5)'][m] + 0.0, color=C2, ls='--', label='q_q (uo_out[5])')
    ax[1].set_ylabel('V')
    ax[1].set_xlabel('time (us)')
    ax[1].legend(loc='upper right', fontsize=7, ncol=2)
    fig.tight_layout()
    fig.savefig(IMG / 'rx_tt.png')
    plt.close(fig)
    return r


def fig_pwr():
    r = res('pwrup_c_tt')
    if not r or 'error' in r:
        return None
    w = r['windows']
    tm = [x['t0'] + 0.5 for x in []] or [(x['t0'] + 0.5e-6) * 1e6 for x in w]
    fig, ax = plt.subplots(3, 1, figsize=(7, 5.6), sharex=True)
    ax[0].plot(tm, [x['vap'] for x in w], color=C1, label='VAPWR')
    ax[0].plot(tm, [x['vbnf'] for x in w], color=C2, label='vbnf')
    ax[0].plot(tm, [x['vg'] for x in w], color=C3, label='vg')
    ax[0].set_ylabel('V (1 us means)')
    ax[0].legend(loc='center right', fontsize=7)
    ax[1].plot(tm, [x['f_a2'] / 1e6 for x in w], 'o-', ms=3, color=C1, label='f(a2)')
    ax[1].set_ylabel('f (MHz)')
    ax[2].plot(tm, [x['i_vap_ma'] for x in w], color=C1, label='I(VAPWR)')
    ax[2].plot(tm, [x['i_vdp_ma'] for x in w], color=C2, label='I(VDPWR)')
    ax[2].set_ylabel('mA (1 us means)')
    ax[2].set_xlabel('time (us)')
    ax[2].legend(loc='center right', fontsize=7)
    fig.tight_layout()
    fig.savefig(IMG / 'powerup_tt.png')
    plt.close(fig)
    return r


def fig_zac():
    rs = {s: res(f'zac_c_tt_{s}') for s in ('vap', 'vdp')}
    if any(v is None or 'error' in v for v in rs.values()):
        return None
    fig, ax = plt.subplots(figsize=(6, 3.4))
    for (s, r), col in zip(rs.items(), (C1, C2)):
        ax.loglog(np.array(r['f']) / 1e6, r['z'], color=col, label={'vap': 'VAPWR', 'vdp': 'VDPWR'}[s])
    ax.set_xlabel('f (MHz)')
    ax.set_ylabel('|Z| into the tile (ohm)')
    ax.legend(fontsize=8)
    fig.tight_layout()
    fig.savefig(IMG / 'supply_z.png')
    plt.close(fig)
    return {s: (r['z_1e+06'], r['z_4.34e+08']) for s, r in rs.items()}


def main():
    IMG.mkdir(parents=True, exist_ok=True)
    for f in (fig_vco, fig_tx, fig_rx, fig_pwr, fig_zac):
        out = f()
        print(f.__name__, 'skipped (pending)' if out is None else 'ok', '' if out is None or isinstance(out, dict) and
              'windows' in out else out if not isinstance(out, dict) or len(str(out)) < 200 else '')


if __name__ == '__main__':
    main()
