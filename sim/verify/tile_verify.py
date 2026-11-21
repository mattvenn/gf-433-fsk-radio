#!/usr/bin/env python3
"""Extracted-tile runs for the verification gaps (docs/plan_verify_gaps.md), on the C-only tile netlist
(layout/pex/tile_c.spice) through sim/top/tb_tile.py's deck():

  gap 2  fskn_*   CPFSK with the receiver's antenna-referred noise (trnoise EMF source), settled high-pass, real ring LO
  gap 3  pvt_*    corner x temperature x supply: an operating point (vbnf), the ring at code 31 (and 0), the settled RX
                  pre-run (ring f, I/Q LO phase) and a -95 dBm CW, TX, power-up; mutations mut_pvt_v300 / mut_pvt_notemp
  gap 4c txrx_*   TX on with RX off, then TX off and rx_en on: the RX side's state after the turnaround
  gap 5  rx0_*    settled receiver, no RF: the limiters must not toggle (mutation: a coupling cap q_i -> baseband node)
  gap 6  fsk_*    CPFSK, noiseless, 16 bits after a preamble, decoded as the firmware would (sim/verify/decode.py)

    python3 sim/verify/tile_verify.py list [smoke|full]
    python3 sim/verify/tile_verify.py run NAME            # -> $TILE_SIMS_OUT/NAME/result.json (default build/verify/tile)
    python3 sim/verify/tile_verify.py analyse NAME
The pre-runs the RX cases start from (rxset_c_tt) are tb_tile.py cases; with TILE_SIMS_OUT pointing here they are
run by `tb_tile.py run rxset_c_tt` (sim/verify/jobs_tile_verify.py does both).
Judge by result.json and the log flags (singular / timestep too small / Transient op started), not exit codes.
"""
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
os.environ.setdefault('TILE_SIMS_OUT', str(REPO / 'build' / 'verify' / 'tile'))
sys.path.insert(0, str(REPO / 'sim' / 'top'))
sys.path.insert(0, str(HERE))
import tb_tile as T  # noqa: E402
import decode as D  # noqa: E402

OUT = T.OUT
RATE, DEV = 50e3, 100e3
LEAD = 2e-6 + 3.7e-11                         # bits start 2 us after the settled start; every bit edge off the
                                              # trnoise 0.25 ns grid (an edge on a noise breakpoint stopped the
                                              # first smoke run at 2.0 us with 'timestep too small')
PRE4 = [1, 0, 1, 0]
DATA16 = [1, 1, 0, 1, 0, 0, 1, 0, 1, 1, 1, 0, 0, 0, 1, 0]
PRE2, DATA2 = [1, 0], [0, 1]                  # the smoke runs: 2 preamble + 2 data bits
NF_TT = 7.3                                   # dB, antenna to comparator, C-only extraction at tt (docs/rx_layout.md:
                                              # LNA 7.23 dB C-only + baseband 0.09 dB)
SAVE_FSK = 'v(uo_out4) v(uo_out5) v(oi_p) v(oi_n) v(oq_p) v(oq_n) v(bi_p) v(bi_n) v(bq_p) v(bq_n) v(vap) v(nb)'
CORNERS3 = ('typical', 'ss', 'ff')
TEMPS = (0, 27, 70)
VDDS = (3.15, 3.3, 3.45)
FW_WAIT_MS = 2.0                              # docs/bringup.md, firmware rule 2: wait 2 ms after rx_en / TX (was 1 ms; Matt 2026-11-20)


def fsk_case(level, pre, data, nf=None, seed=None, threads=6, est=None):
    bits = list(pre) + list(data) + [1]        # + one tail bit (half of it simulated: the filter delay)
    tstop = LEAD + (len(bits) - 0.5) / RATE + 3.7e-11   # off the trnoise 0.25 ns grid: a tstop on a noise breakpoint
                                                          # stops the run with "timestep too small" at tstop
    c = dict(kind='fsk', rx_en=1, step=20e-12, outstep=5e-9, tstop=tstop, pre='rxset_c_tt',
             hold=T.VBNF_RX['typical'], save=SAVE_FSK, threads=threads, npre=len(pre),
             fsk=dict(bits=bits, rate=RATE, dev=DEV, level=level, lead=LEAD), nf=nf, nseed=seed,
             est=est or int(tstop * 1e6 * 440))   # ~440 s per simulated us on 6 threads (smoke runs, machine loaded)
    return c


