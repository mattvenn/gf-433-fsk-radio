#!/usr/bin/env python3
"""
dbg_tg: the debug switch. Four in the tile (baseband I / Q, the receiver bias nb, vctrl), each next to its source,
all onto one bus to the analog pad ua[0]; selected by the SPI bits dbg_sel[3:0] (3.3 V logic from tx_fine).

  MTn / MTp: a transmission gate between mod (the source node) and bus (to ua[0]): ctrl = 1 -> on
             (MTn gate = ctrl, MTp gate = ctrl_b).
  Ic       : the inverter that makes ctrl_b from ctrl.
The sources are DC or slow (<= 143 kHz) into a few pF of pad, so a few kOhm on is plenty; small devices keep the
off capacitance on the sensitive source nodes small. The sizes live only here (S): xschem/gen/dbg_tg.py and
layout/gen/dbg_tg.py read them.

    python3 sim/rx/dbg_tg.py          # print the netlist
    python3 sim/rx/dbg_tg.py --sim    # tt 27 C: R_on mod <-> bus at mod 0.3 / 1.65 / 3.0 V, off leakage and C
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rxc  # noqa: E402

S = dict(wn=2.0, wp=4.0, l=0.28,          # the switch (um)
         win=0.42, wip=1.0)                # the inverter ctrl -> ctrl_b


def block(s=None):
    s = dict(S, **(s or {}))
    return ('.subckt dbg_tg VDD VSS ctrl mod bus\n'
            + rxc.inv('Ic', 'ctrl', 'ctrl_b', s['win'], s['wip'])
            + rxc.nfet('MTn', 'mod', 'ctrl', 'bus', s['wn'], s['l'])
            + rxc.pfet('MTp', 'mod', 'ctrl_b', 'bus', s['wp'], s['l'])
            + '.ends\n')


def sim():
    """R_on from a 1 uA-ish DC test: bus held by a source at v, mod driven 1 mV above it; I through the switch.
    Off: ctrl = 0, mod at v, bus at 0 / 3.3 V: leakage; off C on mod = d(Q)/dV from an AC at mod (bus at AC
    ground), and the C seen at bus."""
    deck = rxc.hdr('typical') + block() + '''
.option temp=27
VDD VDD 0 3.3
VC ctrl 0 {vc}
X1 VDD 0 ctrl mod bus dbg_tg
Vm mod 0 DC {vm} AC {am}
Vb bus 0 DC {vb} AC {ab}
.control
set wr_singlescale
'''
    rows = []
    out = []
    for v in (0.3, 1.65, 3.0):
        out.append(f'alter VC dc=3.3\nalter Vm dc={v + 1e-3}\nalter Vb dc={v}\nop\n'
                   f'echo RON {v} $&i(Vb)\n')
    for v in (0.3, 1.65, 3.0):
        out.append(f'alter VC dc=0\nalter Vm dc={v}\nalter Vb dc=0\nop\necho LEAK0 {v} $&i(Vb)\n'
                   f'alter Vb dc=3.3\nop\necho LEAK3 {v} $&i(Vb)\n')
        # off C on mod (AC at mod, bus held), and on bus (AC at bus, mod held)
        out.append(f'alter Vb dc=1.65\nalter Vm ac=1\nalter Vb ac=0\nac lin 1 1e5 1e5\n'
                   f'let cx = imag(i(Vm))\necho CMOD {v} $&cx\n'
                   f'alter Vm ac=0\nalter Vb ac=1\nac lin 1 1e5 1e5\nlet cx = imag(i(Vb))\necho CBUS {v} $&cx\n'
                   f'alter Vb ac=0\n')
    deck = deck.format(vc=3.3, vm=0, vb=0, am=0, ab=0) + ''.join(out) + '.endc\n.end\n'
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / '.spiceinit').write_text('set ng_nomodcheck\noption noinit\n')
        (Path(d) / 'deck.cir').write_text(deck)
        log = subprocess.run(['ngspice', '-b', 'deck.cir'], cwd=d, capture_output=True, text=True).stdout
        if '-v' in sys.argv:
            print(log)
    bad = [w for w in rxc.BAD if w in log.lower()]
    get = lambda k: [(float(a), float(b)) for a, b in re.findall(rf'^{k} (\S+) (\S+)', log, re.M)]
    for v, i in get('RON'):
        rows.append(f'R_on at {v:.2f} V (ctrl = 1): {1e-3 / abs(i):.0f} ohm')
    for (v, i0), (_, i3) in zip(get('LEAK0'), get('LEAK3')):
        rows.append(f'off leakage at mod {v:.2f} V (ctrl = 0): bus 0 V {abs(i0) * 1e12:.2f} pA, bus 3.3 V '
                    f'{abs(i3) * 1e12:.2f} pA')
    w = 2 * 3.141592653589793 * 1e5
    for (v, im), (_, ib) in zip(get('CMOD'), get('CBUS')):
        rows.append(f'off C at mod {v:.2f} V, bus 1.65 V (ctrl = 0): on mod {abs(im) / w * 1e15:.2f} fF, '
                    f'on bus {abs(ib) / w * 1e15:.2f} fF')
    rows.append('log: ' + ('clean' if not bad else 'BAD ' + ' '.join(bad)))
    return rows


if __name__ == '__main__':
    if '--sim' in sys.argv:
        print('\n'.join(sim()))
    else:
        print(block(), end='')
