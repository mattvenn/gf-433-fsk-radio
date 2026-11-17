#!/usr/bin/env python3
"""Dummy COMP fill (GDS 22/4, magic's 'filldiff', not a device) for the receiver cells: DCF.1a.

    python3 layout/gen/rx_fill.py <gds> <cell> [--margin 4.0]

GF180MCU's DCF.1a asks that no 20 x 20 um area be free of COMP (active), except near resistors, well edges and the
other keep-outs. The banded receiver cells leave such areas where a row is longer than its neighbour, and rx_top
leaves them between blocks, so this step drops 2 x 2 um dummy COMP squares on a 4 um grid (DCF.2b: 1.9 um apart)
wherever they keep:
  3.5 um from circuit COMP (DCF.4), 1.5 um from poly (DCF.5), 1.3 um from n-well edges (DCF.6a),
  3.5 um from RES_MK (DCF.8a), and `margin` um inside the cell's bounding box (so a neighbour's COMP across the
  cell edge keeps DCF.4).
The fill goes into the top cell; the GDS is rewritten in place. magic reads 22/4 as filldiff (no device, no
extraction), so LVS and the extraction don't see it.
"""
import argparse

import klayout.db as db

PITCH, SQ = 4.0, 2.0


def fill(gds, cell, margin=4.0, out=None):
    ly = db.Layout()
    ly.read(gds)
    top = ly.cell(cell)
    um = lambda v: int(round(v / ly.dbu))

    def reg(l, d):
        li = ly.find_layer(l, d)
        return db.Region(top.begin_shapes_rec(li)).merged() if li is not None else db.Region()
    comp, poly, nwell, resmk = reg(22, 0), reg(30, 0), reg(21, 0), reg(110, 5)
    old = reg(22, 4)                                          # fill already there (a filled sub-cell): DCF.2b
    keep = comp.sized(um(3.5)) + poly.sized(um(1.5)) + (nwell.sized(um(1.3)) - nwell.sized(um(-1.3))) \
        + resmk.sized(um(3.5)) + old.sized(um(1.9))
    bb = top.bbox()
    area = db.Region(bb).sized(um(-margin))
    free = (area - keep).merged().sized(um(-SQ / 2))          # centres where a whole square fits
    pts = db.Region()
    x0, y0 = bb.left + um(margin + SQ / 2), bb.bottom + um(margin + SQ / 2)
    p = um(PITCH)
    x = x0
    while x < bb.right:
        y = y0
        while y < bb.top:
            pts.insert(db.Box(x - 1, y - 1, x + 1, y + 1))
            y += p
        x += p
    keep_pts = pts.inside(free)
    li = ly.layer(22, 4)
    n = 0
    for b in keep_pts.each():
        c = b.bbox().center()
        top.shapes(li).insert(db.Box(c.x - um(SQ / 2), c.y - um(SQ / 2), c.x + um(SQ / 2), c.y + um(SQ / 2)))
        n += 1
    ly.write(out or gds)
    return n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('gds')
    ap.add_argument('cell')
    ap.add_argument('--margin', type=float, default=4.0)
    a = ap.parse_args()
    n = fill(a.gds, a.cell, a.margin)
    print(f'{a.cell}: {n} dummy COMP squares (22/4)')


if __name__ == '__main__':
    main()
