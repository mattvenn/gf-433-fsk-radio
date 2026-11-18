"""On-resistance of TT's GF180 power switches (tt-multiplexer pg/gf180mcuD, commit 885086c), ngspice.

tt_pg_3v3_hp_2 (VDPWR, 2x2 tile): one pfet_03v3 W 3357.5 um (nf 395) L 0.28 um.
tt_pg_5v0_2   (VAPWR, 2x2 tile): one pfet_05v0 W 3311 um (nf 301) L 0.5 um.
Gate at 0 V (on), source at the supply, 10 mA drawn from the drain; Ron = (Vs - Vd) / I.
Supply 3.3 V (and 5.0 V for the VAPWR switch), 27 C, corners typical / ff / ss.

    python3 sim/power/pg_rdson.py        -> build/power/pg_rdson.json
"""
import json
import os
import re
import subprocess

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
OUT = os.path.join(ROOT, 'build', 'power')
PDK = os.path.join(os.environ.get('PDK_ROOT', '/foss/pdks'), 'gf180mcuD', 'libs.tech', 'ngspice')
SW = {'3v3_hp_2': ('pfet_03v3', 3357.5 / 395, 0.28, 395), '5v0_2': ('pfet_05v0', 3311 / 301, 0.5, 301)}


def run(sw, corner, vdd, i=10e-3):
    m, w, l, nf = SW[sw]
    deck = f"""* {sw} Ron
.temp 27
.include {PDK}/design.ngspice
.lib {PDK}/sm141064.ngspice {corner}
vs s 0 {vdd}
Xp d 0 s s {m} w={w:.4f}u l={l}u m={nf}
I1 d 0 {i}
.control
op
print v(s)-v(d)
.endc
.end
"""
    r = subprocess.run(['ngspice', '-b'], input=deck, capture_output=True, text=True, cwd=OUT)
    v = float(re.search(r'v\(s\)-v\(d\) = ([-\d.eE+]+)', r.stdout).group(1))
    return v / i


def main():
    res = {}
    for sw, vdds in (('3v3_hp_2', (3.3,)), ('5v0_2', (3.3, 5.0))):
        for vdd in vdds:
            for c in ('typical', 'ff', 'ss'):
                res[f'{sw}_{vdd:g}V_{c}'] = run(sw, c, vdd)
                print(f'{sw:9s} {vdd:.1f} V {c:8s} Ron {res[f"{sw}_{vdd:g}V_{c}"]:.3f} ohm')
    json.dump(res, open(os.path.join(OUT, 'pg_rdson.json'), 'w'), indent=1)


if __name__ == '__main__':
    main()
