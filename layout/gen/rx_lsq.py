#!/usr/bin/env python3
"""Layout of the Q-tap level shifter rx_lsq: a geometric copy of lsdiv's level shifter, gf180mcuD.

    python3 layout/gen/rx_lsq.py [--out build/rx_layout/gen/rx_lsq] [--gds layout/rx_lsq.gds]

Circuit: sim/rx/rx_lo.py rx_lsq (= xschem/rx_lsq.sch): ls_ac (Cc, LRB, INV1-3, R1, C1) + the first TSPC stage
tspc_t1 (D1, output unused) + the TX-tap stand-in TT + Dq (holds lsq low when qenb = 1), on vq behind the header Hq,
with the decap Cq on vq.

Why a copy of the geometry, not of the schematic: the I/Q phase depends on the two level shifters delaying their
ring taps by the same amount (docs/rx_design.md, "LO taps (A1)": a schematic-only copy gave 7.6 deg instead of 72).
So this generator runs layout/gen/lsdiv.py's own build() (imported, not edited) with two changes:
  - its column list: B1 and D2 (the /4's second stage and its buffer, which the Q tap doesn't have) are replaced by
    one column with TT and Dq;
  - lsdiv's strip() is wrapped so that this column reserves exactly the width B1 and D2 had (PAD). Everything from
    D1 to the right edge (D1, INV3, INV2, INV1, LRB, Cc, R1, C1, every channel track of those nets) then lands at
    the same coordinates as in layout/lsdiv.gds (asserted below against an unpatched build).
  TT and Dq hang on their own net lsx, joined to the level-shifter output by an M3 jumper to lsdiv's ls M3 vertical
  (so lsdiv's channel sees exactly the nets it always had).
lsdiv's VDD rail becomes vq. Above lsdiv's top VSS rail one more band (layout/gen/rx_lib.py) holds Hq (P row, real
VDD) and Cq (N row) with the real VDD rail on top; vq and qenb reach it on M3 risers.
Pins: VDD (top rail), VSS (rails), aq (M2, right edge, lsdiv's a0 pin), qenb (M3, top edge); lsq: build(pins='tile')
(default, the tile floorplan) M2 on the left edge at the bottom (lsdiv's ls M3 vertical goes down instead of up, to
an M2 run under the N row, just over the bottom VSS rail); build(pins='rx_top') M3 on the top edge (rx_top.py).
Nothing of lsdiv's level shifter (aq to lsq) moves: only the lsq wire past lsdiv's ls vertical changes.
"""
import argparse
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rx_lib as R  # noqa: E402
from ring_core import Cell  # noqa: E402

PAD = 7930          # extra width of the TT / Dq column = B1 + D2 in lsdiv (D1 lands at lsdiv's x; asserted)
PINS = ['VDD', 'VSS', 'aq', 'qenb', 'lsq']


def lsdiv_build(patch):
    """lsdiv.py build(), unpatched or with the rx_lsq column list. Returns (cell, meta, strips drawn)."""
    L = R.load_gen('lsdiv')
    orig_strip = L.strip
    log = []

    def strip(c, x0, ybot, W, seq, Lg, typ, chan):
        x1, t, g = orig_strip(c, x0, ybot, W, seq, Lg, typ, chan)
        if getattr(c, 'name', '') == 'lsdiv':
            log.append((x0, ybot, typ, tuple(seq)))
        if patch and typ == 'n' and 'qenb' in seq:
            x1 += PAD
        return x1, t, g
    L.strip = strip
    if patch:
        D = {d['name']: d for d in R.flat_devs(R.sim_cells(), 'rx_lsq')}
        ttp, ttn, dq = D['TTp'], D['TTn'], D['Dq']
        assert ttp['nets'][:3] == ['tt', 'lsq', 'vq'] and ttn['nets'][:3] == ['tt', 'lsq', 'VSS']
        assert dq['nets'][:3] == ['lsq', 'qenb', 'VSS']
        tt = ('TT', [(ttp['w'], ['VDD', 'lsx', 'q2'], ttp['l'])],
              [(ttn['w'], ['VSS', 'lsx', 'q2'], ttn['l']), (dq['w'], ['VSS', 'qenb', 'lsx'], dq['l'])])
        orig = L.columns()
        assert [c[0] for c in orig] == ['B1', 'D2', 'D1', 'INV3', 'INV2', 'INV1', 'LRB']
        L.columns = lambda: [tt] + orig[2:]
    cells, meta = L.build()
    return cells[0], meta, log


