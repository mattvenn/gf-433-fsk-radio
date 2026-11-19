"""I/Q phase vs extra C on a2 (the Q tap), both taps an extracted lsdiv copy straight on the ring (rx_lo.py bench)."""
import json, sys, time
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'sim' / 'rx'))
import rx_lo as X, rxc
JOBS = [(c, code, ca) for c, code in (('typical', 9), ('ss', 11), ('ff', 7)) for ca in (0.0, 8e-15, 16.6e-15)]
def one(j):
    c, code, ca = j
    deck = X.ring_deck(c, code, 'a2', 1.2e-6)
    if ca:
        deck = deck.replace('.ic ', f'Cxa2 a2 0 {ca}\n.ic ', 1)
    name = f'{rxc.CN[c]}_c{code}_ca{ca*1e15:.1f}'
    d, log, bad = rxc.run(name, deck, sub='a2sym')
    try:
        r = X.analyse(d, 'a2')
    except Exception as e:
        r = dict(error=str(e), log=log.splitlines()[-5:])
    r.update(corner=rxc.CN[c], code=code, ca_fF=ca*1e15, bad=bad)
    print(json.dumps({k: (round(v, 5) if isinstance(v, float) else v) for k, v in r.items()}), flush=True)
    return r
t0 = time.time()
rows = rxc.pmap(one, JOBS, 9)
open(REPO / 'sim/top/a2_load/rows.json', 'w').write(json.dumps(rows, indent=1))
print('done', f'{time.time()-t0:.0f} s')
