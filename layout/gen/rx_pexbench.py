#!/usr/bin/env python3
"""Re-simulation of the receiver with its extracted layout: the sim/rx benches with the extracted cells swapped in.

    python3 layout/gen/rx_pexbench.py <lo|lna|bb|lim|chain> [--corners typical,ss,ff] [--jobs 3] [--pex rcx]

The benches are imported read-only from sim/rx (rx_lo, rx_lna, rx_bb, rx_lim, rx_chain); each deck is built by the
existing code and the schematic .subckt of the block under test is replaced by the extracted one
(layout/pex/<cell>_<pex>.spice, made by layout/gen/pex_rx_block.sh: same name, the sim netlister's port order).
The layout labels every net with its sim name, so the benches' probes (v(xl.tail), v(xbb.vgr), ...) still work.
  lo    rx_lo.py ring, A1: the ring (extracted core) + the extracted lsdiv on a0 (I) + the TX splitter, the extracted
        rx_lsq on a2 (Q, header on: qenb = VSS as in rx_top), two extracted rx_lobuf and both extracted rx_mix
        (switch gates as their load, rf held at the LNA's DC). Against the same ring without the receiver ('base').
        One code per corner (the middle of rx_lo.CODES). Measures I/Q phase, duty, the ring's shift.
  lna   rx_lna.py bench: gain and NF, n_off 3, 40 Ohm, with the extracted rx_lna.
  bb    rx_bb.py bench: response and input noise with the extracted rx_bb (the limiter stage after it: schematic).
  lim   rx_lim.py hyst: the comparator's hysteresis inside the extracted rx_lim (gcp / gcn driven through ports
        added to a copy of the extracted subckt, as the original drives the comparator alone).
  chain rx_chain.py realfsk: FSK through the real ring LO at -70 dBm with the extracted rx_top (C only) and the
        extracted lsdiv on a0 (both level shifters extracted: no stand-in caps).
Results: build/rx_layout/bench/<mode>.json (rows) and a printed summary.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for p in ('sim/rx', 'sim/lsdiv', 'sim/tx'):
    sys.path.insert(0, str(REPO / p))
import rxc  # noqa: E402
import rx_lo  # noqa: E402
import rx_lna  # noqa: E402
import rx_bb  # noqa: E402
import rx_lim  # noqa: E402
import rx_bias  # noqa: E402
import rx_chain  # noqa: E402
import rx_mix  # noqa: E402
import lsdiv as LD  # noqa: E402
import tx_drv  # noqa: E402

PEX = REPO / 'layout' / 'pex'
OUT = REPO / 'build' / 'rx_layout' / 'bench'
SUB = 'rx_layout_pex'                     # rxc.run's build/rx/<SUB>/<name> run directories
MID = dict(typical=9, ss=11, ff=7)        # the middle code of rx_lo.CODES per corner


def pex(cell, kind):
    t = (PEX / f'{cell}_{kind}.spice').read_text()
    assert re.search(rf'(?m)^\.subckt {cell} ', t), cell
    return t


def swap(deck, cell, kind):
    """Replace the schematic .subckt <cell> ... .ends in deck by the extracted one."""
    new, n = re.subn(rf'(?ms)^\.subckt {cell} .*?^\.ends\n?', lambda m: pex(cell, kind), deck, count=1)
    assert n == 1, f'no .subckt {cell} in the deck'
    return new


# ---- lo: rx_lo ring (A1) ---------------------------------------------------------------------------------------
def lo_deck(corner, code, kind, tstop=1.2e-6, vdd=3.3, vctrl=1.65):
    p = dict(LD.vb.P, **LD.WINNER, **LD.CFED)
    body, ics = LD.ring(p, 'pex')
    bits = ''.join(f'vbit{b} bit{b} 0 {vdd if (code >> b) & 1 else 0}\nvbitb{b} bitb{b} 0 {0 if (code >> b) & 1 else vdd}\n'
                   for b in range(5))
    iblk = LD.ls_x(LD.S)                             # the extracted lsdiv: Xlsdiv vls 0 a0 ck lsout q1 lsdiv_x
    rx = (pex('rx_lsq', kind) + pex('rx_lobuf', kind) + pex('rx_mix', kind)
          + f'Ven en 0 {vdd}\nvrx vrx 0 {vdd}\nVrf rfp 0 2.15\nVrfn rfn 0 2.15\n'
          'Xlsq vrx 0 a2 0 lsq rx_lsq\n'                       # qenb = VSS: the Q tap copy on (rx_top)
          'Xbi vrx 0 lsout en lo_i lob_i rx_lobuf\nXbq vrx 0 lsq en lo_q lob_q rx_lobuf\n'
          'Xmi vrx 0 rfp rfn bip bin lo_i lob_i rx_mix\nXmq vrx 0 rfp rfn bqp bqn lo_q lob_q rx_mix\n'
          'Rbb1 bip 0 1e9\nRbb2 bin 0 1e9\nRbb3 bqp 0 1e9\nRbb4 bqn 0 1e9\n')
    save = 'v(a0) v(a2) v(a3) v(lsout) v(vg) v(lo_i) v(lob_i) v(lo_q) v(lob_q) v(lsq) i(vrx)'
    blk = iblk + f'{tx_drv.split(tx_drv.S)}Xtxs vls 0 lsout txa txb tx_split\n'
    t0 = 0.6 * tstop
    return f"""* rx_lo ring, extracted rx_lsq / rx_lobuf / rx_mix ({kind}) {corner} code {code}
{LD.hdr(corner)}.lib {rxc.PDK}/sm141064.ngspice diode_typical
vdd vdd 0 {vdd}
vls vls 0 {vdd}
vdv vdv 0 {vdd}
vff vff 0 {vdd}
vctrl vctrl 0 {vctrl}
{bits}{body}{blk}{rx}.ic {ics}
.control
option temp=27
save {save}
tran 5p {tstop} {t0} 5p
set filetype=binary
write out.raw {save}
quit
.endc
.end
"""


def run_lo(corners, jobs, kind, tstop):
    pts = [(c, MID[c], case) for c in corners for case in ('base', 'pex')]

    def one(pt):
        c, code, case = pt
        name = f'lo_{rxc.CN[c]}_c{code}_{case}'
        deck = rx_lo.ring_deck(c, code, 'base', tstop) if case == 'base' else lo_deck(c, code, kind, tstop)
        d, log, bad = rxc.run(name, deck, sub=SUB, timeout=6 * 3600)
        try:
            r = rx_lo.analyse(d, 'base' if case == 'base' else 'a2', qmodel='x')
        except Exception as e:  # noqa: BLE001
            r = dict(error=str(e), log=log.splitlines()[-5:])
        r.update(corner=rxc.CN[c], code=code, case=case, bad=bad)
        print(json.dumps({k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()}), flush=True)
        return r
    rows = rxc.pmap(one, pts, jobs)
    for c in corners:
        b = [r for r in rows if r['corner'] == rxc.CN[c] and r['case'] == 'base']
        x = [r for r in rows if r['corner'] == rxc.CN[c] and r['case'] == 'pex']
        if b and x and 'f' in b[0] and 'f' in x[0]:
            x[0]['shift_pct'] = (x[0]['f'] / b[0]['f'] - 1) * 100
    return rows


# ---- lna ---------------------------------------------------------------------------------------------------------
def run_lna(corners, jobs, kind):
    s = dict(rx_lna.S)

    def one(c):
        deck = swap(rx_lna.bench_deck(s, c, 3, 40, 150e-15), 'rx_lna', kind)
        d, log, bad = rxc.run(f'lna_{rxc.CN[c]}', deck, sub=SUB)
        r = rx_lna.analyse(log)
        r.update(corner=rxc.CN[c], n_off=3, rroute=40, bad=bad)
        print(json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}), flush=True)
        return r
    return rxc.pmap(one, corners, jobs)


# ---- bb ----------------------------------------------------------------------------------------------------------
def run_bb(corners, jobs, kind):
    def one(c):
        deck = swap(rx_bb.bench_deck(c), 'rx_bb', kind)
        d, log, bad = rxc.run(f'bb_{rxc.CN[c]}', deck, sub=SUB)
        r = rx_bb.analyse(d, log)
        r.update(corner=rxc.CN[c], bad=bad)
        print(json.dumps({k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()}), flush=True)
        return r
    return rxc.pmap(one, corners, jobs)


# ---- lim ---------------------------------------------------------------------------------------------------------
def lim_deck(corner, kind, amp=0.05, f=20e3):
    """rx_lim.hyst_deck's stimulus on the comparator inside the extracted rx_lim (gcp / gcn brought out)."""
    t = pex('rx_lim', kind)
    t, n = re.subn(r'(?m)^(\.subckt rx_lim .*)$', r'\1 gcp gcn', t, count=1)
    assert n == 1
    T = 1 / f
    return f"""* comparator hysteresis inside the extracted rx_lim ({kind}) {corner}
{rxc.hdr(corner)}{rx_bias.block()}{t}
VDD VDD 0 {rxc.VDD}
VSS VSS 0 0
Ven en 0 {rxc.VDD}
Xb VDD VSS en enb nb rx_bias
vcm cm 0 1.0
vi inp inn 0
vic inn 0 2.5
vd d 0 pwl(0 0 {T / 4} {amp} {3 * T / 4} {-amp} {5 * T / 4} {amp} {7 * T / 4} {-amp} {2 * T} 0)
Bp gcp 0 V=v(cm)+v(d)/2
Bn gcn 0 V=v(cm)-v(d)/2
Xl VDD VSS inp inn q nb enb gcp gcn rx_lim
.control
option temp=27
tran {T / 4000} {2 * T}
let dd = v(gcp)-v(gcn)
meas tran vup find dd when v(q)={rxc.VDD / 2} rise=1
meas tran vdn find dd when v(q)={rxc.VDD / 2} fall=1
meas tran vup2 find dd when v(q)={rxc.VDD / 2} rise=2
meas tran vdn2 find dd when v(q)={rxc.VDD / 2} fall=2
.endc
.end
"""