def cases():
    C = {}
    # gap 6: noiseless FSK through the whole tile; gap 2: with noise
    C['fsk_c_tt_-95_n2'] = fsk_case(-95, PRE2, DATA2)
    C['fskn_c_tt_-105_n2_s1'] = fsk_case(-105, PRE2, DATA2, nf=NF_TT, seed=1)
    # full run (smoke-run speed with the machine loaded: about 440 s per simulated us on 6 threads): one whole packet
    # (4-bit preamble + 16 bits, 412 us, about 2 days on 8 threads: the run's critical path); -70 dBm and the noise
    # runs shorter (2-bit preamble), the bit-error statistics are on the extracted chain (jobs_chain.py)
    # 3 threads (was 8; 2026-11-21): in the full run the 8-thread job waited behind 6-thread ones for 4.5 h with
    # 25 of 28 threads busy; at 3 threads it fits now (about 470 s per simulated us, about 54 h)
    C['fsk_c_tt_-95_n16'] = fsk_case(-95, PRE4, DATA16, threads=3, est=int(412 * 470))
    C['fsk_c_tt_-70_n4'] = fsk_case(-70, PRE2, DATA16[:4])
    for s_ in (1, 2):
        C[f'fskn_c_tt_-105_n6_s{s_}'] = fsk_case(-105, PRE2, DATA16[4:10], nf=NF_TT, seed=s_)
    # gap 5: no RF input, settled: the limiters must not toggle; the mutation adds a coupling cap from q_i
    # (uo_out[4]) to the most sensitive baseband node at 10x its budget (sim/verify/coupling.py)
    base0 = dict(kind='rx0', rx0=True, rx_en=1, step=20e-12, tstop=22e-6, tskip=6e-6, pre='rxset_c_tt',
                 hold=T.VBNF_RX['typical'], save=SAVE_FSK + ' v(a2)', threads=4, est=13500)
    C['rx0_c_tt'] = dict(base0)
    C['mut_rx0_ccoup'] = dict(base0, ccoup_from='budget', mut=True)
    # gap 4c: TX on (RX off) for 1.5 us, then TX off and rx_en on (the firmware order): the RX state after
    C['txrx_c_tt'] = dict(kind='txrx', tx=1, rx_en=0, supply='pg', step=20e-12, tstop=6e-6, hold=T.VBNF_RX['typical'],
                          steps={'ui_in5': [(1.5e-6, 0)], 'ui_in6': [(1.5e-6, 0)], 'rx_en': [(1.5e-6, 1)]},
                          save=T.SAVE['rx'] + ' v(ua4) v(ua5) v(ua2) v(ua3) v(pin3) v(dmid) v(vdp) '
                          + ' '.join(f'v({k})' for k in T.S1_NODES), threads=4, est=3300)
    # gap 3: PVT
    for corner in CORNERS3 + ('sf', 'fs'):
        cn = T.CN[corner]
        for tc in TEMPS:
            for v in VDDS:
                tag = f'pvt_{cn}_{tc}_{v:.2f}'
                pt = dict(corner=corner, temp=tc, vap=v, vdp=v, vnom=v)
                C[f'{tag}_op'] = dict(pt, kind='op', tstop=0, rx_en=1, ic=None, est=60)
                C[f'{tag}_k31'] = dict(pt, kind='ring', code=31, tstop=T.VCO_TSTOP, icop=f'{tag}_op', est=2100)
                if corner in ('ff', 'fs'):     # the bottom of the range: highest where the devices are fast
                    C[f'{tag}_k0'] = dict(pt, kind='ring', code=0, tstop=T.VCO_TSTOP, icop=f'{tag}_op', est=2100)
                if corner not in CORNERS3:
                    continue
                sv = T.SAVE['ring'] + ' v(lo_i) v(lo_q) v(nb) ' + ' '.join(f'v({k})' for k in T.SETTLE)
                C[f'{tag}_set'] = dict(pt, kind='ring', rx_en=1, step=20e-12, tstop=3e-6, hold='op', icop=f'{tag}_op',
                                       settle=True, save=sv, threads=4, est=2000)
                C[f'{tag}_rxs'] = dict(pt, kind='rx', rx_en=1, step=20e-12, tstop=22e-6, tskip=6e-6, rfdf=(200e3, -95),
                                       pre=f'{tag}_set', hold='op', icop=f'{tag}_op', threads=4, est=13500,
                                       save=T.SAVE['rx'] + ' ' + ' '.join(f'v({k})' for k in T.S1_NODES))
                C[f'{tag}_tx'] = dict(pt, kind='tx', tx=1, supply='pg', icop=f'{tag}_op', save=T.SAVE['tx'],
                                      code=T.CODE[corner], est=4200)
                # 50 us: at ss / 70 C / 3.15 V the ring had not started by 16 us (vbnf still charging through the
                # reference's 1 Mohm / 20 pF filter, 0.69 of its 1.41 V; first smoke run, 2026-11-20)
                C[f'{tag}_pu'] = dict(pt, kind='pwr', supply='ideal', ramp=10e-6, ic='uic', step=20e-12, tstop=50e-6,
                                      save=T.SAVE['pwr'], threads=4, est=16000)
    # gap 3 mutations: a 3.45 V point run at 3.0 V (the supply check must flag it); 70 C not passed to the deck
    C['mut_pvt_v300'] = dict(corner='typical', temp=27, vap=3.0, vdp=3.0, vnom=3.45, kind='ring', code=31,
                             tstop=T.VCO_TSTOP, icop='pvt_tt_27_3.45_op', mut=True, est=2100)
    C['mut_pvt_notemp'] = dict(corner='typical', temp=70, vap=3.3, vdp=3.3, vnom=3.3, kind='op', tstop=0, rx_en=1,
                               ic=None, notemp=True, mut=True, est=60)
    return C


