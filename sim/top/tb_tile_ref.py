#!/usr/bin/env python3
"""Block-level references for the tile's VCO runs (sim/top/tb_tile.py vco_*): the extracted vco_top
(layout/pex/vco_top_rcx.spice, RC with rcfix) + the extracted medium DAC (layout/pex/mdac_cm.spice, C only, merged)
+ the 200 kOhm vctrl pull-down, exactly the deck of sim/tune/phase_c.py pex_deck() with the extracted DAC
(Table VII of docs/tx_fine_tune.md), at the same corner / code / word as the tile runs, 0.6 us, measured over the
last 40 % (as the tile runs; ref_tt_k9_w512_ca16 ran 1.2 us). No receiver Q tap on a2, ck loaded by a 20 fF wire only.

    python3 sim/top/tb_tile_ref.py list
    python3 sim/top/tb_tile_ref.py run NAME [NAME ...]     # build/tile_sims/<NAME>/result.json
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / 'sim/tune'))
import tb_tile as T  # noqa: E402
import mdac_sim as MS  # noqa: E402
import phase_c as PC  # noqa: E402  (read-only: pex_deck)
from rawread import read_raw  # noqa: E402

MS.PEX = 'cm'          # the extracted medium DAC, as phase_c.py --pex


def cases():
    C = {}
    for corner in ('typical', 'ss', 'ff', 'sf', 'fs'):
        cd = T.CODE[corner]
        for w in ((0, 512, 1023) if corner in ('typical', 'ss', 'ff') else (512,)):
            C[f'ref_{T.CN[corner]}_k{cd}_w{w}'] = dict(corner=corner, code=cd, word=w)
    for cd in (0, 8, 10, 31):
        C[f'ref_tt_k{cd}_w512'] = dict(corner='typical', code=cd, word=512)
    # attribution: the tile's a2 net has 19.0 fF of extracted wiring C against 3.0-3.4 fF on a vco_top ring node; put
    # the difference (15.7 fF) on a0 (a port of vco_top; the ring is symmetric) and see whether f drops as on the tile
    for corner in ('typical', 'sf', 'fs', 'ss', 'ff'):
        cd = T.CODE[corner]
        C[f'ref_{T.CN[corner]}_k{cd}_w512_ca16'] = dict(corner=corner, code=cd, word=512, cadd=15.7e-15)
    return C


def deck(c, tstop=0.6e-6):          # as the tile's VCO runs (tb_tile.VCO_TSTOP)
    if c['corner'] not in PC.VBN0:                   # sf / fs: the typical reference value as the .ic hint
        PC.VBN0[c['corner']] = PC.VBN0['typical']
    d = PC.pex_deck(c['corner'], c['code'], c['word'], tstop=tstop)
    if c.get('cadd'):
        d = d.replace('Cwire ck 0 20f\n', f"Cwire ck 0 20f\nCadd a0 0 {c['cadd']:.4g}\n")
        assert 'Cadd' in d
    d = d.replace(f'tran 5p {tstop} {0.4 * tstop} 5p', f'tran 5p {tstop} {0.6 * tstop} 5p')
    return d.replace('save v(a0) v(vg)', 'save v(a0) v(vg) v(vbnf)').replace('write out.raw v(a0) v(vg)',
                                                                            'write out.raw v(a0) v(vg) v(vbnf)')


def run(name):
    c = cases()[name]
    d = T.OUT / name
    d.mkdir(parents=True, exist_ok=True)
    (d / '.spiceinit').write_text('set ng_nomodcheck\nset num_threads=1\noption noinit\n')
    (d / 'deck.cir').write_text(deck(c))
    (d / 'out.raw').unlink(missing_ok=True)
    t = time.time()
    subprocess.run(['bash', '-c', f'cd {d} && nice -n 5 ngspice -b deck.cir > deck.log 2>&1'], check=False)
    r = dict(name=name, case=c, flags=T.log_flags(d), runtime_s=time.time() - t)
    try:
        pl = read_raw(d / 'out.raw')[0]['vars']
        tt, a0 = pl['time'], pl['v(a0)']
        lo, hi = float(a0.min()), float(a0.max())
        r.update(f_a0=T.freq(tt, a0, (lo + hi) / 2), a0_min=lo, a0_max=hi, vg=T.mean(tt, pl['v(vg)']),
                 vbnf=T.mean(tt, pl['v(vbnf)']))
        h = (tt[0] + tt[-1]) / 2
        r['f_drift'] = T.freq(tt[tt >= h], a0[tt >= h], (lo + hi) / 2) / T.freq(tt[tt < h], a0[tt < h], (lo + hi) / 2) - 1
    except Exception as e:  # noqa: BLE001
        r['error'] = str(e)
    (d / 'result.json').write_text(json.dumps(r, indent=1, default=float))
    print(json.dumps(r))
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('what', choices=['list', 'run', 'deck'])
    ap.add_argument('names', nargs='*')
    a = ap.parse_args()
    if a.what == 'list':
        print('\n'.join(cases()))
    elif a.what == 'deck':
        print(deck(cases()[a.names[0]]))
    else:
        for n in a.names:
            run(n)


if __name__ == '__main__':
    main()
