#!/usr/bin/env python3
"""Layout of the receiver LNA rx_lna (stage 1 + the two stage-2 copies rx_lna2), gf180mcuD, 3.3 V devices.

    python3 layout/gen/rx_lna.py [--out build/rx_layout/gen/rx_lna] [--gds layout/rx_lna.gds]

Circuit and sizes: sim/rx/rx_lna.py block() (= xschem/rx_lna.sch + rx_lna2.sch), flattened (x2i_*, x2q_*).
Three bands (layout/gen/rx_lib.py), bottom to top:
  band 0  stage 2, Q copy (x2q): RLp | M1 / M2 | tail | RLn, then the vcm divider (Mvs, Rv1, Rv2) and 2 of
          Cvcm's 5 fingers
  band 1  stage 1 (mirrored, shares the VDD rail with band 0 and the VSS rail with band 2):
          Rgp Rgn | M1 / M2 | tail | RLp RLn
  band 2  stage 2, I copy (x2i): drawn exactly as band 0 (same columns, same orientation), then 3 of Cvcm's fingers
  (the divider and Cvcm sit in the outer bands so that all three bands are about as wide as stage 1)
  Pairs: one diffusion per pair, fingers A B B A (common source tail between each A-B pair, a shared drain between
  B-B and A-A): both centroids sit on the diffusion's centre line; a poly-only dummy finger 0.3 um past each end.
  Load resistors: ppolyf_u U-shapes, RLp and RLn side by side around the pair.
  Stage 1's outputs (outp, outn), nb and vcm climb to bands 0 and 2 on M3 risers (one x per net through all bands).
Pins: VDD, VSS (rails), inp, inn (M2, left edge, band 1), oip, oin (M2, right edge, band 2: the I mixer sits
up there in rx_top), oqp, oqn, nb, enb (M2, right edge, band 0: the Q mixer below it).
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rx_lib as R  # noqa: E402
from ring_core import Cell  # noqa: E402

PINS = ['VDD', 'VSS', 'inp', 'inn', 'oip', 'oin', 'oqp', 'oqn', 'nb', 'enb']
NF = 10.0           # finger W (um) of the pairs and tails


def devs():
    return {d['name']: d for d in R.flat_devs(R.sim_cells(), 'rx_lna')}


def abba(a, b, n):
    """Region / gate sequence for pair devices a, b (n fingers each, n even): A B B A ... with shared sources."""
    (da, ga, sa), (db, gb, sb) = (a['nets'][:3]), (b['nets'][:3])
    assert sa == sb and n % 2 == 0
    seq = [da]
    for k in range(n // 2):
        seq += [ga, sa, gb, db, gb, sa, ga, da]
    # A B B A per two fingers each -> the pattern above has 2 A + 2 B per k; trim to n each
    gates = seq[1::2]
    assert gates.count(ga) == n and gates.count(gb) == n, (gates.count(ga), n)
    return seq


def pair(a, b):
    assert a['w'] == b['w'] and a['l'] == b['l'] and a['m'] == b['m'] and a['w'] == NF
    return R.mos(NF, a['l'], abba(a, b, a['m']), 'VSS', dummy=True)


def tail(t):
    nf = round(t['w'] * t['m'] / NF)
    assert abs(nf * NF - t['w'] * t['m']) < 1e-6
    return R.from_dev(t, nf=nf)


def load(r, n=2):
    return R.res('rpp', r['w'], r['l'], r['nets'][0], r['nets'][1], n)


def stage2(D, p):
    """Columns of one stage-2 copy (p = 'x2i_' / 'x2q_')."""
    return [('RLp', [], [load(D[p + 'RLp'])]),
            ('PAIR', [], [pair(D[p + 'M1'], D[p + 'M2'])]),
            ('TAIL', [], [tail(D[p + 'Mt'])]),
            ('RLn', [], [load(D[p + 'RLn'])])]


def hr(D, n, k):
    return R.res('hires', D[n]['w'], D[n]['l'], D[n]['nets'][0], D[n]['nets'][1], k)


def cvcm(D, nf, of=5):
    """nf of Cvcm's `of` fingers (Cvcm is split between bands 0 and 2; netgen adds parallel W)."""
    d = D['Cvcm']
    D_, G, S, B = d['nets']
    seq = [S] + [G, S] * nf
    return R.mos(d['w'] * d['m'] / of, d['l'], seq, B)


def stage1(D):
    return [('RG', [], [hr(D, 'Rgp', 4), hr(D, 'Rgn', 4)]),
            ('PAIR', [], [pair(D['M1'], D['M2'])]),
            ('TAIL', [], [tail(D['Mt'])]),
            ('RL', [], [load(D['RLp']), load(D['RLn'])])]


def build():
    D = devs()
    cell = Cell('rx_lna')
    rv = [('RV', [R.from_dev(D['Mvs'], seq=['VDD', 'enb', 'vt'])], [hr(D, 'Rv1', 4), hr(D, 'Rv2', 4)])]
    up = ['outp', 'outn', 'nb', 'vcm']
    b0 = R.Band('lna_q', stage2(D, 'x2q_') + rv + [('CV', [], [cvcm(D, 2)])], ports=up,
                pins=['enb', 'oqp', 'oqn', 'nb'], search=False)
    b1 = R.Band('lna_1', stage1(D), ports=up, pins=['inp', 'inn'], search=False)
    b2 = R.Band('lna_i', stage2(D, 'x2i_') + [('CV', [], [cvcm(D, 3)])], ports=up, pins=['oip', 'oin'],
                search=False)

    def exits(bands, xr):
        x = R.risers(bands, up, xr)
        return [dict(enb=('right', None), oqp=('right', None), oqn=('right', None),
                     nb=[('top', x['nb']), ('right', None)], **{n: ('top', x[n]) for n in up if n != 'nb'}),
                dict(inp=('left', None), inn=('left', None), **{n: ('through', x[n]) for n in up}),
                dict(oip=('right', None), oin=('right', None), **{n: ('bottom', x[n]) for n in up})]
    metas, bb = R.stack(cell, [b0, b1, b2], exits)
    return [cell], dict(bbox=bb, bands=metas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(R.REPO / 'build' / 'rx_layout' / 'gen' / 'rx_lna'))
    ap.add_argument('--gds', default=str(R.REPO / 'layout' / 'rx_lna.gds'))
    a = ap.parse_args()
    cells, meta = build()
    R.save_meta(a.out, meta)
    log = R.write(cells, 'rx_lna', a.gds, a.out)
    print('rx_lna', R.bbox_str(meta['bbox']), 'magic log', log)


if __name__ == '__main__':
    main()
