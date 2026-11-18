#!/usr/bin/env python3
"""Layout of the passive double-balanced mixer rx_mix (four transmission gates + hold caps), gf180mcuD.

    python3 layout/gen/rx_mix.py [--out build/rx_layout/gen/rx_mix] [--gds layout/rx_mix.gds]

Circuit and sizes: sim/rx/rx_mix.py block() (= xschem/rx_mix.sch).
One band (layout/gen/rx_lib.py):
  Cbp (3 fingers) | NMOS switches (N row) | Cbn (3 fingers), with the PMOS switches in the P row above Cbn
  (2026-11-16: was a column of its own, 51.3 x 36.1 um; now 44.4 x 28.1 um)
  switches: the four NMOS on one diffusion   rfp |S1 lo| bbp |S3 lob| rfn |S2 lo| bbn |S4 lob| rfp
            the four PMOS on one diffusion, two fingers of W/2 each (2026-11-16: the P row is half as tall), mirrored
            rfp |S1| bbp |S3| rfn |S2| bbn |S4| rfp |S4| bbn |S2| rfn |S3| bbp |S1| rfp   (gates lob lo lob lo lo lob lo lob)
            so each switch's two fingers sit symmetric about the centre (common centroid)
  each diffusion is symmetric (rf at both ends and in the middle). The N and P diffusions
  stand side by side, not one above the other: a transmission gate's N and P gates are complementary, so stacked
  they would ask for lo below lob at one finger and above it at the next (a track-order cycle in the channel). lo and lob leave on M3 straight up through the VDD rail (right angles to the rf / bb
  tracks), rf on the left edge (the LNA's side in rx_top), bb on the right edge (M2).
Pins: VDD, VSS (rails), bbp, bbn (M2, right edge), lo, lob (M3, top edge); rfp, rfn: build(pins='tile') (default,
the tile floorplan) M3 on the bottom edge at its left end (one cell for mix_i and mix_q: the corner serves mix_i's
"bottom edge, left end" and mix_q's "left edge"); build(pins='rx_top') M2 on the left edge (rx_top.py).
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rx_lib as R  # noqa: E402
from ring_core import Cell  # noqa: E402

PINS = ['VDD', 'VSS', 'rfp', 'rfn', 'bbp', 'bbn', 'lo', 'lob']
EXITS = dict(rfp=('left', None), rfn=('left', None), bbp=('right', None), bbn=('right', None),
             lo=('top', None), lob=('top', None))                               # rx_top
TILE = dict(EXITS, rfp=('bottom', 1360), rfn=('bottom', 2720))                    # the tile: rf at the lower-left


def cols():
    c = R.sim_cells()['rx_mix']
    d = lambda n: R.dev(c, n)
    sn = {k: d(k) for k in ('S1n', 'S2n', 'S3n', 'S4n')}
    sp = {k: d(k) for k in ('S1p', 'S2p', 'S3p', 'S4p')}
    wn, wp = {x['w'] for x in sn.values()}, {x['w'] for x in sp.values()}
    assert len(wn) == len(wp) == 1 and all(x['m'] == 1 for x in list(sn.values()) + list(sp.values()))
    # every switch's nets as drawn must be the netlister's (d, g, s) up to d/s swap
    nseq = ['rfp', 'lo', 'bbp', 'lob', 'rfn', 'lo', 'bbn', 'lob', 'rfp']
    pseq = ['rfp', 'lob', 'bbp', 'lo', 'rfn', 'lob', 'bbn', 'lo', 'rfp', 'lo', 'bbn', 'lob', 'rfn', 'lo', 'bbp', 'lob', 'rfp']
    for seq, devs in ((nseq, sn), (pseq, sp)):
        drawn = sorted({(tuple(sorted((seq[i - 1], seq[i + 1]))), seq[i]) for i in range(1, len(seq), 2)})
        want = sorted((tuple(sorted((x['nets'][0], x['nets'][2]))), x['nets'][1]) for x in devs.values())
        assert drawn == want, (drawn, want)
    L = sn['S1n']['l']
    cbp, cbn = d('Cbp'), d('Cbn')
    return [
        ('CBP', [], [R.from_dev(cbp, nf=3)]),
        ('SWN', [], [R.mos(wn.pop(), L, nseq, 'VSS')]),
        # the PMOS switches (2 fingers per switch) over Cbn, not in a column of their own: 44 um wide, not 56
        ('CBN', [R.mos(wp.pop() / 2, L, pseq, 'VDD')], [R.from_dev(cbn, nf=3)]),
    ]


def build(pins='tile'):
    assert pins in ('tile', 'rx_top'), pins
    cell = Cell('rx_mix')
    band = R.Band('rx_mix', cols(), pins=PINS[2:], search=True)
    metas, bb = R.stack(cell, [band], [EXITS if pins == 'rx_top' else TILE])
    return [cell], dict(bbox=bb, bands=metas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(R.REPO / 'build' / 'rx_layout' / 'gen' / 'rx_mix'))
    ap.add_argument('--gds', default=str(R.REPO / 'layout' / 'rx_mix.gds'))
    a = ap.parse_args()
    cells, meta = build()
    R.save_meta(a.out, meta)
    log = R.write(cells, 'rx_mix', a.gds, a.out)
    print('rx_mix', R.bbox_str(meta['bbox']), 'magic log', log)


if __name__ == '__main__':
    main()