SMOKE = ['fsk_c_tt_-95_n2', 'fskn_c_tt_-105_n2_s1', 'rx0_c_tt', 'txrx_c_tt',
         'pvt_ss_70_3.15_op', 'pvt_ss_70_3.15_k31', 'pvt_ss_70_3.15_set', 'pvt_ss_70_3.15_rxs', 'pvt_ss_70_3.15_tx',
         'pvt_ss_70_3.15_pu', 'pvt_tt_27_3.45_op', 'mut_pvt_v300', 'mut_pvt_notemp']


def deps(name, c):
    d = []
    for k in ('pre', 'icop'):
        if c.get(k):
            d.append(c[k])
    return d


def resolve(name):
    """The case with run-time values filled in: vbnf from its operating-point run, the gap-5 coupling cap."""
    c = dict(cases()[name])
    if c.get('icop'):
        op = json.loads((OUT / c['icop'] / 'result.json').read_text())
        assert 'error' not in op and not op['flags'], f"{c['icop']}: {op.get('error') or op['flags']}"
        vb = round(op['vbnf'], 5)
        if c.get('hold') == 'op':
            c['hold'] = vb
        if c['kind'] in ('ring', 'tx') and not c.get('pre'):
            c['ic'] = dict(a2=0) if c.get('hold') is not None else dict(a2=0, vbnf=vb)
    if c.get('ccoup_from'):
        b = json.loads((REPO / 'build' / 'verify' / 'coupling' / 'budget.json').read_text())
        c['ccoup'] = ('uo_out4', b['tile_most_sensitive']['tile_node'], 10 * b['tile_most_sensitive']['budget_f'])
    return c


EXTRA = ('est', 'threads', 'rev', 'outstep', 'npre', 'icop', 'ccoup_from')


def make_deck(c):
    dk = T.deck({k: v for k, v in c.items() if k not in EXTRA})
    if c.get('outstep'):            # long runs: output interpolated every outstep (the solver's step is unchanged)
        a = f"tran {c['step']} {c['tstop']} 0 {c['step']}"
        assert a in dk, 'tran line'
        dk = dk.replace(a, f"tran {c['outstep']} {c['tstop']} 0 {c['step']}").replace('.control\n', '.control\noption interp\n', 1)
    return dk