def run_lim(corners, jobs, kind):
    def one(c):
        d, log, bad = rxc.run(f'lim_{rxc.CN[c]}', lim_deck(c, kind), sub=SUB)
        m = rxc.meas(log)
        r = {k: m.get(k) for k in ('vup', 'vdn', 'vup2', 'vdn2')}
        if r['vup2'] is not None and r['vdn2'] is not None:
            r['hyst_mv'] = (r['vup2'] - r['vdn2']) / 2 * 1e3
            r['offset_mv'] = (r['vup2'] + r['vdn2']) / 2 * 1e3
        r.update(corner=rxc.CN[c], bad=bad)
        print(json.dumps({k: (round(v, 6) if isinstance(v, float) else v) for k, v in r.items()}), flush=True)
        return r
    return rxc.pmap(one, corners, jobs)


# ---- chain: realfsk with the extracted rx_top --------------------------------------------------------------------
def chain_deck(tstop, level=-70, corner='typical', code=9, f_lo=None, fbits=None, maxstep=10e-12, vg0=1.891,
               kind='c'):
    """rx_chain.real_lo_deck with the extracted lsdiv on a0 and the extracted rx_top (no stand-in caps: both level
    shifters are extracted, the Q one inside rx_top)."""
    p = dict(LD.vb.P, **LD.WINNER, **LD.CFED)
    body, ics = LD.ring(p, 'pex')
    vdd = rxc.VDD
    bits = ''.join(f'vbit{b} bit{b} 0 {vdd if (code >> b) & 1 else 0}\nvbitb{b} bitb{b} 0 {0 if (code >> b) & 1 else vdd}\n'
                   for b in range(5))
    a = rx_mix.dbm_emf(level)
    src = f'vph ph 0 pwl({rx_chain.phase_pwl(fbits)})\nBsig dp dn V={a}*sin(2*pi*{f_lo}*time+v(ph))\n'
    ics = ics + f' v(vg)={vg0}'
    return f"""* rx chain, real LO, extracted rx_top ({kind}) + extracted lsdiv, {corner} code {code}
{LD.hdr(corner)}.lib {rxc.PDK}/sm141064.ngspice diode_typical
.include {rxc.PAD}/tt_asw_5v0.spice
.include {rxc.PAD}/pad_model_gf180.spice
vdd vdd 0 {vdd}
vls vls 0 {vdd}
vdv vdv 0 {vdd}
vff vff 0 {vdd}
vctrl vctrl 0 1.65
VSS VSS 0 0
Ven en 0 {vdd}
{bits}{body}{LD.ls_x(LD.S)}{tx_drv.split(tx_drv.S)}Xtxs vls 0 lsout txa txb tx_split
{pex('rx_top', kind)}{src}
Rsp dp pinp 36.5
Rsn dn pinn 36.5
Rdc dn 0 1e9
Xpp 0 pinp inp pad_model_gf180 rroute=40 n_off=3
Xpn 0 pinn inn pad_model_gf180 rroute=40 n_off=3
Xrx VDD VSS inp inn lsout a2 en q_i q_q rx_top
.ic {ics}
.control
option temp=27
save v(q_i) v(q_q) v(a0) v(vg) v(xrx.lo_i) v(xrx.lo_q) v(xrx.oi_p) v(xrx.oi_n) v(xrx.oq_p) v(xrx.oq_n) v(dp) v(pinp) i(vdd)
tran {maxstep} {tstop} 0 {maxstep}
set filetype=binary
write out.raw
quit
.endc
.end
"""


