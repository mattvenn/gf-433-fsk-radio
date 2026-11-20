#!/usr/bin/env python3
"""Supply-landing check of the tile (layout/gen/tile_driver.sh step 3): python3 layout/gen/supply_check.py [meta.json]

LVS checks connectivity, not resistance: a block supply wired by the signal router passes LVS with any resistance.
That happened (2026-11-17): the turned TX driver's VSS reached VGND only through a router wire, 17.6 ohm, 259 mV of
ground lift and one via at 80x its EM limit (sim/power/results.md), with DRC / LVS / antenna / precheck all clean.
So:
  1. every block supply lands on a Metal4 stripe (build/tile/meta.json 'supply_unlanded' is empty), except an
     allow-list of tiny blocks the router may wire (ROUTED_OK);
  2. each landed supply has enough Via3 cuts for its block's current ('landing_cuts' from tile.py power()):
     cuts >= MARGIN x I / I_CUT, with I the worst average current from sim/power/currents.py (all modes on) and
     I_CUT the per-cut DC limit at 85 C (0.58 mA, layout/gen/tx_drv.py / sim/power/results.md).
Exit 1 on any failure.
"""
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'sim' / 'power'))
sys.path.insert(0, str(REPO / 'layout' / 'gen'))
import currents  # noqa: E402
import tile_nets as TN  # noqa: E402

I_CUT = 0.58      # mA per Via3 cut, 85 C DC limit
MARGIN = 2.0
# blocks whose supplies may be wired by the router: under 0.3 mA each (antenna diodes, the code inverters, the
# debug switches, decap, the vctrl pull-down, the Q-tap header's qenb tie (gates, no current) and the Q LO buffer's
# VDD, which reaches its
# stripe through rx_lobuf_i's rail; check sim/power/results.md before adding to this list)
ROUTED_OK = {'vco.decap', 'xdbg_vctrl', 'xdbg_bbi', 'xdbg_bbq', 'xdbg_nb', 'xvpd', 'xbits', 'rx.lsqh.qenb',
             'rx.lobuf_q', 'xant_tx', 'xant_rx', 'xant_dbg', 'xties'}

meta = json.load(open(sys.argv[1] if len(sys.argv) > 1 else REPO / 'build/tile/meta.json'))
cur = currents.mode('all')
bad, ok = [], []
for inst, nets in meta['supply_unlanded'].items():
    for cnet in nets:
        tag = f'{inst}.{cnet}'
        (ok if inst in ROUTED_OK or tag in ROUTED_OK else bad).append(f'{tag} wired by the router'
                                                                     + ('' if inst in ROUTED_OK or tag in ROUTED_OK
                                                                        else ' (not in the allow-list)'))
cuts = meta.get('landing_cuts', {})
if not cuts:
    bad.append("meta.json has no 'landing_cuts' (rebuild with layout/gen/tile.py)")
for inst, sup in TN.SUPPLY.items():
    for cnet, net in sup.items():
        i = cur.get(net, {}).get(inst, 0.0)
        if i <= 0 or inst in ROUTED_OK or inst == 'xmac' or cnet in TN.TIED_VSS:
            continue     # the macro lands on its own straps (tile.py stripes); tie pins (qenb) carry no current
        if False:
            continue
        need = MARGIN * i / I_CUT
        have = cuts.get(f'{inst}.{cnet}', 0)
        (ok if have >= need else bad).append(f'{inst}.{cnet} ({net}, {i:.2f} mA): {have} Via3 cuts, need >= {need:.0f}')
for line in ok:
    print('ok  ', line)
for line in bad:
    print('FAIL', line)
print('SUPPLY CHECK', 'OK' if not bad else f'FAIL ({len(bad)})')
sys.exit(1 if bad else 0)
