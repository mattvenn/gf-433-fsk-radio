#!/usr/bin/env python3
"""The receiver chain with its EXTRACTED blocks (layout/pex/rx_<cell>_c.spice, C only, magic 8.3.642; the layout
labels every net with its sim name), for the verification gaps that can't run on the whole tile:

  mc     gap 1  one Monte Carlo sample (mismatch on, one draw per device instance): (A) both comparators'
                hysteresis / offset, (B) LNA + ideal LO + both mixers + both baseband arms for 4 us with a -70 dBm
                tone 2 MHz off (mixer DC offset at LO start, stage-1 output offset, I/Q conversion gain and phase),
                (C) both baseband + limiter-stage arms in .ac (gain / phase at 100 kHz); then the model's sensitivity
                with these numbers (sim/verify/rxm.py)
  fsk    gaps 2 / 6  CPFSK through the chain (ideal LO) with a known preamble, optional trnoise at the antenna
  ovl1   gap 4a/b phase 1: a CW burst at fLO + 100 kHz (-10 / 0 / +6 dBm) through the RF chain for 12 us: the baseband
                state at the end and the mixer output during the burst
  rate   gap 4b  a +6 dBm burst for 2 us: every LNA and mixer device's terminal voltages against the 3.3 V rating
  bbrec  gap 4a/b/c phase 2: the baseband + limiters alone (extracted rx_bb, rx_lim, rx_bias), the mixer outputs as
                sources (DC, offset and signal taken from the phase-1 run or the tile), started from the phase-1
                state: the rest of a 1 ms burst, then -95 dBm FSK for 2.5 ms; time until the bits decode again

    python3 sim/verify/chain_x.py mc --seed 7 [--corner typical] [--kind pex|sch] [--mut mmoff|merge]
    python3 sim/verify/chain_x.py fsk --level -105 --nf 7.3 --seed 1 --ndata 8 [--kind pex|sch]
    python3 sim/verify/chain_x.py ovl1 --level -10 | rate --level 6 [--vdd 4.5] | bbrec --from ovl1_tt_-10 ...
Output: build/verify/chain/<name>/ (deck.cir, deck.log, result.json). --kind sch is the schematic (an extra, for
statistics only, labelled as such); the default is the extraction. Judge by result.json and the log flags.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
for p in ('sim/verify', 'sim/rx'):          # (not layout/gen: its rx_mix.py is the layout generator)
    sys.path.insert(0, str(REPO / p))
import rxc  # noqa: E402
import rx_top  # noqa: E402
import rx_mix  # noqa: E402
import rx_bias  # noqa: E402
import rx_bb  # noqa: E402
import rx_lim  # noqa: E402
import rx_chain  # noqa: E402
import decode as D  # noqa: E402

OUT = REPO / 'build' / 'verify' / 'chain'
PEXD = REPO / 'layout' / 'pex'
FLO = rx_mix.FLO
VDD = rxc.VDD
CELLS = ('rx_bias', 'rx_lna', 'rx_mix', 'rx_bb', 'rx_lim')
BAD = ('singular', 'timestep too small', 'transient op started', 'error:', 'no such', 'unknown subckt', 'timeout')
RATING = 3.63          # V: the 3.3 V devices' limit (3.3 V + 10 %)


# ------------------------------------------------------------------------------------------------ netlist helpers
def pex(cell):
    return (PEXD / f'{cell}_c.spice').read_text()


def swap_pex(deck, cells=CELLS):
    """The schematic .subckt of each cell replaced by its C-only extraction (the same port order)."""
    for cell in cells:
        new, n = re.subn(rf'(?ms)^\.subckt {cell} .*?^\.ends\n?', lambda m: pex(cell), deck, count=1)
        assert n == 1, f'no .subckt {cell} in the deck'
        deck = new
    return deck


FET = re.compile(r'^(X\S+)(\s.*\s(?:n|p)fet_03v3\s.*?)\bm=(\d+)\s*$', re.M)


def split_m(deck, keep=()):
    """GF180's ngspice models draw one mismatch per instance and ignore m: every fet with m = k > 1 becomes k unit
    instances (names suffixed _u1 ...). keep: instance names left merged (the 'merge' mutation)."""
    def rep(mo):
        name, body, k = mo.group(1), mo.group(2), int(mo.group(3))
        if k <= 1 or name in keep:
            return mo.group(0)
        return '\n'.join(f'{name}_u{i}{body}m=1' for i in range(1, k + 1))
    return FET.sub(rep, deck)


def merged_fets(deck):
    """Static MC check: fet instances with m > 1 (each would carry a single mismatch draw for all its units)."""
    return [(mo.group(1), int(mo.group(3))) for mo in FET.finditer(deck) if int(mo.group(3)) > 1]


def merge_pex(deck, cell='rx_bb', gate='inp', drain='o1n'):
    """The 'merge' mutation on an extraction: the stage-1 fingers of one side (same gate / drain / source) written back
    as one instance with m = the finger count, as a netlister that merges parallel devices would."""
    m = re.search(rf'(?ms)^\.subckt {cell} .*?^\.ends', deck)
    sub = m.group(0)
    pat = re.compile(rf'^(X\S+) (\S+) {gate} (\S+) VSS nfet_03v3 (.*w=20u l=1u)\s*$', re.M)
    hits = [h for h in pat.finditer(sub) if drain in (h.group(2), h.group(3))]
    assert len(hits) > 1, f'merge mutation: {len(hits)} fingers found'
    h0 = hits[0]
    new = sub
    for h in hits:
        new = new.replace(h.group(0) + '\n', '', 1)
    new = new.replace('.ends', f'{h0.group(1)}m {h0.group(2)} {gate} {h0.group(3)} VSS nfet_03v3 {h0.group(4)} m={len(hits)}\n.ends', 1)
    return deck.replace(sub, new), len(hits)


def mc_hdr(corner, seed, mm=1, pad=False):
    return rxc.hdr(corner, pad=pad) + f'.param sw_stat_mismatch={mm}\n.options seed={seed}\n'


def run(name, deck, threads=1, seed=None, timeout=12 * 3600):
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    rs = f'set rndseed={seed}\n' if seed else ''
    (d / '.spiceinit').write_text(f'set ng_nomodcheck\nset num_threads={threads}\noption noinit\n{rs}')
    (d / 'deck.cir').write_text(deck)
    for f in d.glob('*.raw'):
        f.unlink()
    t = time.time()
    try:
        subprocess.run(['nice', '-n', '10', 'ngspice', '-b', 'deck.cir'], cwd=d, stdout=open(d / 'deck.log', 'w'),
                       stderr=subprocess.STDOUT, timeout=timeout)
    except subprocess.TimeoutExpired:
        (d / 'deck.log').open('a').write('\nTIMEOUT\n')
    log = (d / 'deck.log').read_text(errors='replace')
    flags = [w for w in BAD if w in log.lower()]
    (d / 'runtime.txt').write_text(f'{time.time() - t:.1f}\n')
    return d, log, flags


def raw(d):
    return rxc.read_raw(d / 'out.raw')[0]['vars']


def dft(t, y, f, t0, t1=None):
    t1 = t[-1] if t1 is None else t1
    n = int((t1 - t0) * f)
    if n < 1:
        return 0j
    tu = np.linspace(t0, t0 + n / f, n * 256, endpoint=False)
    return 2 * np.mean(np.interp(tu, t, y) * np.exp(-2j * np.pi * f * tu))


def finish(d, r):
    (d / 'result.json').write_text(json.dumps(r, indent=1, default=float))
    print(json.dumps({k: v for k, v in r.items() if not isinstance(v, list) or len(v) < 40}, default=float)[:3000])
    return r


# ------------------------------------------------------------------------------------------------ gap 1: Monte Carlo
def mc_decks(corner, seed, kind, mut):
    mm = 0 if mut == 'mmoff' else 1
    lim_pex = re.sub(r'(?m)^(\.subckt rx_lim .*)$', r'\1 gcp gcn', pex('rx_lim'), count=1)
    # (A) comparators: a slow +-150 mV triangle on gcp / gcn of both arms' comparators
    T = 1 / 20e3       # three periods: the second rising / falling switching points are always inside the run
    tri = (f'pwl(0 0 {T / 4} 0.15 {3 * T / 4} -0.15 {5 * T / 4} 0.15 {7 * T / 4} -0.15 {9 * T / 4} 0.15 '
           f'{11 * T / 4} -0.15 {3 * T} 0)')
    if kind == 'pex':
        cmp_sub = rx_bias.block() + lim_pex
        inst = ''.join(f'Xl{k} VDD VSS inp{k} inn{k} q{k} nb enb gcp{k} gcn{k} rx_lim\nvi{k} inp{k} inn{k} 0\n'
                       f'vic{k} inn{k} 0 2.5\nBp{k} gcp{k} 0 V=1.0+v(d)/2\nBn{k} gcn{k} 0 V=1.0-v(d)/2\n' for k in (1, 2))
    else:
        cmp_sub = rx_bias.block() + '.subckt cmp VDD VSS gcp gcn q nb\n' + rx_lim.comparator(rx_lim.S, 'gcp', 'gcn', 'q') + '.ends\n'
        inst = ''.join(f'Xc{k} VDD VSS gcp{k} gcn{k} q{k} nb cmp\nBp{k} gcp{k} 0 V=1.0+v(d)/2\nBn{k} gcn{k} 0 V=1.0-v(d)/2\n'
                       for k in (1, 2))
    meas = ''.join(f'meas tran up{k} find dd when v(q{k})={VDD / 2} rise=1\nmeas tran dn{k} find dd when v(q{k})={VDD / 2} fall=1\n'
                   f'meas tran up{k}b find dd when v(q{k})={VDD / 2} rise=2\nmeas tran dn{k}b find dd when v(q{k})={VDD / 2} fall=2\n'
                   for k in (1, 2))
    a = f"""* MC comparators {corner} seed {seed} {kind} {mut}
{mc_hdr(corner, seed, mm)}{cmp_sub}
VDD VDD 0 {VDD}
VSS VSS 0 0
Ven en 0 {VDD}
Xb VDD VSS en enb nb rx_bias
vd d 0 {tri}
{inst}.control
option temp=27
tran {T / 4000} {3 * T}
let dd = v(d)
{meas}.endc
.end
"""
    # (B) front end: dipole + pads + LNA + ideal LO + mixers + both baseband arms + limiters, a -70 dBm tone 2 MHz off
    body = rx_chain.front(None, None, tone=(2e6, -70)) + rx_chain.chain_body()
    sv = ('v(bi_p) v(bi_n) v(bq_p) v(bq_n) v(ri_p) v(ri_n) v(rq_p) v(rq_n) v(xbbi.o1p) v(xbbi.o1n) v(xbbq.o1p) '
          'v(xbbq.o1n) i(VDD)')
    b = f"""* MC front end {corner} seed {seed} {kind} {mut}
{mc_hdr(corner, seed, mm, pad=True)}{rx_top.block()}
VDD VDD 0 {VDD}
VSS VSS 0 0
Ven en 0 {VDD}
{body}.control
option temp=27
save {sv}
tran 20p 4u 0 20p
set filetype=binary
write out.raw {sv}
.endc
.end
"""
    # (C) both baseband arms + limiters, .ac from the mixer's DC
    c = f"""* MC baseband ac {corner} seed {seed} {kind} {mut}
{mc_hdr(corner, seed, mm)}{rx_bias.block()}{rx_bb.block()}{rx_lim.block()}
VDD VDD 0 {VDD}
VSS VSS 0 0
Ven en 0 {VDD}
Xb VDD VSS en enb nb rx_bias
vcm cm 0 2.45
vin ip cm dc 0 ac 0.5
vinn cm im dc 0 ac 0.5
Xbbi VDD VSS ip im oip oin nb enb rx_bb
Xbbq VDD VSS ip im oqp oqn nb enb rx_bb
Xli VDD VSS oip oin qi nb enb rx_lim
Xlq VDD VSS oqp oqn qq nb enb rx_lim
.control
option temp=27
op
print v(xbbi.o1p)-v(xbbi.o1n) v(xbbq.o1p)-v(xbbq.o1n)
ac lin 3 50e3 150e3
let dgi = v(xli.gcp)-v(xli.gcn)
let dgq = v(xlq.gcp)-v(xlq.gcn)
wrdata ac.txt dgi dgq
.endc
.end
"""
    if kind == 'pex':
        # (split_m only touches the schematic subckts left in the deck and not instantiated, e.g. rx_lo, rx_top)
        b = split_m(swap_pex(b))
        c = split_m(swap_pex(c, ('rx_bias', 'rx_bb', 'rx_lim')))
        a = split_m(swap_pex(a, ('rx_bias',)))
        if mut == 'merge':
            b, _ = merge_pex(b)
    else:
        keep = ('XM1a', 'XM1b') if mut == 'merge' else ()
        a, b, c = split_m(a, keep), split_m(b, keep), split_m(c, keep)
    return a, b, c


def mc(a):
    tag = f"mc_{a.kind}_{rxc.CN[a.corner]}_s{a.seed}" + (f'_{a.mut}' if a.mut else '')
    da, db, dc = mc_decks(a.corner, a.seed, a.kind, a.mut)
    r = dict(name=tag, corner=rxc.CN[a.corner], seed=a.seed, kind=a.kind, mut=a.mut, flags=[])
    r['merged_fets'] = sorted(set(merged_fets(da) + merged_fets(db) + merged_fets(dc)))
    if a.only == 'cmp':                      # redo the comparator part of an existing sample
        r = json.loads((OUT / tag / 'result.json').read_text())
        r['flags'] = [f for f in r['flags'] if f != 'error:']
        r.pop('error', None)
    d, log, fl = run(tag + '/cmp', da)
    r['flags'] += fl
    mv = rxc.meas(log)
    for k, arm in ((1, 'i'), (2, 'q')):
        up, dn = mv.get(f'up{k}b'), mv.get(f'dn{k}b')      # the second switching points (the first rise can be
        if up is None or dn is None:                        # the start-up settling at t = 0)
            r['error'] = f'comparator {arm}: no switching in +-150 mV'
            continue
        r[f'vos_{arm}_mv'], r[f'hyst_{arm}_mv'] = (up + dn) / 2 * 1e3, (up - dn) / 2 * 1e3
    if a.only == 'cmp':
        return finish(OUT / tag, r)
    d, log, fl = run(tag + '/fe', db)
    r['flags'] += fl
    try:
        pl = raw(d)
        t = pl['time']
        m = t > 3e-6
        for arm in ('i', 'q'):
            x = pl[f'v(b{arm}_p)'] - pl[f'v(b{arm}_n)']
            r[f'mix_{arm}_off_mv'] = float(np.mean(x[m]) * 1e3)      # 1 us = two periods of the 2 MHz tone
            r[f'conv_{arm}'] = dft(t, x, 2e6, 2e-6)
            s1 = pl[f'v(xbb{arm}.o1p)'] - pl[f'v(xbb{arm}.o1n)']
            r[f's1_{arm}_off_v'] = float(np.mean(s1[m]))
            r[f'lna_{arm}_off_mv'] = float(np.mean(pl[f'v(r{arm}_p)'][m] - pl[f'v(r{arm}_n)'][m]) * 1e3)
        ci, cq = r.pop('conv_i'), r.pop('conv_q')
        r['conv_gq'] = float(abs(cq) / abs(ci))
        r['conv_phase'] = float(np.angle(cq / ci, deg=True))
        r['idd_ma'] = float(-np.mean(pl['i(vdd)'][m]) * 1e3)
    except Exception as e:  # noqa: BLE001
        r['error'] = f'front end: {e}'
    d, log, fl = run(tag + '/ac', dc)
    r['flags'] += fl
    try:
        x = np.loadtxt(d / 'ac.txt')            # f re im f re im, rows 50 / 100 / 150 kHz
        hi, hq = x[1, 1] + 1j * x[1, 2], x[1, 4] + 1j * x[1, 5]
        r['bb_gain_i'], r['bb_gain_q'] = float(abs(hi)), float(abs(hq))
        r['bb_gq'] = float(abs(hq) / abs(hi))
        r['bb_dphase'] = float(np.angle(hq / hi, deg=True))
    except (OSError, IndexError, ValueError):
        r['error'] = 'ac: no output'
    return finish(OUT / tag, r)


# ------------------------------------------------------------------------------------------------ gaps 2 / 6: FSK
SETTLE_X = ('xbbi.o1p', 'xbbi.o1n', 'xbbq.o1p', 'xbbq.o1n', 'bi_p', 'bi_n', 'bq_p', 'bq_n')


def fskpre(corner, kind):
    """The settled baseband for the FSK runs (as tb_tile.py's rxset / S1_NODES on the tile): a 3 us run with the LO on
    and no RF; the stage-1 outputs and the mixer outputs' running means over the last 1 us. The FSK runs start from
    them (.ic), so the stage-1 -> stage-2 AC coupling starts charged to the LO start-up offset: without this the
    baseband sits on that offset (about +-1 V at its outputs, the comparators idle) for 0.3-1 ms, longer than an
    8-bit run (first smoke run, 2026-11-20: no comparator edges at all, errors at chance whatever the noise)."""
    tag = f'fskpre_{kind}_{rxc.CN[corner]}'
    f = OUT / tag / 'result.json'
    if f.exists():
        r = json.loads(f.read_text())
        if not r.get('flags') and 'settle' in r:
            return r
    deck = rx_chain.fsk_deck(corner, -200, 3e-6, None, 20e-12, np.array([1]))
    sv = ' '.join(f'v({n})' for n in SETTLE_X)
    deck = re.sub(r'(?m)^save .*$', f'save {sv}', deck, count=1)
    deck = swap_pex(deck) if kind == 'pex' else deck
    d, log, fl = run(tag, deck)
    r = dict(name=tag, flags=fl)
    try:
        pl = raw(d)
        t = pl['time']
        m1, m2 = t >= t[-1] - 1e-6, (t >= t[-1] - 2e-6) & (t < t[-1] - 1e-6)
        r['settle'] = {n: float(np.mean(pl[f'v({n})'][m1])) for n in SETTLE_X}
        r['drift_mv'] = {n: (r['settle'][n] - float(np.mean(pl[f'v({n})'][m2]))) * 1e3 for n in SETTLE_X}
    except Exception as e:  # noqa: BLE001
        r['error'] = str(e)
    finish(d, r)
    return r


KNOWN_SIGN, KNOWN_DELAY = -1, 1.0e-6   # the chain's rotation sign (rx_design.md Table VI, and every noiseless run) and
                                       # bit delay (the noiseless -95 dBm run fsk_pex_tt_-95_n2: 1.0-1.5 us)


def known_decode(pl, bits, npre):
    """The bit-error statistic of gap 2: the sign and the bit timing known (as the model's genie timing), so that the
    count measures the receiver, not the preamble learning (which fails at -114 dBm, where the preamble's own bits
    are wrong a quarter of the time)."""
    import rx_model
    tu, st = D.steps(pl['time'], pl['v(q_i)'], pl['v(q_q)'], 1 / rx_chain.RATE + 3.7e-11)
    sps = int(round(D.FS / rx_chain.RATE))
    nb = min(len(bits), int((len(st) - int(KNOWN_DELAY * D.FS)) // sps))
    c = rx_model.counts(st, sps, nb, int(KNOWN_DELAY * D.FS))
    dec = (KNOWN_SIGN * c[npre:]) > 0
    ref = np.asarray(bits[npre:nb]) > 0
    return dict(bit_errors_known=int(np.sum(dec != ref)), n_data_known=int(len(ref)), counts_known=[int(x) for x in c])


def fsk(a):
    pre = [1, 0, 1, 0]
    rng = np.random.default_rng(1000 + a.seed)
    data = list(rng.integers(0, 2, a.ndata)) if a.ndata != 2 else [0, 1]
    bits = [1] + pre + data + [1]              # 1 settling bit, the preamble, the data, a tail bit (half simulated)
    nf = a.nf
    tstop = (len(bits) - 0.5) / rx_chain.RATE + 3.7e-11
    deck = rx_chain.fsk_deck(a.corner, a.level, tstop, nf, 20e-12, np.array(bits))
    # every bit edge 37 ps off the trnoise 0.25 ns grid (an edge on a noise breakpoint: 'timestep too small')
    deck = re.sub(r'(?m)^(vph ph 0 pwl\()(.*)\)$', lambda m: m.group(1) + ' '.join(
        f'{float(x) + (3.7e-11 if i % 2 == 0 and float(x) > 0 else 0):.12e}' if i % 2 == 0 else x
        for i, x in enumerate(m.group(2).split())) + ')', deck)
    deck = deck.replace('tran 2e-11', 'tran 5e-09', 1).replace('.control\n', '.control\noption interp\n', 1)
    deck = swap_pex(deck) if a.kind == 'pex' else deck
    st = fskpre(a.corner, a.kind)
    if 'settle' not in st:
        return finish(OUT / 'fskpre_fail', dict(name='fsk', error=f"settle pre-run: {st.get('error') or st.get('flags')}"))
    deck = deck.replace('.control\n', '.ic ' + ' '.join(f'v({k})={v:.6f}' for k, v in st['settle'].items()) + '\n.control\n', 1)
    tag = f"fsk_{a.kind}_{rxc.CN[a.corner]}_{a.level:g}_n{a.ndata}" + (f'_nf{nf:g}_s{a.seed}' if nf is not None else '') \
        + (f'_{a.mut}' if a.mut else '')
    d, log, fl = run(tag, deck, seed=a.seed if nf is not None else None)
    r = dict(name=tag, kind=a.kind, level=a.level, nf=nf, seed=a.seed, flags=fl, bits=bits[1:-1], npre=len(pre))
    try:
        pl = raw(d)
        r.update(D.decode(pl['time'], pl['v(q_i)'], pl['v(q_q)'], bits[1:-1], len(pre), 1 / rx_chain.RATE + 3.7e-11))
        r.update(known_decode(pl, bits[1:-1], len(pre)))
    except Exception as e:  # noqa: BLE001
        r['error'] = str(e)
    return finish(d, r)


# ------------------------------------------------------------------------------------------------ gap 4: overload
def state_nodes():
    """Every net of the extracted rx_bb and rx_lim (ports and internal), for the phase-2 start state."""
    nodes = {}
    for cell, insts in (('rx_bb', ('xbbi', 'xbbq')), ('rx_lim', ('xli', 'xlq'))):
        t = pex(cell)
        sub = re.search(rf'(?ms)^\.subckt {cell} (.*?)$(.*?)^\.ends', t)
        ports = sub.group(1).split()
        nets = set()
        for ln in sub.group(2).splitlines():
            if ln.startswith('X'):
                f = ln.split()
                nets.update(x for x in f[1:5] if '=' not in x)
            elif ln.startswith('C'):
                nets.update(ln.split()[1:3])
        nets -= {'VDD', 'VSS', '0'}
        nodes[cell] = (insts, sorted(n for n in nets if n not in ports), ports)
    return nodes


def ovl1_deck(corner, level, tstop, vdd=VDD, save_lna=False):
    """Dipole (CW at fLO + 100 kHz, `level` dBm) + pads + the extracted chain, ideal LO."""
    body = rx_chain.front(None, None, tone=(100e3, level)) + rx_chain.chain_body()
    nd = state_nodes()
    sv = ['v(bi_p)', 'v(bi_n)', 'v(bq_p)', 'v(bq_n)', 'v(q_i)', 'v(q_q)', 'v(inp)', 'v(inn)', 'v(pinp)', 'v(pinn)', 'i(VDD)']
    for cell, (insts, internal, ports) in nd.items():
        sv += [f'v({i}.{n})' for i in insts for n in internal]
    sv += ['v(oi_p)', 'v(oi_n)', 'v(oq_p)', 'v(oq_n)', 'v(nb)', 'v(enb)']
    step = '20p' if save_lna else '5n'
    if save_lna:      # every LNA and mixer net, full resolution (the rating check)
        sv = ['v(inp)', 'v(inn)', 'v(pinp)', 'v(pinn)', 'v(ri_p)', 'v(ri_n)', 'v(rq_p)', 'v(rq_n)', 'v(bi_p)', 'v(bi_n)',
              'v(bq_p)', 'v(bq_n)', 'v(lo_i)', 'v(lob_i)', 'v(lo_q)', 'v(lob_q)', 'v(nb)', 'v(enb)', 'v(VDD)']
        for cell, inst in (('rx_lna', 'xlna'), ('rx_mix', 'xmi'), ('rx_mix', 'xmq')):
            sub = re.search(rf'(?ms)^\.subckt {cell} (.*?)$(.*?)^\.ends', pex(cell))
            nets = set()
            for ln in sub.group(2).splitlines():
                if ln.startswith('X'):
                    nets.update(x for x in ln.split()[1:5] if '=' not in x)
            sv += [f'v({inst}.{n})' for n in sorted(nets - set(sub.group(1).split()) - {'VSS', 'VDD'})]
    s = ' '.join(sv)
    interp = '' if save_lna else 'option interp\n'
    return swap_pex(f"""* overload phase 1 {corner} {level} dBm
{rxc.hdr(corner, pad=True)}{rx_top.block()}
VDD VDD 0 {vdd}
VSS VSS 0 0
Ven en 0 {vdd}
{body}.control
{interp}option temp=27
save {s}
tran {step} {tstop} 0 20p
set filetype=binary
write out.raw
.endc
.end
"""), sv


def ovl1(a):
    tag = f'ovl1_{rxc.CN[a.corner]}_{a.level:g}'
    deck, sv = ovl1_deck(a.corner, a.level, 12e-6)
    d, log, fl = run(tag, deck)
    r = dict(name=tag, level=a.level, flags=fl)
    try:
        pl = raw(d)
        t = pl['time']
        st = {k[2:-1]: float(pl[k][-1]) for k in pl if k.startswith('v(') and '.' in k}
        r['state'] = st
        r['t_end'] = float(t[-1])
        for arm in ('i', 'q'):
            x = pl[f'v(b{arm}_p)'] - pl[f'v(b{arm}_n)']
            c = dft(t, x, 100e3, 2e-6, 12e-6)
            r[f'mix_{arm}_amp_v'], r[f'mix_{arm}_ph'] = float(abs(c)), float(np.angle(c, deg=True))
            r[f'mix_{arm}_dc_v'] = float(np.mean(x[t > 2e-6]))
            r[f'mix_{arm}_cm_v'] = float(np.mean((pl[f'v(b{arm}_p)'] + pl[f'v(b{arm}_n)'])[t > 2e-6] / 2))
            r[f'{arm}_final'] = {n: float(pl[f'v({n})'][-1]) for n in (f'b{arm}_p', f'b{arm}_n', f'o{arm}_p', f'o{arm}_n')}
        r['inp_max'], r['inp_min'] = float(pl['v(inp)'].max()), float(pl['v(inp)'].min())
        r['idd_ma'] = float(-np.mean(pl['i(vdd)'][t > 2e-6]) * 1e3)
    except Exception as e:  # noqa: BLE001
        r['error'] = str(e)
    return finish(d, r)


def rate(a):
    """+6 dBm (or other) burst for 2 us: max |Vgs|, |Vgd|, |Vds|, |Vgb| of every LNA / mixer device (3.3 V devices)."""
    tag = f'rate_{rxc.CN[a.corner]}_{a.level:g}' + (f'_vdd{a.vdd:g}' if a.vdd != VDD else '')
    if a.analyse:
        d = OUT / tag
        fl = [w for w in BAD if w in (d / 'deck.log').read_text(errors='replace').lower()]
    else:
        deck, sv = ovl1_deck(a.corner, a.level, 2e-6, vdd=a.vdd, save_lna=True)
        d, log, fl = run(tag, deck)
    r = dict(name=tag, level=a.level, vdd=a.vdd, flags=fl, rating_v=RATING)
    try:
        pl = raw(d)
        t = pl['time']
        m = t > 0.2e-6
        devs = []
        for cell, inst in (('rx_lna', 'xlna'), ('rx_mix', 'xmi'), ('rx_mix', 'xmq')):
            sub = re.search(rf'(?ms)^\.subckt {cell} (.*?)$(.*?)^\.ends', pex(cell))
            ports = sub.group(1).split()
            outer = dict(zip(ports, dict(xlna='VDD VSS inp inn ri_p ri_n rq_p rq_n nb enb', xmi='VDD VSS ri_p ri_n bi_p bi_n lo_i lob_i',
                                         xmq='VDD VSS rq_p rq_n bq_p bq_n lo_q lob_q')[inst].split()))

            def v(n):
                n = outer.get(n, n)
                if n in ('VSS', '0'):
                    return np.zeros(m.sum())
                k = f'v({n})' if n in outer.values() or n == 'VDD' else f'v({inst}.{n})'
                return pl[k.lower()][m]
            for ln in sub.group(2).splitlines():
                if not ln.startswith('X') or 'fet_03v3' not in ln:
                    continue
                f = ln.split()
                dd, g, s, b = (v(x) for x in f[1:5])
                mx = dict(gs=np.max(np.abs(g - s)), gd=np.max(np.abs(g - dd)), ds=np.max(np.abs(dd - s)),
                          gb=np.max(np.abs(g - b)))
                k = max(mx, key=mx.get)
                devs.append((f'{inst}.{f[0]}', k, float(mx[k])))
        devs.sort(key=lambda x: -x[2])
        r['worst'] = devs[:10]
        r['n_devices'] = len(devs)
        r['n_over'] = sum(1 for x in devs if x[2] > RATING)
        r['inp_max'], r['inp_min'] = float(pl['v(inp)'][m].max()), float(pl['v(inp)'][m].min())
        r['pinp_max'], r['pinp_min'] = float(pl['v(pinp)'][m].max()), float(pl['v(pinp)'][m].min())
    except Exception as e:  # noqa: BLE001
        r['error'] = f'{type(e).__name__}: {e}'
    return finish(d, r)


def bbrec_deck(corner, st, src, tstop, en_step=None):
    """Extracted rx_bias + 2 x rx_bb + 2 x rx_lim; bi/bq from sources: cm + offset(t)/2 + signal; .ic from st."""
    lines = []
    for arm, ph0 in (('i', 0.0), ('q', -72.0)):
        amp = src[f'amp_{arm}']
        lines.append(f'B{arm}p b{arm}_p 0 V=v(cm{arm})+v(off{arm})/2+v(env)*{amp / 2}*cos(v(ph)+{np.deg2rad(ph0):.6f})\n'
                     f'B{arm}n b{arm}_n 0 V=v(cm{arm})-v(off{arm})/2-v(env)*{amp / 2}*cos(v(ph)+{np.deg2rad(ph0):.6f})\n'
                     f'voff{arm} off{arm} 0 pwl({src[f"offpwl_{arm}"]})\nvcm{arm} cm{arm} 0 pwl({src[f"cmpwl_{arm}"]})\n')
    en = f'pwl(0 0 {en_step} 0 {en_step + 1e-8} {VDD})' if en_step is not None else f'{VDD}'
    ic = ('.ic ' + ' '.join(f'v({k})={v:.6f}' for k, v in st.items()) + '\n') if st else ''
    return swap_pex(f"""* baseband recovery {corner}
{rxc.hdr(corner)}{rx_bias.block()}{rx_bb.block()}{rx_lim.block()}
VDD VDD 0 {VDD}
VSS VSS 0 0
Ven en 0 {en}
Xb VDD VSS en enb nb rx_bias
{''.join(lines)}vph ph 0 pwl({src['phpwl']})
venv env 0 pwl({src['envpwl']})
Xbbi VDD VSS bi_p bi_n oi_p oi_n nb enb rx_bb
Xbbq VDD VSS bq_p bq_n oq_p oq_n nb enb rx_bb
Xli VDD VSS oi_p oi_n q_i nb enb rx_lim
Xlq VDD VSS oq_p oq_n q_q nb enb rx_lim
{ic}.control
option temp=27
option interp
save v(q_i) v(q_q) v(oi_p) v(oi_n) v(oq_p) v(oq_n) v(xbbi.g2p) v(xbbi.g2n) v(xli.gcp) v(xli.gcn) v(bi_p) v(bi_n)
tran 20n {tstop} 0 20n
set filetype=binary
write out.raw v(q_i) v(q_q) v(oi_p) v(oi_n) v(oq_p) v(oq_n) v(xbbi.g2p) v(xbbi.g2n) v(xli.gcp) v(xli.gcn) v(bi_p) v(bi_n)
.endc
.end
""", ('rx_bias', 'rx_bb', 'rx_lim'))


def bbrec(a):
    """Phase 2. --from ovl1_<c>_<level>: the burst goes on (as its measured mixer-output tone) until --tburst, then
    -95 dBm FSK (amplitude and offset from the ovl1 -95 reference run). --from tile: rx_en rises at 5 us (TX -> RX
    turnaround), with the tile's mixer offset and common mode (sim/verify/tile_verify.py txrx_c_tt)."""
    rate_ = rx_chain.RATE
    ref = json.loads((OUT / f'ovl1_{rxc.CN[a.corner]}_-95' / 'result.json').read_text())
    tstop = a.tstop
    nb = int(tstop * rate_) + 2
    rng = np.random.default_rng(5)
    bits = rng.integers(0, 2, nb)
    if a.src == 'tile':
        tv = json.loads((REPO / 'build' / 'verify' / 'tile' / 'txrx_c_tt' / 'result.json').read_text())
        t_ev, t_fsk = 5e-6, 0.0
        st = None
        src = {}
        for arm in ('i', 'q'):
            b = f'b{arm}'
            src[f'cmpwl_{arm}'] = (f"0 {tv[f'{b}_cm_before']} {t_ev} {tv[f'{b}_cm_before']} {t_ev + 1e-6} "
                                   f"{tv[f'{b}_cm_after']}")
            # before rx_en the mixer output carries what the tile had with RX off; after, the tile's offset
            src[f'offpwl_{arm}'] = (f"0 {tv[f'{b}_off_mv_before'] * 1e-3} {t_ev} {tv[f'{b}_off_mv_before'] * 1e-3} "
                                    f"{t_ev + 50e-9} {tv[f'{b}_off_mv_after'] * 1e-3}")
            src[f'amp_{arm}'] = ref[f'mix_{arm}_amp_v']
        env = f'0 1 {tstop} 1'
        en_step = t_ev
        tag = f'bbrec_{rxc.CN[a.corner]}_txrx' + (f'_{a.mut}' if a.mut else '')
    else:
        s1 = json.loads((OUT / a.src / 'result.json').read_text())
        st = s1['state']
        tb = max(a.tburst - s1['t_end'], 0.0)       # the rest of the burst, after the phase-1 run
        t_ev, t_fsk = tb, tb
        if a.mut == 'burston':          # the burst never ends: the bits are sent from the same time, under the burst
            tb, t_ev = tstop + t_fsk + 1e-3, t_fsk
        src = {}
        for arm in ('i', 'q'):
            src[f'cmpwl_{arm}'] = (f"0 {s1[f'mix_{arm}_cm_v']} {max(tb, 1e-9)} {s1[f'mix_{arm}_cm_v']} "
                                   f"{max(tb, 1e-9) + 1e-6} {ref[f'mix_{arm}_cm_v']}")
            src[f'offpwl_{arm}'] = (f"0 {s1[f'mix_{arm}_dc_v']} {max(tb, 1e-9)} {s1[f'mix_{arm}_dc_v']} "
                                    f"{max(tb, 1e-9) + 50e-9} {ref[f'mix_{arm}_dc_v']}")
            src[f'amp_{arm}'] = ref[f'mix_{arm}_amp_v']
        k = s1['mix_i_amp_v'] / ref['mix_i_amp_v']          # the burst tone, relative to the -95 dBm signal
        env = f'0 {k} {max(tb, 1e-9)} {k} {max(tb, 1e-9) + 50e-9} 1 {tstop} 1'
        en_step = None
        tag = f'bbrec_{a.src[5:]}_{a.tburst * 1e3:g}ms' + (f'_{a.mut}' if a.mut else '')
    # phase: during the burst a steady +100 kHz rotation (the CW burst); from t_fsk CPFSK on `bits`
    pts, ph, tt = [(0.0, 0.0)], 0.0, 0.0
    if t_fsk > 0:
        ph = 2 * np.pi * 100e3 * t_fsk
        pts.append((t_fsk, ph))
    for kb, bt in enumerate(bits):
        ph += 2 * np.pi * (rx_chain.DEV if bt else -rx_chain.DEV) / rate_
        pts.append((t_fsk + (kb + 1) / rate_, ph))
    src['phpwl'] = ' '.join(f'{x:.9e} {y:.6f}' for x, y in pts)
    src['envpwl'] = env
    deck = bbrec_deck(a.corner, st, src, tstop + (t_fsk if a.src != 'tile' else 0), en_step)
    d, log, fl = run(tag, deck)
    r = dict(name=tag, src=a.src, tburst_ms=a.tburst * 1e3, mut=a.mut, flags=fl, t_event=t_ev, t_fsk=t_fsk)
    try:
        pl = raw(d)
        t = pl['time']
        rec = D.recovery(t, pl['v(q_i)'], pl['v(q_q)'], bits, t_fsk, rate_, t_ref=t_ev)
        r.update(rec)
        r['src_values'] = {k: v for k, v in src.items() if k not in ('phpwl',)}
    except Exception as e:  # noqa: BLE001
        r['error'] = f'{type(e).__name__}: {e}'
    return finish(d, r)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['mc', 'fsk', 'ovl1', 'rate', 'bbrec'])
    ap.add_argument('--corner', default='typical')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('--kind', default='pex', choices=['pex', 'sch'])
    ap.add_argument('--mut', default=None)
    ap.add_argument('--level', type=float, default=-95)
    ap.add_argument('--nf', type=float, default=None)
    ap.add_argument('--ndata', type=int, default=8)
    ap.add_argument('--vdd', type=float, default=VDD)
    ap.add_argument('--src', default='ovl1_tt_-10')
    ap.add_argument('--tburst', type=float, default=1e-3)
    ap.add_argument('--tstop', type=float, default=2.5e-3)
    ap.add_argument('--analyse', action='store_true', help='rate: re-analyse an existing run')
    ap.add_argument('--only', default=None, help='mc: redo only this part (cmp) of an existing sample')
    a = ap.parse_args()
    r = dict(mc=mc, fsk=fsk, ovl1=ovl1, rate=rate, bbrec=bbrec)[a.mode](a)
    sys.exit(1 if ('error' in r or r.get('flags')) else 0)


if __name__ == '__main__':
    main()
