#!/usr/bin/env python3
"""Layout of the receiver bias rx_bias (constant-gm reference, start-up, enable), gf180mcuD, 3.3 V devices.

    python3 layout/gen/rx_bias.py [--out build/rx_layout/gen/rx_bias] [--gds layout/rx_bias.gds]

Circuit and sizes: sim/rx/rx_bias.py block() (= xschem/rx_bias.sch), read through rx_lib.sim_cells().
Two bands (layout/gen/rx_lib.py; the second mirrored onto the first's VDD rail), columns left to right:
  INV  : Ie (en -> enb)
  SW   : Msw (VDD -> vh, gate enb) over Moff / Moff2 (nb, x to VSS)
  MIR  : MP1 / MP2 as one diffusion, fingers A B B A with the shared source vh in the middle of each pair (common
         centroid, the 1:1 mirror); under it MN2 | MN1 | MN2 (two fingers of MN2 either side of the unit MN1: the
         K = 4 pair shares one centroid)
  START: MS1 (0.42 / 10, gate VSS) over MS2, MS3
  RB   : Rb (ppolyf_u, 2 um wide, 4 strips) next to MN2's source
  CAP  : Cnb (nfet gate cap on nb, 3 fingers)
Pins: VDD, VSS (rails, M2), en (M2, left edge), enb and nb (M2, right edge).
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rx_lib as R  # noqa: E402
from ring_core import Cell  # noqa: E402

PINS = ['VDD', 'VSS', 'en', 'enb', 'nb']
EXITS = dict(en=('right', None), enb=('right', None), nb=('right', None))
RISE = ['nb', 'enb', 'x', 'n2', 'vh', 'nr']


def cols():
    c = R.sim_cells()['rx_bias']
    d = lambda n: R.dev(c, n)
    m = lambda n, seq: R.from_dev(d(n), seq=seq)
    mp1, mp2 = d('MP1'), d('MP2')
    assert (mp1['w'], mp1['l'], mp1['m']) == (mp2['w'], mp2['l'], mp2['m']) == (4.0, 1.0, 2)
    mir_p = R.mos(mp1['w'], mp1['l'], ['nb', 'n2', 'vh', 'n2', 'n2', 'n2', 'vh', 'n2', 'nb'], 'VDD')  # A B B A
    mn1, mn2 = d('MN1'), d('MN2')
    assert mn2['m'] == 4 and mn1['m'] == 1 and mn1['w'] == mn2['w'] and mn1['l'] == mn2['l']
    half = R.mos(mn2['w'], mn2['l'], ['n2', 'nb', 'nr', 'nb', 'n2'], 'VSS')                          # 2 of 4
    unit = R.mos(mn1['w'], mn1['l'], ['VSS', 'nb', 'nb'], 'VSS')
    rb = d('Rb')
    cnb = d('Cnb')
    return [
        ('INV', [m('Iep', ['VDD', 'en', 'enb'])], [m('Ien', ['VSS', 'en', 'enb'])]),
        ('SW', [m('Msw', ['VDD', 'enb', 'vh'])], [m('Moff', ['VSS', 'enb', 'nb']), m('Moff2', ['VSS', 'enb', 'x'])]),
        ('MIR', [mir_p], [half, unit, dict(half)]),
        ('START', [m('MS1', ['vh', 'VSS', 'x'])], [m('MS2', ['VSS', 'nb', 'x']), m('MS3', ['n2', 'x', 'nb'])]),
        ('RB', [], [R.res('rpp', rb['w'], rb['l'], 'nr', 'VSS', 4)]),
        ('CAP', [], [R.from_dev(cnb, nf=3)]),
    ]


def build():
    cell = Cell('rx_bias')
    c = cols()
    b0 = R.Band('bias_mir', c[:3], ports=RISE, pins=PINS[2:], search=True)
    b1 = R.Band('bias_su', c[3:], ports=RISE, search=True)

    def exits(bands, xr):
        x = R.risers(bands, [n for n in RISE if all(n in b.span0 for b in bands)], xr)
        e0 = {n: [('top', v)] for n, v in x.items()}
        for n, e in EXITS.items():
            e0[n] = e0.get(n, []) + [e]
        return [e0, {n: ('top', v) for n, v in x.items()}]
    metas, bb = R.stack(cell, [b0, b1], exits)
    return [cell], dict(bbox=bb, bands=metas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(R.REPO / 'build' / 'rx_layout' / 'gen' / 'rx_bias'))
    ap.add_argument('--gds', default=str(R.REPO / 'layout' / 'rx_bias.gds'))
    a = ap.parse_args()
    cells, meta = build()
    R.save_meta(a.out, meta)
    log = R.write(cells, 'rx_bias', a.gds, a.out)
    print('rx_bias', R.bbox_str(meta['bbox']), 'magic log', log)


if __name__ == '__main__':
    main()
