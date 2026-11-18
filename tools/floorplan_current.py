"""Write layout/floorplan/current.json: today's tile (layout/gen/tt_wrapper.py) as floorplan placements, so the page's
"current" variant reproduces it.

    python3 tools/floorplan_current.py           (needs the klayout module)

Each block's placed bbox is computed here with KLayout from the block's GDS and the exact transformation
tt_wrapper.py inserts it with (db.Trans.M90 for vco_top, db.Trans.M0 for tx_drv, plain shifts for the rest), and the
page orientation that gives the same bbox is recorded with it. `node layout/floorplan/page/check.js --current`
compares the page engine's placed rectangles against these bboxes (they must agree to 0.01 um).

tt_wrapper.py places everything in the 711.20 um tile (tt_analog_2x2.def). The floorplan uses the VAPWR template
(tt_analog_2x2_pgvaa.def), 693.28 um wide with every pin 17.92 um further left, so "current" is today's tile moved onto
it: every block and stripe shifted by DX = -17.92 um, keeping its place against the pads and the digital pins, except
the macro, which would leave the tile (x -17.32): it stays at x 0.6 with its strap stripes. The stripes that feed the
VAPWR blocks (vco_top's VDD and VDD_LS, mdac, the code inverters) become VAPWR (Matt 2026-11-16); tx_drv's stays VDPWR.
`bbox` is the wrapper's own bbox (711.20 um tile) and `shift` the x shift applied, so check.js can compare the two.
"""
import importlib.util
import json
import os

DX = -17.92                                    # um: tt_analog_2x2.def -> tt_analog_2x2_pgvaa.def pin shift
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))


def main():
    import klayout.db as db
    spec = importlib.util.spec_from_file_location('tt_wrapper', os.path.join(ROOT, 'layout/gen/tt_wrapper.py'))
    T = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(T)
    inst = {   # page instance: (GDS, cell, KLayout Trans as tt_wrapper.py inserts it, page orientation)
        'xvco': ('layout/vco_top.gds', 'vco_top', db.Trans(db.Trans.M90, db.Vector(T.X0, T.Y0)), 'MY'),
        'xtxd': ('layout/tx_drv.gds', 'tx_drv', db.Trans(db.Trans.M0, db.Vector(T.TX_X, T.TX_Y)), 'MX'),
        'xmdac': ('layout/mdac.gds', 'mdac', db.Trans(db.Vector(*T.MDAC)), 'R0'),
        'xvpd': ('layout/vctrl_pd.gds', 'vctrl_pd', db.Trans(db.Vector(*T.VPD)), 'R0'),
        'xmac': (str(T.MAC_GDS.relative_to(T.REPO)), 'tx_fine', db.Trans(db.Vector(*T.MAC)), 'R0'),
    }
    out = {'source': 'layout/gen/tt_wrapper.py, moved onto tt_analog_2x2_pgvaa.def', 'place': {}, 'bbox': {}, 'shift': {}}
    for n, (g, c, tr, o) in inst.items():
        ly = db.Layout()
        ly.read(os.path.join(ROOT, g))
        b = ly.cell(c).bbox().transformed(tr).to_dtype(ly.dbu)
        out['bbox'][n] = [round(b.left, 3), round(b.bottom, 3), round(b.width(), 3), round(b.height(), 3)]
        out['shift'][n] = 0.0 if n == 'xmac' else DX
        out['place'][n] = {'x': round(b.left + out['shift'][n], 3), 'y': round(b.bottom, 3), 'orient': o}
    # the coarse-code inverter + antenna rows (tt_wrapper: from x 555.16 - 1.12 at INV_ROW_Y, two rows)
    x0 = (555160 - 1120) / 1000
    out['shift']['xbits'] = DX
    out['place']['xbits'] = {'x': round(x0 + DX, 3), 'y': T.INV_ROW_Y / 1000, 'orient': 'R0'}
    out['bbox']['xbits'] = [x0, T.INV_ROW_Y / 1000, 20.16, 2 * T.ROW_H / 1000]
    VAP = {420000, 540000, 649140}               # tt_wrapper's VDPWR stripes on vco_top / mdac / the inverter row / VDD_LS
    out['straps'] = [{'net': 'VAPWR' if (n == 'VDPWR' and x in VAP) else n,
                      'x': round(x / 1000 + (0 if x < 200000 else DX), 3), 'w': w / 1000} for n, x, w in T.STRIPES]
    p = os.path.join(ROOT, 'layout', 'floorplan', 'current.json')
    with open(p, 'w') as fh:
        json.dump(out, fh, indent=1)
    for n, b in out['bbox'].items():
        print(f'{n:6s} {out["place"][n]["orient"]:4s} wrapper bbox x {b[0]:.3f} ... {b[0] + b[2]:.3f}, y {b[1]:.3f} ... {b[1] + b[3]:.3f}; placed at x {out["place"][n]["x"]}')


if __name__ == '__main__':
    main()
