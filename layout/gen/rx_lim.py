#!/usr/bin/env python3
"""Layout of one limiter + comparator arm rx_lim, gf180mcuD, 3.3 V devices.

    python3 layout/gen/rx_lim.py [--out build/rx_layout/gen/rx_lim] [--gds layout/rx_lim.gds]

Circuit and sizes: sim/rx/rx_lim.py block() (= xschem/rx_lim.sch).
Two bands (layout/gen/rx_lib.py), bottom to top:
  1  signal band, along the signal flow. N row: the limiter pair MLa / MLb (A B B A, poly dummies) and MtL, the
     comparator pair C1 / C2 (A B B A) and Ct, C9 / C10, the output inverters' n halves B1n / B2n, all on the VSS
     rail, with Mvbsnk (0.42 / 50 um) as an overlay along the channel edge over them (rx_lib Band overlay;
     2026-11-16: Mvbsnk was in band 2 and set the cell width, Cvb in this row set its height).
     P row: Mvbs, the AC-coupling caps CcLa / CcLb (input) and CcCa / CcCb (limiter to comparator), each in its own
     n-well (bulk = the node it hangs from, gate on the high-impedance node); the comparator loads C3-C8; B1p, B2p.
     The comparator's output q leaves at the right edge, as far as the cell allows from the input couplings (left).
  2  (mirrored, shares band 1's VDD rail) P row: the pseudo-resistors in n-well islands by bulk (vb: Mvbrep and every
     Rp..r / Rp..b; one tiny well per coupling node glp, gln, gcp, gcn). N row: RLa / RLb (ppolyf_u), Rvb1, Rvb2
     (ppolyf_u_1k) and Cvb (vb's decap, next to the vb devices).
  Nets between the bands climb on M3 risers.
Pins: VDD, VSS (rails); build(pins='rx_top'): inp, inn, enb, nb (M3, bottom edge), q (M3, top edge, through band 2).
The receiver's signal flows up in rx_top: the baseband below, q out of the top edge.
build(pins='tile') (default, the tile floorplan; one cell for lim_i and lim_q, both placed MX): inp, inn (M3,
bottom edge, left end) and q (M2, left edge, as low as it goes): the lower-left corner serves lim_i's "q on the left
edge at the bottom, inputs on the bottom edge's left end" and lim_q's "q on the bottom edge's left end, inputs on
the left edge at the bottom". q leaves the comparator on M3 straight down to an M2 run just over the bottom VSS rail
(under the N row, which has no M2; it crosses the pairs' gate end caps at right angles, both halves of each A B B A
pair alike) to the left edge: not along the channel, where its track would run beside the coupling nodes gcp / gcn.
nb, enb twice (DC nets): M3 at the bottom edge's right end (lim_i) and, up a band-1 riser at the same x, M2 on the
right edge in band 2's channel (lim_q's "right edge, y 38").
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

RISE = ['glp', 'gln', 'gcp', 'gcn', 'vgr', 'vbt', 'lp', 'ln']


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
           [one(D['C9'], ['VSS', 'cx', 'cx']), one(D['C10'], ['VSS', 'cx', 'co']), b1n, b2n])]
    rp = lambda s: [one(D[f'Rp{s}ar']), one(D[f'Rp{s}ab'], ['vb', f'mRp{s}a', f'mRp{s}a']),
                    one(D[f'Rp{s}br']), one(D[f'Rp{s}bb'], ['vb', f'mRp{s}b', f'mRp{s}b'])]
    tiny = lambda s, a, b: [one(D[f'Rp{s}aa'], [a, f'mRp{s}a', f'mRp{s}a']),
                            one(D[f'Rp{s}ba'], [b, f'mRp{s}b', f'mRp{s}b'])]
    B2 = [('PRL', [one(D['Mvbrep'], ['vb', 'vgr', 'vgr'])] + rp('L') + tiny('L', 'glp', 'gln'),
           [R.res('rpp', D['RLa']['w'], D['RLa']['l'], D['RLa']['nets'][0], 'VDD', 4),
            R.res('rpp', D['RLb']['w'], D['RLb']['l'], D['RLb']['nets'][0], 'VDD', 4), hres(D['Rvb1'], 12)]),
          ('PRC', rp('C') + tiny('C', 'gcp', 'gcn'), [hres(D['Rvb2'], 8), cap(D['Cvb'], 12.285)])]
    return B1, B2


def build(cell_name=CELL, pins='tile'):
    assert pins in ('tile', 'rx_top'), pins
    D = {d['name']: d for d in R.flat_devs(R.sim_cells(), CELL)}
    B1, B2 = bands(D)
    cell = Cell(cell_name)
    b1 = R.Band('lim_sig', B1, ports=RISE + ['q', 'nb'], pins=['inp', 'inn', 'nb', 'enb'], search=True,
                overlay=[one(D['Mvbsnk'])])
    if pins == 'tile':
        b2 = R.Band('lim_bias', B2, ports=RISE + ['nb', 'enb'], pins=['nb', 'enb'], search=False)
    else:
        b2 = R.Band('lim_bias', B2, ports=RISE + ['q'], pins=['q'], search=False)

    def exits_tile(bands_, xr):
        x = R.risers(bands_, RISE, xr)
        G = R.GRID
        xs = dict(inp=9 * G, inn=11 * G, nb=159 * G, enb=161 * G)      # 6.12, 7.48 (left of lp's riser), 108.12, 109.48
        for n, v in xs.items():
            assert all(abs(v - u) >= R.M3P for u in x.values()), (n, v)
        assert xs['enb'] + 190 + 280 <= xr - R.STRAPX1, (xr, xs['enb'])            # clear of the right M3 strap
        e1 = {n: ('top', x[n]) for n in RISE}
        e1.update({n: ('bottom', xs[n]) for n in ('inp', 'inn')})
        qx.append(bands_[0].span0['q'][1])           # q's M3 drop (drawn below), kept free in both bands
        assert all(abs(qx[0] - u) >= R.M3P for u in list(x.values()) + list(xs.values()))
        e1.update({n: ('throughb', xs[n]) for n in ('nb', 'enb')})
        e2 = {n: ('top', x[n]) for n in RISE}
        e2.update({n: [('top', xs[n]), ('right', None)] for n in ('nb', 'enb')})
        return [e1, e2]

    def exits(bands_, xr):
        x = R.risers(bands_, RISE + ['q'], xr)
        e1 = {n: ('top', x[n]) for n in RISE}
        e1['nb'] = ('bottom', None)
        e1.update(inp=('bottom', None), inn=('bottom', None), enb=('bottom', None), q=('top', x['q']))
        e2 = {n: ('top', x[n]) for n in RISE}
        e2['q'] = ('throughb', x['q'])                  # band 2 is mirrored: its local bottom is the cell top
        return [e1, e2]
    qx = []
    metas, bb = R.stack(cell, [b1, b2], exits if pins == 'rx_top' else exits_tile, m3_shared=qx)
    if pins == 'tile':
        # q: via2 on its track, M3 down to just over the bottom VSS rail (local y 0), via2, M2 to the left edge
        k, ty, _ = metas[0]['tracks']['q']
        assert not metas[0]['flip'] and metas[0]['Y']['vss_t'] == 0
        x, yp = qx[0], 700
        cell.r('v2', x - 140, ty - 140, x + 140, ty + 140)
        cell.r('m3', x - 190, yp - 190, x + 190, ty + 190)
        cell.r('v2', x - 140, yp - 140, x + 140, yp + 140)
        cell.r('m2', 0, yp - 190, x + 190, yp + 190)
        cell.label('q', 'm2', 150, yp, port=True)
        # band 2's nb / enb risers are not pins (only their right-edge exits)
        R.edge_ports_only(cell, bb, ('nb', 'enb'))
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
