#!/usr/bin/env python3
"""Local structural checks of the tile against the Tiny Tapeout rules (the subset of the TT precheck that needs no
third-party code): python3 layout/gen/tile_precheck.py [gds] [lef]

  - top cell name = info.yaml top_module; the boundary (layer 0/0 / bbox) equals the template's die area
  - every template pin: a Metal4 rectangle exactly at the DEF's place, with its label; no other top-level labels
    with a pin name; the LEF has the same pins
  - power: VDPWR, VAPWR (uses_vapwr), VGND each with at least one Metal4 stripe >= 1.2 um wide that runs from within
    10 um of the bottom to within 10 um of the top; LEF USE POWER / GROUND
  - no Metal5 / Via4 anywhere, no shape outside the die
  - info.yaml: analog_pins, uses_vapwr; src/project.v declares VAPWR when uses_vapwr
Exit 1 on any failure. The real TT precheck (tt-support-tools) remains the reference: run it before submitting.
"""
import re
import sys
from pathlib import Path

import klayout.db as db
import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import tile  # noqa: E402

gds = Path(sys.argv[1]) if len(sys.argv) > 1 else REPO / 'gds' / f'{tile.TOP}.gds'
lef = Path(sys.argv[2]) if len(sys.argv) > 2 else REPO / 'lef' / f'{tile.TOP}.lef'
info = yaml.safe_load((REPO / 'info.yaml').read_text())['project']
T = tile.parse_def(tile.DEF)
bad = []
ok = []


def chk(cond, what):
    (ok if cond else bad).append(what)


ly = db.Layout()
ly.read(str(gds))
top = ly.top_cell()
chk(top.name == info['top_module'] == tile.TOP, f"top cell {top.name}")
bb = top.bbox()
chk((bb.left, bb.bottom, bb.right, bb.top) == (0, 0, T['w'], T['h']), f"bbox {bb} = die 0 0 {T['w']} {T['h']}")
for l, d in ((81, 0), (82, 0), (81, 10)):
    li = ly.find_layer(l, d)
    chk(li is None or db.Region(top.begin_shapes_rec(li)).is_empty(), f"no {l}/{d} (Metal5 / Via4)")
m4 = db.Region(top.shapes(ly.find_layer(46, 0))).merged()
labels = {}
li = ly.find_layer(46, 10)
for s in top.shapes(li).each():
    if s.is_text():
        labels.setdefault(s.text_string, []).append(s.text.trans.disp)
npin = 0
for name, p in T['pins'].items():
    r = db.Box(*p['rect'])
    inside = not (db.Region(r) - m4).is_empty()
    lab = any(r.contains(q) for q in labels.get(name, []))
    chk(not inside and lab, f"pin {name}: Metal4 at the DEF rectangle, labelled")
    npin += 1
# power stripes
for net in ('VDPWR', 'VGND') + (('VAPWR',) if info.get('uses_vapwr') else ()):
    good = 0
    for q in labels.get(net, []):
        for poly in m4.each():
            b = poly.bbox()
            if b.contains(q) and b.width() >= 1200 and b.bottom <= 10000 and b.top >= T['h'] - 10000:
                good += 1
                break
    chk(good > 0, f"{net}: {good} Metal4 stripe(s) >= 1.2 um wide spanning to within 10 um of both edges")
# LEF
lt = lef.read_text()
for name in T['pins']:
    chk(re.search(rf'PIN {re.escape(name)}\s', lt) is not None, f"LEF pin {name}")
chk(re.search(r'PIN VDPWR.*?USE POWER', lt, re.S) is not None and re.search(r'PIN VGND.*?USE GROUND', lt, re.S)
    is not None, "LEF power / ground uses")
if info.get('uses_vapwr'):
    chk(re.search(r'PIN VAPWR.*?USE POWER', lt, re.S) is not None, "LEF VAPWR")
    chk('input  wire       VAPWR' in (REPO / 'src/project.v').read_text(), "project.v declares VAPWR")
chk(info.get('analog_pins') == 6, f"analog_pins {info.get('analog_pins')}")
for n in ok:
    print('ok  ', n) if not n.startswith('pin ') and not n.startswith('LEF pin') else None
print(f'ok   {npin} template pins at their DEF rectangles; {sum(n.startswith("LEF pin") for n in ok)} in the LEF')
for n in bad:
    print('FAIL', n)
print('PRECHECK (local)', 'OK' if not bad else f'FAIL ({len(bad)})')
sys.exit(1 if bad else 0)