def run(name):
    c = resolve(name)
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    seed = f"set rndseed={c['nseed']}\n" if c.get('nseed') else ''
    (d / '.spiceinit').write_text(f'set ng_nomodcheck\nset num_threads={c.get("threads", 1)}\noption noinit\n{seed}')
    (d / 'deck.cir').write_text(make_deck(c))
    for f in ('out.raw', 'result.json', 'op.txt'):
        (d / f).unlink(missing_ok=True)
    t = time.time()
    subprocess.run(['bash', '-c', f'cd {d} && nice -n 5 ngspice -b deck.cir > deck.log 2>&1'], check=False)
    (d / 'runtime.txt').write_text(f'{time.time() - t:.0f}\n')
    return analyse(name)


def deck_meta(d):
    """What the deck actually ran: option temp, the supply sources' values."""
    txt = (d / 'deck.cir').read_text() if (d / 'deck.cir').exists() else ''
    m = re.search(r'^option temp=(\S+)', txt, re.M)
    va = re.search(r'^vsa \S+ 0 (\S+)', txt, re.M)
    vd = re.search(r'^vsd \S+ 0 (\S+)', txt, re.M)
    f = lambda x: float(x.group(1)) if x and re.match(r'^[-+0-9.eE]+$', x.group(1)) else None  # noqa: E731
    return dict(deck_temp=f(m), deck_vsa=f(va), deck_vsd=f(vd))


def an_op(pl, c, d):
    r = {k: float(np.real(pl[f'v({k})'][0])) for k in ('vbnf', 'vg', 'nb', 'vap', 'vdp') if f'v({k})' in pl}
    if 'vbnf' not in r:            # op raw vectors may be named without v()
        r.update({k: float(np.real(pl[k][0])) for k in ('vbnf', 'vg', 'nb', 'vap', 'vdp') if k in pl})
    return r


def an_fsk(pl, c, d):
    t = pl['time']
    fk = c['fsk']
    r = D.decode(t, pl['v(uo_out4)'], pl['v(uo_out5)'], fk['bits'][:-1], c['npre'], fk['lead'], RATE)
    r['level_dbm'], r['nf'], r['seed'] = fk['level'], c.get('nf'), c.get('nseed')
    r['bits_sent'] = fk['bits'][:-1]
    m = t > fk['lead']
    oi = pl['v(oi_p)'][m] - pl['v(oi_n)'][m]
    r['oi_mean'], r['oi_rms'] = float(np.mean(oi)), float(np.std(oi))
    r['mix_i_mean_mv'] = float(np.mean(pl['v(bi_p)'][m] - pl['v(bi_n)'][m]) * 1e3)
    return r


def an_rx0(pl, c, d):
    t = pl['time']
    m = t >= c['tskip']
    r = {}
    for k, n in (('q_i', 'v(uo_out4)'), ('q_q', 'v(uo_out5)')):
        v = pl[n][m]
        e = len(D.xings(t[m], v, D.VTH)) + len(D.xings(t[m], v, D.VTH, False))
        r[f'{k}_edges'] = int(e)
        r[f'{k}_level'] = float(np.mean(v))
    for k, (a, b) in (('oi', ('v(oi_p)', 'v(oi_n)')), ('oq', ('v(oq_p)', 'v(oq_n)'))):
        x = pl[a][m] - pl[b][m]
        r[f'{k}_mean'], r[f'{k}_pp'] = float(np.mean(x)), float(np.ptp(x))
    r['window_us'] = float((t[-1] - c['tskip']) * 1e6)
    return r