def run_chain(level, kind, flo=411.05e6):
    """rx_chain.py realfsk's flow: a 10 us pre-run (settled? the ring's f with the receiver on it), then 2-FSK
    (1 settling bit + 4 data bits) centred on that f."""
    t0 = time.time()
    bits = np.array([1, 1, 0, 1, 0])
    d, log, bad = rxc.run('chain_pre', chain_deck(10e-6, level=level, f_lo=flo, fbits=bits, kind=kind), sub=SUB,
                          timeout=8 * 3600)
    pl = rxc.read_raw(d / 'out.raw')[0]['vars']
    t, a0 = pl['time'], pl['v(a0)']
    f = {}
    for k, (t1, t2) in enumerate(((3e-6, 6.5e-6), (6.5e-6, 10e-6))):
        m = (t > t1) & (t < t2)
        r = rxc.xings(t[m], a0[m], (a0[m].min() + a0[m].max()) / 2)
        f[k] = (len(r) - 1) / (r[-1] - r[0])
    pre = dict(f1=f[0], f2=f[1], drift_hz=f[1] - f[0], vg_end=float(pl['v(vg)'][-1]), bad=bad,
               wall_s=time.time() - t0)
    print(json.dumps(pre), flush=True)
    d, log, bad = rxc.run('chain', chain_deck(len(bits) / rx_chain.RATE + 5e-6, level=level, f_lo=f[1], fbits=bits,
                                              kind=kind), sub=SUB, timeout=30 * 3600)
    try:
        r = rx_chain.fsk_analyse(d, bits)
        pl = rxc.read_raw(d / 'out.raw')[0]['vars']
        t, a0 = pl['time'], pl['v(a0)']
        ff = []
        for t1 in np.arange(10e-6, t[-1] - 10e-6, 20e-6):
            m = (t > t1) & (t < t1 + 10e-6)
            rr = rxc.xings(t[m], a0[m], (a0[m].min() + a0[m].max()) / 2)
            ff.append((len(rr) - 1) / (rr[-1] - rr[0]))
        r['f_ring_track'] = ff
        ri = rxc.xings(t, pl['v(xrx.lo_i)'], rxc.VDD / 2)
        rq = rxc.xings(t, pl['v(xrx.lo_q)'], rxc.VDD / 2)
        per = np.median(np.diff(ri))
        r['lo_iq_phase'] = float(np.median([((rq[rq > x][0] - x) / per * 360) % 360 for x in ri[:-2] if (rq > x).any()]))
    except Exception as e:  # noqa: BLE001
        r = dict(error=str(e), log=log.splitlines()[-5:])
    r.update(mode='realfsk_pex', kind=kind, pre=pre, level=level, bad=bad, wall_s=time.time() - t0)
    print(json.dumps(r, default=str), flush=True)
    return [r]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['lo', 'lna', 'bb', 'lim', 'chain'])
    ap.add_argument('--corners', default='typical,ss,ff')
    ap.add_argument('--jobs', type=int, default=3)
    ap.add_argument('--pex', default='rcx', help='extraction: rcx (R + C, rcfix) or c (C only)')
    ap.add_argument('--tstop', type=float, default=1.2e-6)
    ap.add_argument('--level', type=float, default=-70)
    a = ap.parse_args()
    cs = a.corners.split(',')
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if a.mode == 'lo':
        rows = run_lo(cs, a.jobs, a.pex, a.tstop)
    elif a.mode == 'lna':
        rows = run_lna(cs, a.jobs, a.pex)
    elif a.mode == 'bb':
        rows = run_bb(cs, a.jobs, a.pex)
    elif a.mode == 'lim':
        rows = run_lim(cs, a.jobs, a.pex)
    else:
        rows = run_chain(a.level, a.pex)
    (OUT / f'{a.mode}.json').write_text(json.dumps(dict(mode=a.mode, pex=a.pex, corners=cs, rows=rows,
                                                        wall_s=time.time() - t0), indent=1, default=str))
    print('wrote', OUT / f'{a.mode}.json', f'{time.time() - t0:.0f} s')


if __name__ == '__main__':
    main()
