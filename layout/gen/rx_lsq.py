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

The I/Q-symmetric split (branch iq-symmetry, 2026-11-19): the level shifter goes into vco_core against the ring, as
a mirror image of lsdiv (layout/gen/vco_core.py), and the header band stays in the tile. build(part=...):
  part='ls'  -> rx_lsq_ls: the lsdiv copy only (no header band); its supply rail is the port vq; pins on the left
                edge: lsq (M2, y 0.7, as 'tile'), vq (M2, the rail's left end); aq on the right edge as before.
                Dq's gate (qenb) is tied to VSS here: an M3 riser from its gate track up to y 20, M2 west onto
                the left M3 VSS strap (a 0.42 / 0.28 um gate on a routed tie to a stripe broke KLayout's ANT.16 /
                ANT.4 in the tile). To gate the Q copy later (qenb to enb), cut that via2 and bring qenb out.
                lsdiv's ls M3 vertical stops at its upper via (y 14.2): the stub on up to lsdiv's ls port would
                be dead wire on lsq.
  part='hdr' -> rx_lsq_hdr: the header band alone (Hq over Cq) on its own VSS rail (the copy of lsdiv's top rail),
                VDD rail on top; pins vq and qenb on M3 at the bottom edge.
  split_source(): rx_lsq's netlist (xschem or the sim netlister) -> the two subckts rx_lsq_ls (vq VSS aq lsq, qenb
                tied to VSS inside) and rx_lsq_hdr (VDD VSS qenb vq), for the LVS sources and the size diff.
"""
import argparse
import re
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


def split_source(text):
    """The rx_lsq subckt of a netlist -> rx_lsq_ls (vq VSS aq lsq: everything but the header and its decap, Dq's gate
    qenb tied to VSS as drawn) and rx_lsq_hdr (VDD VSS qenb vq: Hq and Cq), with the header's output net named vq in
    both. Other subckts unchanged."""
    text = re.sub(r'\n\+', ' ', text)
    m = re.search(r'^\.subckt rx_lsq (.*?)\n(.*?)^\.ends[^\n]*\n?', text, flags=re.M | re.S | re.I)
    assert m, 'no rx_lsq subckt'
    assert m.group(1).split() == ['VDD', 'VSS', 'aq', 'qenb', 'lsq'], m.group(1)
    body = [ln for ln in m.group(2).splitlines() if ln.strip() and not ln.startswith('*')]
    hq = [ln for ln in body if re.match(r'X?Hq\b', ln, flags=re.I)]
    cq = [ln for ln in body if re.match(r'X?Cq\b', ln, flags=re.I)]
    assert len(hq) == 1 and len(cq) == 1, (hq, cq)
    vq = hq[0].split()[1]

    def ren(ln, tie=False):
        return ' '.join('vq' if t == vq else ('VSS' if tie and t == 'qenb' else t) for t in ln.split())
    ls = [ren(ln, tie=True) for ln in body if ln not in hq + cq]
    assert all(t != 'VDD' for ln in ls for t in ln.split()), 'rx_lsq_ls: a device on VDD'
    new = ('.subckt rx_lsq_ls vq VSS aq lsq\n' + '\n'.join(ls) + '\n.ends\n'
           '.subckt rx_lsq_hdr VDD VSS qenb vq\n' + ren(hq[0]) + '\n' + ren(cq[0]) + '\n.ends\n')
    return text[:m.start()] + new + text[m.end():]


def build(pins='tile', part='all'):
    assert pins in ('tile', 'rx_top'), pins
    assert part in ('all', 'ls', 'hdr'), part
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
    if part == 'ls':
        return build_ls(cell, m, T, Y, xr, ls_x, y_lsx)
    # ---- the header band above lsdiv's top VSS rail: Hq (P row), Cq (N row), real VDD rail on top ----
    D = {d['name']: d for d in R.flat_devs(R.sim_cells(), 'rx_lsq')}
    hq, cq = D['Hq'], D['Cq']
    assert hq['nets'] == ['vq', 'qenb', 'VDD', 'VDD'] and hq['m'] == 2
    # Hq: 6 fingers of W / 3 (= m 2 x W), not 2 of W, over Cq: the header band's P row is a third as tall
    # (2026-11-16)
    cols = [('HQ', [R.mos(hq['w'] / 3, hq['l'], ['VDD'] + ['qenb', 'vq', 'qenb', 'VDD'] * 3, 'VDD')],
             [R.from_dev(cq, nf=3)])]                 # Hq over Cq, one column
    band = R.Band('lsq_hdr', cols, ports=['vq', 'qenb'], pins=['qenb'] + (['vq'] if part == 'hdr' else []),
                  x0=2900, search=True)
    band.place()
    assert band.xend <= xr - 500, (band.xend, xr)
    xq = T['qenb'][2][0]                         # qenb riser at Dq's gate (its track is one point)
    xv = xq + 2600                                # vq riser
    assert abs(xv - ls_x) > R.M3P and xv < m['c1']['x1']
    if part == 'hdr':
        return build_hdr(band, Y, xr, xq, xv)
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


def build_ls(cell, m, T, Y, xr, ls_x, y_lsx):
    """rx_lsq_ls: the lsdiv copy without the header band (part='ls'); see the module docstring."""
    cell.name = 'rx_lsq_ls'
    n0 = len(cell.rects)
    cell.rects = [r for r in cell.rects if r != ('m3', ls_x - 190, 13995, ls_x + 190, m['bbox'][3])]
    assert len(cell.rects) == n0 - 1, 'lsdiv ls M3 vertical not found'
    # lsq: as pins='tile' (ls M3 vertical down to y 0.7, via2, M2 to the left edge)
    yp = 700
    cell.r('m3', ls_x - 190, yp - 190, ls_x + 190, y_lsx + 190)
    cell.r('v2', ls_x - 140, yp - 140, ls_x + 140, yp + 140)
    cell.r('m2', 0, yp - 190, ls_x + 190, yp + 190)
    cell.label('lsq', 'm2', 150, yp, port=True)
    # vq: lsdiv's VDD rail (M1 + M2 from x 0.3) on to the left edge
    yv = (Y['vdd_b'] + Y['vdd_t']) // 2
    cell.r('m2', 0, Y['vdd_b'], 400, Y['vdd_t'])
    cell.label('vq', 'm2', 150, yv, port=True)
    # qenb tied to VSS: via2 on Dq's gate track, M3 up past the vq rail, via2, M2 west onto the left M3 VSS strap
    # (x 0.3 ... 1.3, via2 at x 0.8)
    xq, yq0 = T['qenb'][2][0], T['qenb'][1]
    yq = 20000
    cell.r('v2', xq - 140, yq0 - 140, xq + 140, yq0 + 140)
    cell.r('m2', xq - 190, yq0 - 190, xq + 190, yq0 + 190)
    cell.r('m3', xq - 190, yq0 - 190, xq + 190, yq + 190)
    cell.r('v2', xq - 140, yq - 140, xq + 140, yq + 140)
    cell.r('m2', 300, yq - 190, xq + 190, yq + 190)
    cell.r('v2', 800 - 140, yq - 140, 800 + 140, yq + 140)
    labels = [(t, l, x, y, p) for (t, l, x, y, p) in cell.labels if not (t == 'vq' and p and x != 150) and t != 'qenb']
    cell.labels = [(t, l, x, y, p and t in ('VSS', 'aq', 'lsq', 'vq')) for (t, l, x, y, p) in labels]
    bb = (0, m['bbox'][1], xr, Y['vss2_t'])          # (the top is lsdiv's top VSS rail: the ls port stub is gone)
    pins_own = [('lsq', 0, yp, 'left'), ('vq', 0, yv, 'left'), ('aq', xr, R.LL.A0_Y, 'right')]
    return [cell], dict(bbox=bb, lsdiv=m, ls_x=ls_x, xq=xq, yq=yq, pins_own=pins_own, part='ls')


def build_hdr(band, Y, xr, xq, xv):
    """rx_lsq_hdr: the header band (Hq over Cq) on its own VSS rail (part='hdr'); see the module docstring."""
    cell = Cell('rx_lsq_hdr')
    meta_b = band.finish(cell, xr, y0=Y['vss2_b'], exits=dict(qenb=('throughb', xq), vq=('bottom', xv)), xmin=2500)
    R.draw_rails(cell, [meta_b], xr)
    bb = (0, meta_b['y'][0], xr, meta_b['y'][1])
    pins_own = [('vq', xv, bb[1], 'bottom'), ('qenb', xq, bb[1], 'bottom')]
    return [cell], dict(bbox=bb, band=meta_b, xq=xq, xv=xv, pins_own=pins_own, part='hdr')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--part', default='all', choices=['all', 'ls', 'hdr'])
    ap.add_argument('--out', default=None)
    ap.add_argument('--gds', default=None)
    a = ap.parse_args()
    name = dict(all='rx_lsq', ls='rx_lsq_ls', hdr='rx_lsq_hdr')[a.part]
    out = a.out or str(R.REPO / 'build' / 'rx_layout' / 'gen' / name)
    gds = a.gds or str(R.REPO / 'layout' / f'{name}.gds')
    cells, meta = build(part=a.part)
    R.save_meta(out, meta)
    log = R.write(cells, name, gds, out)
    print(name, R.bbox_str(meta['bbox']), 'magic log', log)


if __name__ == '__main__':
    main()