def build(pins='tile'):
    assert pins in ('tile', 'rx_top'), pins
    c0, m0, log0 = lsdiv_build(False)
    cell, m, log1 = lsdiv_build(True)
    # the copy: every strip from D1 rightwards and the passive band at lsdiv's coordinates
    keep0 = {x for x in log0 if not ({'ck', 'D2x', 'D2y', 'D2qb', 'q2'} & set(x[3]))}
    keep1 = {x for x in log1 if not ({'lsx', 'q2', 'qenb'} & set(x[3]))}
    assert keep0 == keep1, keep0 ^ keep1
    for k in ('Y', 'bbox', 'cc', 'r1', 'c1', 'lf_x', 'ls_x'):
        assert m0[k] == m[k], k
    for n in ('D1qb', 'D1x', 'D1y', 'lf', 'lg', 'lo1', 'lo2', 'ls'):
        assert m0['tracks'][n] == m['tracks'][n], n
    cell.name = 'rx_lsq'
    Y, bb, T = m['Y'], m['bbox'], m['tracks']
    xr = bb[2]
    ls_x = m['ls_x']
    # ---- labels: lsdiv names -> rx_lsq names; drop the unused ck pin stub (its track has no terminal) ----
    ck_y = T['ck'][1]
    cell.rects = [r for r in cell.rects if not (r[0] == 'm2' and r[2] == ck_y - 190 and r[4] == ck_y + 190
                                                 and r[1] in (0, 110) and r[3] in (300, 490))]
    ren = dict(VDD='vq', a0='aq', ls='lsq', q2='tt')
    labels = []
    for (t, l, x, y, port) in cell.labels:
        if t == 'ck':
            continue
        if t == 'ls' and l == 'm3':            # the TX-tap pin: replaced by the lsq pin at the new top edge
            continue
        t2 = ren.get(t, t)
        labels.append((t2, l, x, y, port and t2 in PINS))
    cell.labels = labels
    for n in ('D1x', 'D1y', 'D1qb', 'qenb'):
        k, ty, (a, b) = T[n]
        cell.label(n, 'm2', R.snap((a + b) / 2), ty)
    # ---- lsx (TT, Dq) -> lsq: via2 at the lsx track's right end, M3 along the track's y to ls_x, up to the ls track
    k, y_lsx, (a, b) = T['lsx']
    y_ls = T['ls'][1]
    cell.r('m2', b - 190, y_lsx - 190, b + 190, y_lsx + 190)
    cell.r('m3', b - 190, y_lsx - 190, ls_x + 190, y_lsx + 190)
    cell.r('m3', ls_x - 190, y_lsx - 190, ls_x + 190, y_ls + 190)
    cell.r('v2', b - 140, y_lsx - 140, b + 140, y_lsx + 140)
    cell.label('lsq', 'm3', (b + ls_x) // 2 // 5 * 5, y_lsx)
    # ---- the header band above lsdiv's top VSS rail: Hq (P row), Cq (N row), real VDD rail on top ----
    D = {d['name']: d for d in R.flat_devs(R.sim_cells(), 'rx_lsq')}
    hq, cq = D['Hq'], D['Cq']
    assert hq['nets'] == ['vq', 'qenb', 'VDD', 'VDD'] and hq['m'] == 2
    # Hq: 6 fingers of W / 3 (= m 2 x W), not 2 of W, over Cq: the header band's P row is a third as tall
    # (2026-11-16)
    cols = [('HQ', [R.mos(hq['w'] / 3, hq['l'], ['VDD'] + ['qenb', 'vq', 'qenb', 'VDD'] * 3, 'VDD')],
             [R.from_dev(cq, nf=3)])]                 # Hq over Cq, one column
    band = R.Band('lsq_hdr', cols, ports=['vq', 'qenb'], pins=['qenb'], x0=2900, search=True)
    band.place()
    assert band.xend <= xr - 500, (band.xend, xr)
    xq = T['qenb'][2][0]                         # qenb riser at Dq's gate (its track is one point)
    xv = xq + 2600                                # vq riser
    assert abs(xv - ls_x) > R.M3P and xv < m['c1']['x1']
    meta_b = band.finish(cell, xr, y0=Y['vss2_t'], exits=dict(qenb=('through', xq), vq=('bottom', xv)),
                         m3_used=[ls_x], xmin=2500)
    for net, ys, skip in meta_b['rails']:        # lsdiv's own M3 VSS strap (x 0.3-1.3 um) has its via2s there
        if net == 'VSS':
            skip.append((0, 1700))
    R.draw_rails(cell, [meta_b], xr, m3_only=[(Y['vss2_b'], Y['vss2_t'])])    # lsdiv drew that rail's M1 / M2
    ytop = meta_b['y'][1]
    # qenb: lsdiv's qenb track (via2) up to the band's bottom edge (the band's own M3 continues to its top edge)
    cell.r('v2', xq - 140, T['qenb'][1] - 140, xq + 140, T['qenb'][1] + 140)
    cell.r('m2', xq - 190, T['qenb'][1] - 190, xq + 190, T['qenb'][1] + 190)
    cell.r('m3', xq - 190, T['qenb'][1] - 190, xq + 190, Y['vss2_b'])
    # vq: lsdiv's (former VDD) rail, via2 on its M2, M3 up to the band's bottom edge
    yv = (Y['vdd_b'] + Y['vdd_t']) // 2
    cell.r('m3', xv - 190, yv - 190, xv + 190, Y['vss2_b'])
    cell.r('v2', xv - 140, yv - 140, xv + 140, yv + 140)
    if pins == 'rx_top':
        # lsq pin: lsdiv's ls M3 vertical on up to the new top edge (a window in the band's VSS / VDD rail M3)
        cell.r('m3', ls_x - 190, bb[3] - 400, ls_x + 190, ytop)
        cell.label('lsq', 'm3', ls_x, ytop - 200, port=True)
        pins_own = None
    else:
        # lsq pin on the left edge, as low as the cell allows: the ls M3 vertical (it already reaches the lsx jumper
        # at y_lsx) on down to just over the bottom VSS rail (Y vss_t = 0; M2 there is free: the N row has M1
        # only), via2, M2 to x 0 (under lsdiv's M3 VSS strap at x 0.3-1.3)
        assert Y['vss_t'] == 0 and y_lsx - 190 > 1200
        yp = 700
        cell.r('m3', ls_x - 190, yp - 190, ls_x + 190, y_lsx + 190)
        cell.r('v2', ls_x - 140, yp - 140, ls_x + 140, yp + 140)
        cell.r('m2', 0, yp - 190, ls_x + 190, yp + 190)
        cell.label('lsq', 'm2', 150, yp, port=True)
        pins_own = [('lsq', 0, yp, 'left')]
    pins_own = (pins_own or []) + [('aq', xr, R.LL.A0_Y, 'right'), ('qenb', xq, ytop, 'top')]
    meta = dict(bbox=(0, bb[1], xr, ytop), lsdiv=m, band=meta_b, pad=PAD, ls_x=ls_x, xq=xq, xv=xv, pins_own=pins_own)
    return [cell], meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(R.REPO / 'build' / 'rx_layout' / 'gen' / 'rx_lsq'))
    ap.add_argument('--gds', default=str(R.REPO / 'layout' / 'rx_lsq.gds'))
    a = ap.parse_args()
    cells, meta = build()
    R.save_meta(a.out, meta)
    log = R.write(cells, 'rx_lsq', a.gds, a.out)
    print('rx_lsq', R.bbox_str(meta['bbox']), 'magic log', log)


if __name__ == '__main__':
    main()
