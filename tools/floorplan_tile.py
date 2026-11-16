"""Write layout/floorplan/tile.json for the floorplan page: the tile outline and every signal pin, from a Tiny Tapeout
analog DEF template.

    python3 tools/floorplan_tile.py [<def>]

Default: tt-support-tools main, tech/gf180mcuD/def/analog/tt_analog_2x2_pgvaa.def (the VAPWR template; downloaded
into build/floorplan/ if it is not there). Every pin is a Metal4 rectangle: ua[0..7] 6 x 2 um on the bottom edge
(their top half inside the die), the digital pins 0.3 x 1 um on the top edge.
"""
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
NAME = 'tt_analog_2x2_pgvaa.def'
URL = 'https://raw.githubusercontent.com/TinyTapeout/tt-support-tools/main/tech/gf180mcuD/def/analog/' + NAME


def parse(path):
    t = open(path).read()
    dbu = int(re.search(r'UNITS DISTANCE MICRONS (\d+)', t).group(1))
    die = [int(v) for v in re.search(r'DIEAREA \( (\S+) (\S+) \) \( (\S+) (\S+) \)', t).groups()]
    u = lambda v: round(v / dbu, 3)
    pins = {}
    for m in re.finditer(r'- (\S+) \+ NET \S+ \+ DIRECTION (\w+) \+ USE (\w+)\s+\+ PORT\s+\+ LAYER (\w+) '
                         r'\( (\S+) (\S+) \) \( (\S+) (\S+) \)\s+\+ (?:PLACED|FIXED) \( (\S+) (\S+) \) (\w+)', t):
        name, d, use, layer, a, b, c, e, x, y, o = m.groups()
        a, b, c, e, x, y = (int(v) for v in (a, b, c, e, x, y))
        pins[name] = {'layer': layer, 'dir': d, 'x0': u(x + a), 'y0': max(0.0, u(y + b)), 'x1': u(x + c),
                      'y1': min(u(die[3]), u(y + e))}
    assert len(pins) == int(re.search(r'PINS (\d+) ;', t).group(1)), 'DEF pin parse'
    return {'w': u(die[2]), 'h': u(die[3]), 'pins': pins}


def main():
    p = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'build', 'floorplan', NAME)
    if not os.path.exists(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
        urllib.request.urlretrieve(URL, p)
    t = parse(p)
    t = {'source': 'tt-support-tools main: tech/gf180mcuD/def/analog/' + os.path.basename(p), 'w': t['w'], 'h': t['h'],
         'stripe_y': [5.0, 320.36], 'stripe_min_w': 0.8, 'pins': t['pins']}
    out = os.path.join(ROOT, 'layout', 'floorplan', 'tile.json')
    with open(out, 'w') as fh:
        json.dump(t, fh, indent=1, sort_keys=True)
    ua = {k: round((v['x0'] + v['x1']) / 2, 2) for k, v in t['pins'].items() if k.startswith('ua')}
    print(out, t['w'], 'x', t['h'], len(t['pins']), 'pins;', ua)


if __name__ == '__main__':
    main()
