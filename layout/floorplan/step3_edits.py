"""The step-3 placement edits (docs/tile_layout.md): applied to variant B's floorplan.json (git 6a9fe73) -> build/tile/fp_try.json; then node layout/floorplan/page/pinreport.js build/tile/fp_try.json writes floorplan.json / pins.md. Run from the repo root."""
import json, sys
f = json.load(open('layout/floorplan/floorplan.json'))
f['pins_moved'] = {}
E = {  # inst: dict(x=, y=, orient=(rot, mirror))
    'xmdac': dict(y=207.0),
    'vco.core': dict(y=133.5), 'rx.lim_q': dict(y=68.5, x=276.27), 'rx.lim_i': dict(y=3.0),
    'rx.lsq': dict(x=216.45, y=107.2),
    'rx.lobuf_i': dict(y=81.44, rot=90, mirror=True, orient='MXR90'),
    'xdbg_bbi': dict(x=260.8, y=140.0, rot=0, mirror=False, orient='R0'),
    'xdbg_bbq': dict(x=118.0, y=150.5, rot=90, mirror=False, orient='R90'),
    'xdbg_nb': dict(x=399.0, y=89.5, rot=90, mirror=False, orient='R90'),
    'xdbg_vctrl': dict(x=427.0, y=76.0, rot=90, mirror=False, orient='R90'),
    'xvpd': dict(y=106.0),
    'xbits': dict(x=393.0, y=150.0, rot=90, mirror=False, orient='R90'),
}
B = json.load(open('layout/floorplan/blocks.json'))
size = {'vco.decap': 'decap_ls', 'xdbg_bbi': 'dbg_tg', 'xdbg_bbq': 'dbg_tg', 'xdbg_nb': 'dbg_tg', 'xdbg_vctrl': 'dbg_tg',
        'rx.lim_i': 'rx_lim', 'rx.lim_q': 'rx_lim'}
for b in f['blocks']:
    e = E.get(b['inst'])
    if e:
        b.update(e)
    c = size.get(b['inst'])
    if c:
        w, h = B[c]['w'], B[c]['h']
        b['w'], b['h'] = (h, w) if b['rot'] in (90, 270) else (w, h)
    if b['inst'] == 'xbits':
        b['w'], b['h'] = (9.04, 19.04) if b['rot'] in (90, 270) else (19.04, 9.04)
    if b['inst'] == 'xmac':
        b.pop('note', None)
# decap rectangles: clipped clear of every block (2.5 um keep-out, the macro's 5 um halo too), keeping the largest piece
K = 2.6
blocks = [b for b in f['blocks'] if b['inst'] not in ('deca', 'decd')]
def rect(b):
    k = K + (5 if b['inst'] == 'xmac' else 0)
    return (b['x'] - k, b['y'] - k, b['x'] + b['w'] + k, b['y'] + b['h'] + k)
for d in [b for b in f['blocks'] if b['inst'] in ('deca', 'decd')]:
    r = [d['x'], d['y'], d['x'] + d['w'], d['y'] + d['h']]
    for b in blocks:
        q = rect(b)
        if q[0] < r[2] and r[0] < q[2] and q[1] < r[3] and r[1] < q[3]:
            cands = [[r[0], r[1], q[0], r[3]], [q[2], r[1], r[2], r[3]], [r[0], r[1], r[2], q[1]], [r[0], q[3], r[2], r[3]]]
            r = max(cands, key=lambda c: max(0, c[2] - c[0]) * max(0, c[3] - c[1]))
    d['x'], d['y'] = round(r[0], 2), round(r[1], 2)
    d['w'], d['h'] = round(max(0, r[2] - r[0]), 2), round(max(0, r[3] - r[1]), 2)
f['blocks'] = [b for b in f['blocks'] if b['inst'] not in ('deca', 'decd') or (b['w'] >= 8 and b['h'] >= 8)]
import os
if os.path.exists('build/tile/stripes.json'):        # the stripes tile.py draws (its planner adds the turned blocks')
    f['straps'] = json.load(open('build/tile/stripes.json'))
json.dump(f, open(sys.argv[1] if len(sys.argv) > 1 else 'build/tile/fp_try.json', 'w'), indent=1)
