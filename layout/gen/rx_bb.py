#!/usr/bin/env python3
"""Layout of one baseband arm rx_bb (three differential stages, two AC couplings, vb / vgr bias), gf180mcuD.

    python3 layout/gen/rx_bb.py [--out build/rx_layout/gen/rx_bb] [--gds layout/rx_bb.gds]

Circuit and sizes: sim/rx/rx_bb.py block() (= xschem/rx_bb.sch).
Three bands (layout/gen/rx_lib.py), bottom to top:
  A  NN band (n devices on both sides of the channel, VSS rails top and bottom): the low-pass caps C2a, C3a (top
     row, with Mvbsnk, the 0.42 / 50 um vgr sink) and C2b, C3b (bottom row, with Cvb and Rvb2), 4 fingers of
     24.57 um each. The caps are 4.2 of this arm's 7.2 thousand um2 of devices, so they get their own band.
  B  signal band. N row, along the signal flow: stage 1 pair M1a / M1b (16 + 16 fingers of 20 um, A B B A, common
     source t1, poly dummies), its tail Mt1, stage 2 (M2a / M2b A B B A, Mt2f), stage 3 (M3a / M3b, Mt3f).
     P row, above them: Mvbs, the AC-coupling caps Cc2a, Cc2b (over stage 1) and Cc3a, Cc3b (over stages 2 and 3),
     each a pfet in its own n-well (its bulk is the stage output it hangs from), gate on the high-impedance node.
  C  (mirrored: shares B's VDD rail) P row: the pseudo-resistors, in n-well islands by bulk: vb (Mvbrep and every
     Rp..r / Rp..b) and one tiny well per coupling node (Rp2aa on g2p, ...: the bulk is that ~60 MOhm node).
     N row: the loads R1a / R1b (ppolyf_u), R2a / R2b, R3a / R3b and Rvb1 (ppolyf_u_1k serpentines).
  Nets between bands climb on M3 risers. The coupling nodes g2p / g2n / g3p / g3n run only between B and C, short.
Pins: VDD, VSS (rails), inp, inn (M2, left edge, band B), outp, outn (M2, right edge, band B), nb (M3, bottom
edge), enb (M2, left edge, band B).
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rx_lib as R  # noqa: E402
from ring_core import Cell  # noqa: E402

PINS = ['VDD', 'VSS', 'inp', 'inn', 'outp', 'outn', 'nb', 'enb']
CELL = 'rx_bb'


def devs(cell=CELL):
    return {d['name']: d for d in R.flat_devs(R.sim_cells(), cell)}


def abba(a, b):
    """A B B A pair with shared sources (rx_lna.abba), poly dummies at both ends; fingers of the device W."""
    (da, ga, sa), (db, gb, sb) = a['nets'][:3], b['nets'][:3]
    assert sa == sb and a['m'] == b['m'] and a['m'] % 2 == 0 and a['w'] == b['w'] and a['l'] == b['l']
    seq = [da]
    for k in range(a['m'] // 2):
        seq += [ga, sa, gb, db, gb, sa, ga, da]
    return R.mos(a['w'], a['l'], seq, 'VSS', dummy=True)


def cap(d, wf):
    """nfet / pfet gate cap d as fingers of wf (um): S/D/B on one net, gate on the other."""
    D_, G, S, B = d['nets']
    nf = round(d['w'] * d['m'] / wf)
    assert abs(nf * wf - d['w'] * d['m']) < 1e-3, (d['name'], nf, wf)
    seq = [S] + [G, S] * nf
    return R.mos(d['w'] * d['m'] / nf, d['l'], seq, B)


def one(d, seq=None):
    """Single device, drawn [s, g, d] (or the given order)."""
    D_, G, S, B = d['nets']
    return R.mos(d['w'] * d['m'], d['l'], seq or [S, G, D_], B)


def hres(d, n):
    return R.res('hires', d['w'], d['l'], d['nets'][0], d['nets'][1], n)


def bands(D):
    nf_t1 = 2
    # NN band: R.Band's P list is its top row
    A = [('CAPS', [cap(D['C2a'], 24.57), cap(D['C3a'], 24.57), one(D['Mvbsnk'])],
          [cap(D['C2b'], 24.57), cap(D['C3b'], 24.57), cap(D['Cvb'], 24.57), hres(D['Rvb2'], 6)])]
    B = [('S1', [one(D['Mvbs'], ['VDD', 'enb', 'vbt']), cap(D['Cc2a'], 12.285), cap(D['Cc2b'], 12.285)],
          [abba(D['M1a'], D['M1b']), R.from_dev(D['Mt1'], nf=nf_t1)]),
         ('S23', [cap(D['Cc3a'], 12.285), cap(D['Cc3b'], 12.285)],
          [abba(D['M2a'], D['M2b']), one(D['Mt2f']), abba(D['M3a'], D['M3b']), one(D['Mt3f'])])]
    rp = lambda s: [one(D[f'Rp{s}ar']), one(D[f'Rp{s}ab'], ['vb', f'mRp{s}a', f'mRp{s}a']),
                    one(D[f'Rp{s}br']), one(D[f'Rp{s}bb'], ['vb', f'mRp{s}b', f'mRp{s}b'])]
    C = [('C1', [one(D['Mvbrep'], ['vb', 'vgr', 'vgr'])] + rp('2')
          + [one(D['Rp2aa'], ['g2p', 'mRp2a', 'mRp2a']), one(D['Rp2ba'], ['g2n', 'mRp2b', 'mRp2b'])],
          [R.res('rpp', D['R1a']['w'], D['R1a']['l'], D['R1a']['nets'][0], 'VDD', 4),
           R.res('rpp', D['R1b']['w'], D['R1b']['l'], D['R1b']['nets'][0], 'VDD', 4), hres(D['Rvb1'], 8)]),
         ('C2', rp('3') + [one(D['Rp3aa'], ['g3p', 'mRp3a', 'mRp3a']), one(D['Rp3ba'], ['g3n', 'mRp3b', 'mRp3b'])],
          [hres(D['R2a'], 10), hres(D['R2b'], 10), hres(D['R3a'], 10), hres(D['R3b'], 10)])]
    return A, B, C


RISE_AB = ['o2p', 'o2n', 'outp', 'outn', 'vb', 'vgr', 'nb']
RISE_BC = ['o1p', 'o1n', 'o2p', 'o2n', 'outp', 'outn', 'g2p', 'g2n', 'g3p', 'g3n', 'vb', 'vgr', 'vbt']


def build(cell_name=CELL):
    D = devs()
    A, B, C = bands(D)
    cell = Cell(cell_name)
    bA = R.Band('bb_caps', A, ports=RISE_AB, pins=['nb'], top='N', search=False)
    bB = R.Band('bb_sig', B, ports=RISE_AB + RISE_BC, pins=['inp', 'inn', 'outp', 'outn', 'enb'], search=False)
    bC = R.Band('bb_bias', C, ports=RISE_BC, search=False)
    risers = sorted(set(RISE_AB) | set(RISE_BC))

    def exits(bands_, xr):
        x = R.risers(bands_, risers, xr)
        ea = {n: ('top', x[n]) for n in RISE_AB if n != 'nb'}
        ea['nb'] = ('throughb', x['nb'])
        eb = {}
        for n in risers:
            inA, inC = n in RISE_AB, n in RISE_BC
            if n == 'nb':
                eb[n] = ('bottom', x[n])
            elif inA and inC:
                eb[n] = ('through', x[n])
            elif inA:
                eb[n] = ('bottom', x[n])
            else:
                eb[n] = ('top', x[n])
        eb.update(inp=('left', None), inn=('left', None), enb=('left', None))
        eb['outp'] = [eb['outp'], ('right', None)]
        eb['outn'] = [eb['outn'], ('right', None)]
        ec = {n: ('top', x[n]) for n in RISE_BC}       # C is mirrored: its local top (VDD rail) faces band B
        return [ea, eb, ec]
    metas, bb = R.stack(cell, [bA, bB, bC], exits)
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