def an_txrx(pl, c, d):
    """During TX (RX off): what reaches the LNA input pins and the analog supply; after the turnaround: the mixer's
    DC offset step and the stage-1 coupling nodes against the settled values (rxset_c_tt), the input to the
    baseband recovery bench (sim/verify/chain_x.py en)."""
    t = pl['time']
    ts = c['steps']['rx_en'][0][0]
    tx = (t > 0.5e-6) & (t < ts)
    rx = t > t[-1] - 1e-6
    r = dict(t_switch_us=ts * 1e6)
    lna = pl['v(ua4)'] - pl['v(ua5)']
    r['lna_in_pp_tx_mv'] = float(np.ptp(lna[tx]) * 1e3)
    r['ua4_max_tx'], r['ua4_min_tx'] = float(pl['v(ua4)'][tx].max()), float(pl['v(ua4)'][tx].min())
    r['vap_ripple_tx_mv'] = float(np.ptp(pl['v(vap)'][tx]) * 1e3)
    r['tx_dip_pp_v'] = float(np.ptp(pl['v(pin3)'][tx] - pl['v(dmid)'][tx]))
    r['tx_dip_pp_after_v'] = float(np.ptp(pl['v(pin3)'][rx] - pl['v(dmid)'][rx]))
    for a in ('bi', 'bq'):
        x = pl[f'v({a}_p)'] - pl[f'v({a}_n)']
        r[f'{a}_off_mv_before'] = float(np.mean(x[tx]) * 1e3)
        r[f'{a}_off_mv_after'] = float(np.mean(x[rx]) * 1e3)
        r[f'{a}_cm_before'] = float(np.mean((pl[f'v({a}_p)'] + pl[f'v({a}_n)'])[tx] / 2))
        r[f'{a}_cm_after'] = float(np.mean((pl[f'v({a}_p)'] + pl[f'v({a}_n)'])[rx] / 2))
    try:
        st = json.loads((OUT / 'rxset_c_tt' / 'result.json').read_text())['settle']
        r['s1_vs_settled_mv'] = {k: (float(np.mean(pl[f'v({k})'][rx])) - st[k]) * 1e3 for k in T.S1_NODES}
    except (OSError, KeyError):
        r['s1_vs_settled_mv'] = None
    for k in ('uo_out4', 'uo_out5'):
        r[f'{k}_after'] = float(np.mean(pl[f'v({k})'][rx]))
    r['lo_i_pp_after'] = float(np.ptp(pl['v(lo_i)'][rx]))
    r['lo_i_pp_tx'] = float(np.ptp(pl['v(lo_i)'][tx]))
    return r


def analyse(name):
    c = resolve(name) if name in cases() else None
    d = OUT / name
    r = dict(name=name, flags=T.log_flags(d), case={k: v for k, v in cases()[name].items()})
    r.update(deck_meta(d))
    if (d / 'runtime.txt').exists():
        r['runtime_s'] = float((d / 'runtime.txt').read_text())
    try:
        pl = T.read_raw(d / 'out.raw')[0]['vars']
    except Exception as e:  # noqa: BLE001
        r['error'] = f'no raw: {e}'
        (d / 'result.json').write_text(json.dumps(r, indent=1, default=str))
        return r
    try:
        k = c['kind']
        if k in T.KIND:
            r.update(T.KIND[k](pl, dict(T.DEF, **{a: b for a, b in c.items() if a not in EXTRA})))
            if 'v(vap)' in pl:
                r['vap_mean'] = float(np.mean(pl['v(vap)']))
        else:
            r.update(dict(op=an_op, fsk=an_fsk, rx0=an_rx0, txrx=an_txrx)[k](pl, c, d))
    except Exception as e:  # noqa: BLE001
        r['error'] = f'analysis: {type(e).__name__}: {e}'
    (d / 'result.json').write_text(json.dumps(r, indent=1, default=float))
    return r


def main():
    a = sys.argv[1:]
    if not a or a[0] == 'list':
        sel = a[1] if len(a) > 1 else 'full'
        C = cases()
        for n in (SMOKE if sel == 'smoke' else C):
            print(f"{n:32s} {C[n]['kind']:5s} est {C[n]['est']:6d} s thr {C[n].get('threads', 1)} deps {deps(n, C[n])}")
        return
    rc = 0
    for n in a[1:]:
        r = run(n) if a[0] == 'run' else analyse(n)
        print(json.dumps({k: v for k, v in r.items() if k != 'case'}, indent=1, default=str)[:4000])
        if 'error' in r or r.get('flags'):
            rc = 1
    sys.exit(rc)


if __name__ == '__main__':
    main()
