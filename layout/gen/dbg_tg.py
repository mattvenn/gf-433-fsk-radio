#!/usr/bin/env python3
"""Layout of the debug switch dbg_tg (a transmission gate mod <-> bus and its ctrl inverter), gf180mcuD, 3.3 V.

    python3 layout/gen/dbg_tg.py [--out build/tx_tile/layout_dbg_tg] [--gds layout/dbg_tg.gds]

Circuit and sizes: sim/rx/dbg_tg.py (S, block()) = xschem/dbg_tg.sch. One band (layout/gen/rx_lib.py), columns left
to right:
  TG  : MTp over MTn, both mod | gate | bus (mod on the left, next to its pin: its metal stays short)
  INV : Icp over Icn (ctrl -> ctrl_b)
Pins: VDD, VSS (rails, M1 + M2 + M3 continuous so the tile's Metal4 stripes can land on them; the port labels on
M3), mod (M2, left edge), bus (M2, right edge), ctrl (top edge: an M3 riser from its track that crosses the VDD rail
on M2 through a window in the rail's M2 only, the pin on that M2 at the top edge).
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rx_lib as R  # noqa: E402
from ring_core import Cell  # noqa: E402

_spec = importlib.util.spec_from_file_location('sim_dbg_tg', R.REPO / 'sim' / 'rx' / 'dbg_tg.py')
DT = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(DT)

PINS = ['VDD', 'VSS', 'ctrl', 'mod', 'bus']
EXITS = dict(mod=('left', None), bus=('right', None), ctrl=('top', None))


def cols():
    c = R.parse(DT.block())['dbg_tg']
    d = lambda n: R.dev(c, n)
    m = lambda n, seq: R.from_dev(d(n), seq=seq)
    return [
        ('TG', [m('MTp', ['mod', 'ctrl_b', 'bus'])], [m('MTn', ['mod', 'ctrl', 'bus'])]),
        ('INV', [m('Icp', ['ctrl_b', 'ctrl', 'VDD'])], [m('Icn', ['ctrl_b', 'ctrl', 'VSS'])]),
    ]


def rail_m2_cross(cell, meta):
    """The VDD rail: M3 continuous; the ctrl riser crosses it on M2 (a window in the rail's M2, M1 continuous)."""
    Y, y0 = meta['Y'], meta['y0']
    assert not meta['flip'] and y0 == 0
    yb, yt = Y['vdd_b'], Y['vdd_t']
    xc = [x for x, y, e in meta['pins']['ctrl'] if e == 'top'][0]
    xr = cell_bbox_xr = max(r[3] for r in cell.rects if r[0] == 'm1')
    keep = []
    for r in cell.rects:
        lay, x1, y1, x2, y2 = r
        on_rail = lay in ('m2', 'm3', 'v1', 'v2') and y1 >= yb and y2 <= yt
        riser = lay == 'm3' and x1 == xc - 190 and x2 == xc + 190 and y2 == yt
        if on_rail:
            continue
        if riser:
            lo = yb - 400
            keep.append(('m3', x1, y1, x2, lo))
            continue
        keep.append(r)
    cell.rects = keep
    lo = yb - 400
    cell.via2(xc, lo - 300)                                      # M3 riser -> M2
    cell.r('m2', xc - 190, lo - 490, xc + 190, yt)               # M2 across the rail to the top edge
    win = (xc - 190 - 400, xc + 190 + 400)
    cell.r('m3', 0, yb, xr, yt)
    for a, b in ((0, win[0]), (win[1], xr)):
        if b - a < 1000:
            continue
        cell.r('m2', a, yb, b, yt)
        x = a + 450
        while x + 450 <= b:
            cell.r('v1', x - 130, yb + 300, x + 130, yt - 300)
            cell.r('v2', x - 140, yb + 300, x + 140, yt - 300)
            x += 2000
    # the VSS rail: M1 + M2 + M3 from rx_lib (no window, nothing crosses it); make sure its M3 is continuous
    assert not any(e in ('bottom', 'through', 'throughb') for p in meta['pins'].values() for _, _, e in p)
    cell.r('m3', 0, Y['vss_b'], xr, Y['vss_t'])
    # labels: ctrl on its M2 at the top edge; VDD / VSS on the rails' M3
    lab = []
    for (t, layer, x, y, port) in cell.labels:
        if t == 'ctrl' and port:
            lab.append(('ctrl', 'm2', xc, yt - 200, True))
        elif t in ('VDD', 'VSS') and port:
            lab.append((t, 'm3', x, y, True))
        else:
            lab.append((t, layer, x, y, port))
    cell.labels = lab
    return xc


def build():
    cell = Cell('dbg_tg')
    band = R.Band('dbg', cols(), ports=['mod', 'bus', 'ctrl', 'ctrl_b'], pins=PINS[2:], search=True)
    metas, bb = R.stack(cell, [band], [EXITS])
    xc = rail_m2_cross(cell, metas[0])
    m = metas[0]
    Y = m['Y']
    ybot = bb[1]
    own = lambda x, y: [x - bb[0], y - ybot]
    pins = {
        'mod': own(0, m['tracks']['mod'][1]) + ['W', 'm2'],
        'bus': own(bb[2], m['tracks']['bus'][1]) + ['E', 'm2'],
        'ctrl': own(xc, bb[3]) + ['N', 'm2'],
        'VDD': own(0, (Y['vdd_b'] + Y['vdd_t']) // 2) + ['rail', 'm1+m2+m3'],
        'VSS': own(0, (Y['vss_b'] + Y['vss_t']) // 2) + ['rail', 'm1+m2+m3'],
    }
    return [cell], dict(bbox=bb, bands=metas, pins_own=pins,
                        rails_own=dict(VDD=[Y['vdd_b'] - ybot, Y['vdd_t'] - ybot],
                                       VSS=[Y['vss_b'] - ybot, Y['vss_t'] - ybot]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(R.REPO / 'build' / 'tx_tile' / 'layout_dbg_tg'))
    ap.add_argument('--gds', default=str(R.REPO / 'layout' / 'dbg_tg.gds'))
    a = ap.parse_args()
    cells, meta = build()
    R.save_meta(a.out, meta)
    log = R.write(cells, 'dbg_tg', a.gds, a.out)
    print('dbg_tg', R.bbox_str(meta['bbox']), 'magic log', log)
    print(json.dumps(meta['pins_own']))


if __name__ == '__main__':
    main()
