#!/usr/bin/env python3
"""Layout of the LO buffer rx_lobuf (NAND gate, splitter, two NAND-gated arms of 3 inverters), gf180mcuD.

    python3 layout/gen/rx_lobuf.py [--out build/rx_layout/gen/rx_lobuf] [--gds layout/rx_lobuf.gds]

Circuit and sizes: sim/rx/rx_lo.py rx_lobuf (= xschem/rx_lobuf.sch).
One band (layout/gen/rx_lib.py, the style of layout/gen/tx_drv.py), mirror-symmetric about the splitter:
  N3 N2 N1 NG | TG B1 | G0 T | A1 A2 | XA XB | PG P1 P2 P3
  lob arm (mirrored, left)   splitter (B path next to the lob arm, A path next to the lo arm)   lo arm (right)
Fingers: at most 4.2 um (P) / 2.5 um (N) each, so the P and N rows stay short.
The cell sits right above its mixer in rx_top (the same for I and Q): lo and lob leave on M3 through the bottom
edge at the mixer's lo / lob pin x (layout/gen/rx_mix.py meta, the cells centred on each other), so both outputs
reach the switches with equal wire and cross the mixer's rf / bb tracks at right angles.
Pins: VDD, VSS (rails), in (M2, left edge), en (M3, top edge), lo, lob (M3, bottom edge).
"""
import argparse
import json
import math
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rx_lib as R  # noqa: E402
from ring_core import Cell  # noqa: E402

PINS = ['VDD', 'VSS', 'in', 'en', 'lo', 'lob']
WPMAX, WNMAX = 4.2, 2.5


def inv(D, n):
    """Inverter n (devices n+'p', n+'n') as fingered strips."""
    out = []
    for t, wmax in (('p', WPMAX), ('n', WNMAX)):
        d = D[n + t]
        nf = max(1, math.ceil(d['w'] * d['m'] / wmax - 1e-9))
        out.append(R.from_dev(d, nf=nf))
    return out[0], out[1]


def nand(D, a, b, c, dd):
    """NAND from pull-ups a, b (P, parallel) and stack c (top, input of a), dd (bottom, input of b)."""
    pa, pb, nc, nd = D[a], D[b], D[c], D[dd]
    out = pa['nets'][0]
    assert pb['nets'][0] == out and nc['nets'][0] == out and nc['nets'][2] == nd['nets'][0]
    assert pa['w'] == pb['w'] and nc['w'] == nd['w']
    P = R.mos(pa['w'], pa['l'], ['VDD', pa['nets'][1], out, pb['nets'][1], 'VDD'], 'VDD')
    N = R.mos(nc['w'], nc['l'], [out, nc['nets'][1], nc['nets'][2], nd['nets'][1], 'VSS'], 'VSS')
    return P, N


def mirror(cols):
    rev = lambda e: dict(e, seq=e['seq'][::-1])
    return [(n, [rev(e) for e in P], [rev(e) for e in N]) for n, P, N in reversed(cols)]


def cols():
    D = {d['name']: d for d in R.flat_devs(R.sim_cells(), 'rx_lobuf')}
    col = lambda name, pn: (name, [pn[0]], [pn[1]])
    lob_arm = [col('NG', nand(D, 'NGa', 'NGb', 'NGc', 'NGd'))] + [col(f'N{k}', inv(D, f'N{k}')) for k in (1, 2, 3)]
    lo_arm = [col('PG', nand(D, 'PGa', 'PGb', 'PGc', 'PGd'))] + [col(f'P{k}', inv(D, f'P{k}')) for k in (1, 2, 3)]
    tgp, tgn = D['TGp'], D['TGn']
    tg = ('TG', [R.mos(tgp['w'], tgp['l'], [tgp['nets'][2], tgp['nets'][1], tgp['nets'][0]], 'VDD')],
          [R.mos(tgn['w'], tgn['l'], [tgn['nets'][2], tgn['nets'][1], tgn['nets'][0]], 'VSS')])
    mid = [tg, col('B1', inv(D, 'B1')), col('G0', nand(D, 'G0a', 'G0b', 'G0c', 'G0d')), col('T', inv(D, 'T')),
           col('A1', inv(D, 'A1')), col('A2', inv(D, 'A2')), col('XA', inv(D, 'XA')), col('XB', inv(D, 'XB'))]
    return mirror(lob_arm) + mid + lo_arm


def mix_pins():
    """The mixer's lo / lob pin x and its width (from layout/gen/rx_mix.py, built in-process)."""
    _, meta = R.load_gen('rx_mix').build()
    p = meta['bands'][0]['pins']
    return p['lo'][0][0], p['lob'][0][0], meta['bbox'][2] - meta['bbox'][0]


def build():
    cell = Cell('rx_lobuf')
    band = R.Band('rx_lobuf', cols(), pins=PINS[2:], search=True)
    xlo, xlob, wmix = mix_pins()
    info = {}

    def exits(bands, xr):
        dx = R.snap((xr - wmix) / 2)             # mixer origin in lobuf coordinates (cells centred)
        info['mix_dx'] = dx
        return [dict(**{'in': ('left', None)}, en=('top', None), lo=('bottom', xlo + dx), lob=('bottom', xlob + dx))]
    metas, bb = R.stack(cell, [band], exits)
    return [cell], dict(bbox=bb, bands=metas, mix_dx=info['mix_dx'])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(R.REPO / 'build' / 'rx_layout' / 'gen' / 'rx_lobuf'))
    ap.add_argument('--gds', default=str(R.REPO / 'layout' / 'rx_lobuf.gds'))
    a = ap.parse_args()
    cells, meta = build()
    R.save_meta(a.out, meta)
    log = R.write(cells, 'rx_lobuf', a.gds, a.out)
    print('rx_lobuf', R.bbox_str(meta['bbox']), 'mixer origin at x', meta['mix_dx'] / 1000, 'magic log', log)


if __name__ == '__main__':
    main()
