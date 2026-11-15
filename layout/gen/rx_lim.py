#!/usr/bin/env python3
"""Layout of one limiter + comparator arm rx_lim, gf180mcuD, 3.3 V devices.

    python3 layout/gen/rx_lim.py [--out build/rx_layout/gen/rx_lim] [--gds layout/rx_lim.gds]

Circuit and sizes: sim/rx/rx_lim.py block() (= xschem/rx_lim.sch).
Two bands (layout/gen/rx_lib.py), bottom to top:
  1  signal band, along the signal flow. N row: the limiter pair MLa / MLb (A B B A, poly dummies) and MtL, the
     comparator pair C1 / C2 (A B B A) and Ct, C9 / C10, the output inverters' n halves B1n / B2n, then Cvb.
     P row: Mvbs, the AC-coupling caps CcLa / CcLb (input) and CcCa / CcCb (limiter to comparator), each in its own
     n-well (bulk = the node it hangs from, gate on the high-impedance node); the comparator loads C3-C8; B1p, B2p.
     The comparator's output q leaves at the right edge, as far as the cell allows from the input couplings (left).
  2  (mirrored, shares band 1's VDD rail) P row: the pseudo-resistors in n-well islands by bulk (vb: Mvbrep and every
     Rp..r / Rp..b; one tiny well per coupling node glp, gln, gcp, gcn). N row: RLa / RLb (ppolyf_u), Rvb1, Rvb2
     (ppolyf_u_1k) and Mvbsnk.
  Nets between the bands climb on M3 risers.
Pins: VDD, VSS (rails), inp, inn, enb, nb (M3, bottom edge), q (M3, top edge, through band 2). The receiver's
signal flows up in rx_top: the baseband below, q out of the top edge.
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rx_lib as R  # noqa: E402
from ring_core import Cell  # noqa: E402

CELL = 'rx_lim'
BB = R.load_gen('rx_bb')
abba, cap, one, hres = BB.abba, BB.cap, BB.one, BB.hres

RISE = ['glp', 'gln', 'gcp', 'gcn', 'vb', 'vbt', 'lp', 'ln', 'nb']


def bands(D):
    inv = lambda n: (one(D[n + 'p'], ['VDD', D[n + 'p']['nets'][1], D[n + 'p']['nets'][0]]),
                     one(D[n + 'n'], ['VSS', D[n + 'n']['nets'][1], D[n + 'n']['nets'][0]]))
    b1p, b1n = inv('B1')
    b2p, b2n = inv('B2')
    pd = lambda n: one(D[n], ['VDD', D[n]['nets'][1], D[n]['nets'][0]])       # comparator pfet, source VDD
    B1 = [('LIM', [one(D['Mvbs'], ['VDD', 'enb', 'vbt']), cap(D['CcLa'], 12.285), cap(D['CcLb'], 12.285)],
           [abba(D['MLa'], D['MLb']), one(D['MtL'])]),
          ('CMP', [cap(D['CcCa'], 12.285), cap(D['CcCb'], 12.285)] + [pd(n) for n in ('C3', 'C5', 'C6', 'C4')],
           [abba(D['C1'], D['C2']), one(D['Ct'])]),
          ('OUT', [pd('C7'), pd('C8'), b1p, b2p],
           [one(D['C9'], ['VSS', 'cx', 'cx']), one(D['C10'], ['VSS', 'cx', 'co']), b1n, b2n,
            cap(D['Cvb'], 12.285)])]
    rp = lambda s: [one(D[f'Rp{s}ar']), one(D[f'Rp{s}ab'], ['vb', f'mRp{s}a', f'mRp{s}a']),
                    one(D[f'Rp{s}br']), one(D[f'Rp{s}bb'], ['vb', f'mRp{s}b', f'mRp{s}b'])]
    tiny = lambda s, a, b: [one(D[f'Rp{s}aa'], [a, f'mRp{s}a', f'mRp{s}a']),
                            one(D[f'Rp{s}ba'], [b, f'mRp{s}b', f'mRp{s}b'])]
    B2 = [('PRL', [one(D['Mvbrep'], ['vb', 'vgr', 'vgr'])] + rp('L') + tiny('L', 'glp', 'gln'),
           [R.res('rpp', D['RLa']['w'], D['RLa']['l'], D['RLa']['nets'][0], 'VDD', 4),
            R.res('rpp', D['RLb']['w'], D['RLb']['l'], D['RLb']['nets'][0], 'VDD', 4), hres(D['Rvb1'], 12)]),
          ('PRC', rp('C') + tiny('C', 'gcp', 'gcn'), [hres(D['Rvb2'], 8), one(D['Mvbsnk'])])]
    return B1, B2


def build(cell_name=CELL):
    D = {d['name']: d for d in R.flat_devs(R.sim_cells(), CELL)}
    B1, B2 = bands(D)
    cell = Cell(cell_name)
    b1 = R.Band('lim_sig', B1, ports=RISE + ['q'], pins=['inp', 'inn', 'nb', 'enb'], search=True)
    b2 = R.Band('lim_bias', B2, ports=RISE + ['q'], pins=['q'], search=False)

    def exits(bands_, xr):
        x = R.risers(bands_, RISE + ['q'], xr)
        e1 = {n: ('top', x[n]) for n in RISE if n != 'nb'}
        e1['nb'] = ('throughb', x['nb'])
        e1.update(inp=('bottom', None), inn=('bottom', None), enb=('bottom', None), q=('top', x['q']))
        e2 = {n: ('top', x[n]) for n in RISE}
        e2['q'] = ('throughb', x['q'])                  # band 2 is mirrored: its local bottom is the cell top
        return [e1, e2]
    metas, bb = R.stack(cell, [b1, b2], exits)
    return [cell], dict(bbox=bb, bands=metas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(R.REPO / 'build' / 'rx_layout' / 'gen' / CELL))
    ap.add_argument('--gds', default=str(R.REPO / 'layout' / f'{CELL}.gds'))
    a = ap.parse_args()
    cells, meta = build()
    R.save_meta(a.out, meta)
    log = R.write(cells, CELL, a.gds, a.out)
    print(CELL, R.bbox_str(meta['bbox']), 'magic log', log)


if __name__ == '__main__':
    main()
