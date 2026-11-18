"""
dbg_tg: the debug switch (sim/rx/dbg_tg.py block()). A transmission gate MTn / MTp between mod (the source node)
and bus (to the analog pad ua[0]); ctrl = 1 turns it on (MTn gate ctrl, MTp gate ctrl_b); the inverter Ic makes
ctrl_b. Four in the tile, one per debug source, selected by dbg_sel[3:0].

Source of truth: sim/rx/dbg_tg.py (S holds the sizes; block() the netlist). Every device is looked up there by
name, so W, L, m and the nets are the simulated ones.

    python3 xschem/gen/dbg_tg.py
"""
import importlib.util
import os

from common import REPO, Sch, gmos, ginv, place as _place, finish, title, bulk, port, supply, parse

_spec = importlib.util.spec_from_file_location('sim_dbg_tg', os.path.join(REPO, 'sim', 'rx', 'dbg_tg.py'))
DT = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(DT)

C = 'dbg_tg'
PINS = ['VDD', 'VSS', 'ctrl', 'mod', 'bus']
DEV = parse('\n'.join(ln for ln in DT.block().splitlines() if ln.startswith('X')))
for _d in DEV.values():
    _d['w'], _d['l'] = round(_d['w'], 4), round(_d['l'], 4)


def wl(d):
    return f"{d['w']:.3g}/{d['l']:.3g}"


def check(inst, **nets):
    assert inst.nets == nets, (inst.props.get('name'), inst.nets, nets)


def build():
    s = Sch()
    # the transmission gate: MTn (gate on the left), MTp turned 180 degrees (gate on the right); drains (mod) on
    # top, sources (bus) below
    mtn = _place(s, 'MTn', 0, 0, dev=DEV['MTn'])
    mtp = _place(s, 'MTp', 200, 0, rot=2, dev=DEV['MTp'])
    check(mtn, D='mod', G='ctrl', S='bus', B='VSS')
    check(mtp, D='mod', G='ctrl_b', S='bus', B='VDD')
    bulk(s, mtn, to='VSS')
    bulk(s, mtp, to='VDD')
    ym, yb = -80, 80
    s.route(mtn.pin('D'), (mtn.pin('D')[0], ym))
    s.route(mtp.pin('D'), (mtp.pin('D')[0], ym))
    s.bus((mtn.pin('D')[0], ym), (mtp.pin('D')[0], ym), [(100, ym)])
    s.route((100, ym), (100, -150), (-400, -150))
    port(s, (-400, -150), 'mod', 'io')
    s.route(mtn.pin('S'), (mtn.pin('S')[0], yb))
    s.route(mtp.pin('S'), (mtp.pin('S')[0], yb))
    s.bus((mtn.pin('S')[0], yb), (mtp.pin('S')[0], yb), [(100, yb)])
    s.route((100, yb), (100, 150), (500, 150))
    port(s, (500, 150), 'bus', 'io_r')
    # Ic: ctrl -> ctrl_b
    dp, dn = DEV['Icp'], DEV['Icn']
    assert dp['nets'] == ['ctrl_b', 'ctrl', 'VDD', 'VDD'] and dn['nets'] == ['ctrl_b', 'ctrl', 'VSS', 'VSS']
    p, n, g, d = ginv(s, -150, 350, dict(W=dp['w'], L=dp['l'], m=dp['m'], name='Icp'),
                      dict(W=dn['w'], L=dn['l'], m=dn['m'], name='Icn'))
    p.props['val'] = f'"{wl(dp)}"'
    n.props['val'] = f'"{wl(dn)}"'
    bulk(s, p, to='VDD'); supply(s, p.pin('S'), 'VDD')
    bulk(s, n, to='VSS'); supply(s, n.pin('S'), 'VSS')
    s.bus((-400, 350), g, [(-300, 350)])
    port(s, (-400, 350), 'ctrl', 'in')
    s.route((-300, 350), (-300, 0), mtn.pin('G'))
    s.route(d, (300, 350), (300, 0), mtp.pin('G'))
    s.text(240, 330, 'ctrl_b', 0.3)
    for i, net in enumerate(('VDD', 'VSS')):
        yy = 560 + 60 * i
        s.wire((-400, yy), (-340, yy))
        port(s, (-400, yy), net, 'io')
        supply(s, (-340, yy), net)
    S = DT.S
    title(s, -400, -420, ['dbg_tg: debug switch onto the ua[0] bus',
                          f"MTn {wl(DEV['MTn'])}, MTp {wl(DEV['MTp'])} um in parallel; ctrl = 1: on "
                          '(tt 27 C: R_on 0.84 / 1.17 / 1.25 kOhm at 0.3 / 1.65 / 3.0 V, off C on mod 6.4 fF)',
                          f"Ic {wl(DEV['Icp'])} / {wl(DEV['Icn'])} makes ctrl_b; source: sim/rx/dbg_tg.py "
                          f"(S: wn {S['wn']}, wp {S['wp']}, L {S['l']})"])
    finish(s, C, PINS, left=['ctrl', 'mod'], right=['bus'], top=['VDD'], bottom=['VSS'], width=140, label='dbg_tg')


if __name__ == '__main__':
    build()
