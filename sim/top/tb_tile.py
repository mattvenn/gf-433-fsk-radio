#!/usr/bin/env python3
"""The whole extracted tile (layout/pex/tile_<c|rcx>.spice: the tile without the tx_fine macro, magic 8.3.642,
layout/gen/pex_tile.sh) in one deck: VCO, TX, RX, power-up, debug mux and supply benches.

    python3 sim/top/tb_tile.py list                       # every case name
    python3 sim/top/tb_tile.py run NAME [NAME ...]        # deck -> ngspice -> result.json in build/tile_sims/<NAME>/
    python3 sim/top/tb_tile.py analyse NAME               # re-analyse an existing run
Verdicts and the summary: sim/top/tb_tile_verdict.py. Jobs for sim/sched.py: sim/top/jobs_tile.py.

The deck (deck()):
- the tile's ports connected by name (ui_in[0] -> node ui_in0 ...); VGND is node 0, VAPWR -> vap, VDPWR -> vdp;
- supplies 'ideal' (two 3.3 V sources) or 'pg': each through one TT power switch (tt_pg_3v3_hp_2: pfet_03v3
  W 3357.5 um L 0.28, Ron 1.32 ohm tt, as sim/tx/tb_tx_top.py case pg) from an ideal chip supply. VDPWR has that
  switch on silicon; for VAPWR (the _pgvaa template) the same switch is ASSUMED;
- the macro's outputs from sources at VDPWR logic levels (src/tx_fine.v, active-low DAC lines, mdac_sim.word_bits:
  dac_tn[i] = segment i + 1, dac_bn[b] = binary bit b, dac_sdn = the sigma-delta cell); reset values: MED_INT 512,
  RX_EN 0, DBG_SEL 0 (docs/tx_fine_tune.md Table VI);
- the macro's input ck loaded by one gf180mcu_fd_sc_mcu7t5v0__dffq_1 clock pin on VDPWR (as sim/top/top_pex.py; the
  route to the macro pin is in the extraction, so no extra wire C);
- ua[0], ua[2], ua[3], ua[4], ua[5] each through pad_model_gf180 (rroute 40 ohm, n_off 3, sim/pad): ua[2] / ua[3]
  into the TX dipole (73 ohm + 100 pF, as tb_tx_top.py), ua[4] / ua[5] from the RX dipole (EMF source, 36.5 ohm per
  arm, as sim/rx/rx_chain.py front()), ua[0] to a probe (10 Mohm // 10 pF) or a source;
- uo_out[4] / uo_out[5] (q_i / q_q) loaded with 50 fF (TT's output mux, assumed); every other undriven port 1 Gohm
  to VGND (the macro's stubs carry only C).
Frequencies at mid-swing (the ring swings vg ... VDD, CLAUDE.md): a2 at (min + max) / 2 of the window.
"""
import argparse
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
sys.path.insert(0, str(REPO / 'tools'))
sys.path.insert(0, str(REPO / 'sim/tune'))
from rawread import read_raw  # noqa: E402
import mdac_sim as MS  # noqa: E402  (read-only: word_bits)

OUT = Path(os.environ.get('TILE_SIMS_OUT', REPO / 'build' / 'tile_sims'))   # (iq-symmetry runs: build/tile_sims_iq)
PDK = '/foss/pdks/gf180mcuD/libs.tech/ngspice'
STD = '/foss/pdks/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/spice/gf180mcu_fd_sc_mcu7t5v0.spice'
PEX = dict(c=REPO / 'layout/pex/tile_c.spice', rcx=REPO / 'layout/pex/tile_rcx.spice')
VDD = 3.3
FLO = 433.92e6
CODE = dict(typical=9, ss=11, ff=7, sf=9, fs=10)     # 433.92 MHz codes (docs/remap_results.md, Table VII)
VBNF0 = dict(typical=1.232, ss=1.384, ff=1.083, sf=1.232, fs=1.232)   # .ic hint (sim/ref/results.md)
CN = dict(typical='tt', ss='ss', ff='ff', sf='sf', fs='fs')
RDIP, CDIP = 73.0, 100e-12
VBNF_RX = dict(typical=1.23479, ss=1.38751, ff=1.08568)   # vbnf means of rxpre_c_* (free vbnf, 1.2-2 us)
# the receiver's first AC coupling per arm (rx_bb stage 1 -> stage 2): stage 1 is DC-coupled to the mixer, so the
# mixer's DC offset when the LO starts (about -3 mV, LO self-mixing) shifts these nodes, and the 8.5 kHz high-pass
# then takes 0.5-0.9 ms to settle (docs/rx_design.md). Found in tile_c.spice: the drains of the nfets gated by
# bi_* / bq_* that are also the source / drain / well of an L = 10 um pfet coupling cap (2026-11-17, after d606bd4).
S1_NODES = ('xtile.w_33972_51181#', 'xtile.w_28656_51181#', 'xtile.w_7081_50899#', 'xtile.w_1765_50899#')
SETTLE = S1_NODES + ('bi_p', 'bi_n', 'bq_p', 'bq_n')
VCO_TSTOP = 0.6e-6    # the tile's ring runs: f over the last 40 % (240 ns, ~90 periods)
RX_TSTOP = 14e-6      # 20 ps steps: 1.7-2.5 s per ns on the C-only tile with one thread
BAD = ('singular', 'timestep too small', 'transient op started', 'error', 'no such', 'unknown subckt', 'timeout')


def node(p):
    """Tile port -> testbench node name (no brackets)."""
    return {'VGND': '0', 'VAPWR': 'vap', 'VDPWR': 'vdp'}.get(p, re.sub(r'\[(\d+)\]', r'\1', p))


def ports(pex):
    txt = re.sub(r'\n\+', ' ', PEX[pex].read_text())
    m = re.search(r'^\.subckt (\S+) (.*)$', txt, re.M)
    return m.group(1), m.group(2).split()


# ------------------------------------------------------------------------------------------------ deck
DEF = dict(pex='c', corner='typical', temp=27, code=None, word=512, sd=0, rx_en=0, dbg=0, tx=0, supply='ideal',
           vap=VDD, vdp=VDD, tstop=1.2e-6, tstart=None, step=5e-12, ramp=None, rf=None, ua0='probe', ic='ring',
           save=None, ac=None, kind='ring', hold=None, settle=False, tskip=None, rsw=None, iinj=None, swap=None, rfdf=None, pre=None, mut=False, cadd=None)


def supplies(c):
    """Tile supply nodes vap / vdp. Sources vsa / vsd carry the tile's currents (i(vsa) < 0 when it draws)."""
    va, vd = c['vap'], c['vdp']
    if c['ramp']:
        tr = c['ramp']
        sa = f'PWL(0 0 {tr} {va})'
        sd = f'PWL(0 0 {tr} {vd})'
    else:
        sa, sd = f'{va}', f'{vd}'
    if c['ac']:                      # small-signal on one supply (AC analysis)
        sa += ' AC 1' if c['ac'] == 'vap' else ''
        sd += ' AC 1' if c['ac'] == 'vdp' else ''
    if c['supply'] == 'ideal':
        return f'vsa vap 0 {sa}\nvsd vdp 0 {sd}\n'
    if c['rsw'] is not None:         # a plain resistor for the switch (mutation / sensitivity)
        return (f'vsa vsa_n 0 {sa}\nRswa vsa_n vap {c["rsw"]}\n'
                f'vsd vsd_n 0 {sd}\nRswd vsd_n vdp {c["rsw"]}\n')
    # TT power switch tt_pg_3v3_hp_2 (pfet_03v3 W 3357.5 um = 395 x 8.5 um, L 0.28 um, gate at 0 V when on)
    return (f'vsa vsa_n 0 {sa}\nXpga vap 0 vsa_n vsa_n pfet_03v3 w=8.5u l=0.28u m=395\n'
            f'vsd vsd_n 0 {sd}\nXpgd vdp 0 vsd_n vsd_n pfet_03v3 w=8.5u l=0.28u m=395\n')


def logic(name, on, c, vsup='vdp'):
    """A VDPWR-level logic source (follows the supply ramp in power-up runs)."""
    if not on:
        return f'v{name} {name} 0 0\n'
    if c['ramp']:
        return f'v{name} {name} 0 PWL(0 0 {c["ramp"]} {c["vdp"]})\n'
    return f'v{name} {name} 0 {c["vdp"]}\n'


def stimuli(c):
    s = ''
    code = c['code'] if c['code'] is not None else CODE[c['corner']]
    for i in range(5):
        s += logic(f'ui_in{i}', (code >> i) & 1, c)
    s += logic('ui_in5', c['tx'], c) + logic('ui_in6', c['tx'], c)
    st = MS.word_bits(c['word'], c['sd'])
    for i in range(31):
        s += logic(f'dac_tn{i}', 1 - st[f's{i + 1}'], c)          # active low: on -> 0 V
    for b in range(5):
        s += logic(f'dac_bn{b}', 1 - st[f'b{b}'], c)
    s += logic('dac_sdn', 1 - st['sd'], c)
    s += logic('rx_en', c['rx_en'], c)
    for k in range(4):
        s += logic(f'dbg_sel{k}', (c['dbg'] >> k) & 1, c)
    return s


def rf_in(c):
    """RX dipole: EMF source (dp - dn) through 36.5 ohm per arm into the pads (rx_chain.front())."""
    if not c['rf']:
        src = 'Vsig dp dn 0\n'
    else:
        f, dbm = c['rf']
        emf = 2 * np.sqrt(2 * 73 * 1e-3 * 10 ** (dbm / 10))     # available power into a matched 73 ohm load
        src = f'Bsig dp dn V={emf:.6e}*sin(2*pi*{f:.3f}*time)\n'
    return src + 'Rsp dp pinp 36.5\nRsn dn pinn 36.5\nRdc dn 0 1e9\n'


def pad_ext():
    """pad_model_gf180 with its three supplies (VDDIO, VAPWR, VDPWR) as ports instead of fixed sources, for the
    power-up runs: there the pad ring ramps with the chip (fixed 3.3 V pad supplies against 0 V nodes at t = 0 stop
    the transient on 'timestep too small' at the pad's VDPWR source)."""
    txt = (REPO / 'sim/pad/pad_model_gf180.spice').read_text()
    sub = re.search(r'^\.subckt pad_model_gf180 .*?^\.ends', txt, re.S | re.M).group(0)
    sub = sub.replace('.subckt pad_model_gf180 VGND pin mod', '.subckt pad_model_ext VGND pin mod vddio vapwr vdpwr')
    sub = re.sub(r'^V(IO|AP|DP) .*\n', '', sub, flags=re.M)
    assert 'VIO' not in sub and 'pad_model_ext' in sub
    return sub + '\n'


def pads(c):
    vs = c['vap']
    if c['ramp']:                    # pad supplies = the chip supplies before the tile's switches (ramping)
        sa = 'vsa_n' if c['supply'] != 'ideal' else 'vap'
        sd = 'vsd_n' if c['supply'] != 'ideal' else 'vdp'
        pm = f'pad_model_ext rroute=40 n_off=3'
        con = f' {sa} {sa} {sd}'
        s = pad_ext()
    else:
        pm = f'pad_model_gf180 rroute=40 n_off=3 vsup={vs}'
        con = ''
        s = ''
    s += ''.join(f'Xpad{k} 0 pin{k} ua{k}{con} {pm}\n' for k in (0, 2, 3))
    s += f'Xpad4 0 pinp ua4{con} {pm}\nXpad5 0 pinn ua5{con} {pm}\n'
    # TX dipole on ua[3] (out_p) / ua[2] (out_n)
    s += f'Rdip pin3 dmid {RDIP}\nCdip dmid pin2 {CDIP}\n'
    s += rf_in(c)
    if c['ua0'] == 'probe':
        s += 'Rprb pin0 0 10meg\nCprb pin0 0 10p\n'
    elif isinstance(c['ua0'], (int, float)):
        s += f'vua0 pin0 0 {c["ua0"]}\n'
    return s


def tile_inst(c):
    name, ps = ports(c['pex'])
    conn = {p: node(p) for p in ps}
    if c['swap']:                    # mutation: two tile ports exchanged at the testbench
        a, b = c['swap']
        conn[a], conn[b] = conn[b], conn[a]
    driven = {'0', 'vap', 'vdp', 'ck', 'ua0', 'ua2', 'ua3', 'ua4', 'ua5', 'uo_out4', 'uo_out5'} \
        | {f'ui_in{i}' for i in range(7)} | {f'dac_tn{i}' for i in range(31)} | {f'dac_bn{b}' for b in range(5)} \
        | {'dac_sdn', 'rx_en'} | {f'dbg_sel{k}' for k in range(4)}
    ties = ''.join(f'Rtie_{node(p)} {node(p)} 0 1G\n' for p in ps if node(p) not in driven
                   and re.match(r'(clk|ena|rst_n|ua\d|ui_in\d|uio_\w+|uo_out\d)$', node(p)))
    return f'Xtile {" ".join(conn[p] for p in ps)} {name}\n.include {PEX[c["pex"]]}\n' + ties


SAVE = dict(
    ring='v(a2) v(ls) v(ck) v(lsq) v(vg) v(vbnf) v(vap) v(vdp) i(vsa) i(vsd)',
    tx='v(a2) v(ls) v(ck) v(vg) v(vbnf) v(vap) v(vdp) v(ua2) v(ua3) v(pin2) v(pin3) v(dmid) i(vsa) i(vsd)',
    rx='v(a2) v(ls) v(lsq) v(vg) v(vbnf) v(vap) v(lo_i) v(lo_q) v(oi_p) v(oi_n) v(oq_p) v(oq_n) v(bi_p) v(bi_n) '
       'v(bq_p) v(bq_n) v(uo_out4) v(uo_out5) v(nb) v(dp) v(pinp) i(vsa) i(vsd)',
    pwr='v(a2) v(ls) v(ck) v(vg) v(vbnf) v(vap) v(vdp) v(ua2) v(ua3) v(pin3) v(dmid) v(nb) v(lsq) v(lo_i) '
        'i(vsa) i(vsd)',
    dbg='v(ua0) v(pin0) v(oi_p) v(oq_p) v(nb) v(vctrl) v(ua1) v(a2) v(vbnf) i(vsa) i(vsd)',
)


def pre_result(name):
    """The RX pre-run's ring f and settled vg / vbnf (result.json)."""
    r = json.loads((OUT / name / 'result.json').read_text())
    assert 'error' not in r and r['f_a2'] == r['f_a2'], f'{name}: no usable result'
    return r


def deck(c):
    c = dict(DEF, **c)
    corner = c['corner']
    if c['rfdf']:                    # the tone at the pre-run's ring f + df; start from its settled bias
        pr = pre_result(c['pre'])
        c['rf'] = (pr['f_a2'] + c['rfdf'][0], c['rfdf'][1])
        c['ic'] = dict(a2=0, vg=round(pr['vg'], 5)) if c['hold'] is not None else \
            dict(a2=0, vbnf=round(pr['vbnf'], 5), vg=round(pr['vg'], 5))
        if pr.get('settle'):         # the high-pass starts settled: the stage-1 outputs and the mixer outputs at
            c['ic'].update({k: round(v, 6) for k, v in pr['settle'].items()})   # their running means (see S1_NODES)
    hdr = (f'.include {PDK}/design.ngspice\n.lib {PDK}/sm141064.ngspice {corner}\n'
           f'.lib {PDK}/sm141064.ngspice res_typical\n.lib {PDK}/sm141064.ngspice diode_typical\n'
           f'.include {STD}\n.include {REPO}/sim/pad/tt_asw_5v0.spice\n.include {REPO}/sim/pad/pad_model_gf180.spice\n')
    body = (supplies(c) + stimuli(c) + tile_inst(c) + pads(c)
            + 'XFF 0 ck ffq vdp vdp 0 0 gf180mcu_fd_sc_mcu7t5v0__dffq_1\n'
            + 'Cqi uo_out4 0 50f\nCqq uo_out5 0 50f\n')
    if c['hold'] is not None:       # vbnf held (the RX runs): the ring's f doesn't drift with the RC filter
        body += f'vhold vbnf 0 {c["hold"]}\n'
    if c['cadd']:                   # an extra capacitor node -> ground (the I/Q check's mutation: + C on a2)
        nd, cv = c['cadd']
        body += f'Cadd_{nd} {nd} 0 {cv:g}\n'
    if c['kind'] == 'dbg':          # a current into ua[1] (the ground-sense pin check)
        body += 'Iinj 0 ua1 0\n'
    ic = ''
    if c['ic'] == 'ring':
        ic = f'.ic v(a2)=0 v(vbnf)={VBNF0[corner]}\n' if c['hold'] is None else '.ic v(a2)=0\n'
    elif isinstance(c['ic'], dict):
        ic = '.ic ' + ' '.join(f'v({k})={v}' for k, v in c['ic'].items()) + '\n'
    save = c['save'] or SAVE['ring']
    if c['kind'] == 'dbg':
        ana, save_w = dbg_control(c), ''
        body += 'Iprb 0 pin0 0\nvfrc pinf 0 0\nRfrc pinf pin0 1e12\n'
        # markers: oi_p and oq_p sit at the same DC level; +-0.1 uA into their ~200 kOhm outputs moves them about
        # +-20 mV apart, so a reading can tell which one is on ua[0]
        body += 'Imki 0 oi_p 0.1u\nImkq oq_p 0 0.1u\n'
    elif c['ac']:
        ana = (f'op\nsave {save}\nac dec 10 1e4 3e9\n')
        save_w = ''
    elif c['tstop'] == 0:
        ana = f'op\nprint all > op.txt\n'
        save_w = ''
    else:
        tstart = c['tstart'] if c['tstart'] is not None else 0
        uic = ' uic' if c['ic'] == 'uic' else ''
        ana = f'save {save}\ntran {c["step"]} {c["tstop"]} {tstart} {c["step"]}{uic}\n'
        save_w = save
    return f"""* tb_tile {json.dumps({k: v for k, v in c.items() if v != DEF.get(k)})}
{hdr}{body}{ic}.control
option temp={c['temp']}
{ana}set filetype=binary
write out.raw {save_w}
quit
.endc
.end
"""


DBG_NODES = ('oi_p', 'oq_p', 'nb', 'vctrl')        # dbg_sel[k] -> its source node (layout/gen/tile_nets.py DBG)


def dbg_control(c):
    """Operating points: for each select k (and none), ua[0] read by the 10 Mohm probe, then loaded by 1 uA (path
    resistance and how much the reading pulls the source node); with no select, ua[0] forced to 0 / 3.3 V (off
    isolation: the source nodes must not move); select 3 with ua[0] forced to 1.65 V (the vctrl override);
    ua[1] with 1 mA injected (the ground-sense pin)."""
    vd = c['vdp']
    L = []

    def sel(k):
        return ''.join(f'alter vdbg_sel{j} dc={vd if j == k else 0}\n' for j in range(4))
    for k in (-1, 0, 1, 2, 3):
        for i in (0, 1e-6):
            L.append(sel(k) + f'alter Iprb dc={i}\nop\n'
                     f'echo DBG sel {k} iprb {i:g} $&v(pin0) $&v(ua0) $&v(oi_p) $&v(oq_p) $&v(nb) $&v(vctrl) $&v(ua1)\n')
    for k, vf in ((-1, 0.0), (-1, 3.3), (3, 1.65)):
        L.append(sel(k) + f'alter Iprb dc=0\nalter vfrc dc={vf}\nalter Rfrc 1e-3\nop\n'
                 f'echo FRC sel {k} vf {vf} $&v(pin0) $&v(ua0) $&v(oi_p) $&v(oq_p) $&v(nb) $&v(vctrl) $&v(ua1)\n'
                 'alter Rfrc 1e12\n')
    L.append(sel(-1) + 'alter Iinj dc=1e-3\nop\necho UA1 $&v(ua1)\nalter Iinj dc=0\n')
    return ''.join(L)


# ------------------------------------------------------------------------------------------------ cases
def cases():
    """name -> dict(kind, est (s), threads, case parameters)."""
    C = {}

    def add(name, kind, est, **kw):
        C[name] = dict(kind=kind, est=est, **kw)
    # 1. VCO on the tile: f per code / word, tile against the vco_top references (tb_tile_ref.py)
    for corner in ('typical', 'ss', 'ff', 'sf', 'fs'):
        cd = CODE[corner]
        for word in ((0, 512, 1023) if corner in ('typical', 'ss', 'ff') else (512,)):
            add(f'vco_c_{CN[corner]}_k{cd}_w{word}', 'ring', 1800, pex='c', corner=corner, code=cd, word=word,
                tstop=VCO_TSTOP)
    for cd in (0, 8, 10, 31):
        add(f'vco_c_tt_k{cd}_w512', 'ring', 1800, pex='c', code=cd, tstop=VCO_TSTOP)
    # sf: the a2 load slows the ring most there (slow NMOS): is 433.92 MHz still in reach at higher codes?
    for cd in (15, 23, 31):
        add(f'vco_c_sf_k{cd}_w512', 'ring', 2000, pex='c', corner='sf', code=cd, tstop=VCO_TSTOP)
    add('vco_c_tt_k9_w512_rx', 'ring', 1800, pex='c', code=9, rx_en=1, tstop=VCO_TSTOP)
    add('vco_rcx_tt_k9_w512', 'ring', 6 * 3600, pex='rcx', code=9, tstop=300e-9)   # rcx: ~60 s of CPU per ns
    # 2. TX into the dipole, behind the power switches
    for corner in ('typical', 'ss', 'ff', 'sf', 'fs'):
        add(f'tx_c_{CN[corner]}_on', 'tx', 2400, corner=corner, tx=1, supply='pg', save=SAVE['tx'])
    add('tx_c_tt_off', 'tx', 2400, tx=0, supply='pg', save=SAVE['tx'])
    # (tx_rcx_tt_on dropped: ~70 s of CPU per ns; the tx_drv block's rcx / c difference is 0.15 dB, block_pex.txt)
    # the tile's ring is about 12 % slow, so code 9 runs at 370 MHz; code 13 brings it near 434 MHz
    add('tx_c_tt_on_k13', 'tx', 4000, tx=1, code=13, supply='pg', save=SAVE['tx'])
    add('tx_c_tt_on_ideal', 'tx', 2400, tx=1, supply='ideal', save=SAVE['tx'])
    # 3. RX: a pre-run with the receiver on (the ring's own f and its settled vg / vbnf), then a CW tone at
    #    f + df at the dipole; the I / Q baseband and the limiter outputs
    #    First try (rxpre_c_*, rx_c_tt_-70_p): vbnf free, from its .ic hint; it was still settling (1 Mohm / 20 pF),
    #    the ring ran 0.96 MHz lower in the RX run than in the pre-run and the tone fell outside the baseband.
    #    Now (rxh): vbnf held by a source at the free pre-run's mean in both runs (as sim/tune/phase_c.py does), so
    #    the ring's f is the same in both.
    for corner in ('typical', 'ss', 'ff'):
        add(f'rxpre_c_{CN[corner]}', 'ring', 2400, corner=corner, rx_en=1, step=20e-12, tstop=2e-6,
            save=SAVE['ring'] + ' v(lo_i) v(lo_q) v(nb)')
        add(f'rxhpre_c_{CN[corner]}', 'ring', 3500, corner=corner, rx_en=1, step=20e-12, tstop=1.2e-6,
            hold=VBNF_RX[corner], save=SAVE['ring'] + ' v(lo_i) v(lo_q) v(nb)')
    add('rx_c_tt_-70_p', 'rx', 3 * 3600, rx_en=1, step=20e-12, tstop=RX_TSTOP, rfdf=(200e3, -70), pre='rxpre_c_tt',
        save=SAVE['rx'], threads=3)
    for corner, df, dbm in (('typical', 200e3, -70), ('typical', -200e3, -70), ('typical', 200e3, -95),
                            ('ss', 200e3, -70), ('ff', 200e3, -70)):
        add(f'rxh_c_{CN[corner]}_{dbm:+d}_{"p" if df > 0 else "n"}', 'rx', 3 * 3600, corner=corner, rx_en=1,
            step=20e-12, tstop=RX_TSTOP, rfdf=(df, dbm), pre=f'rxhpre_c_{CN[corner]}', hold=VBNF_RX[corner],
            save=SAVE['rx'], threads=3)
    # 4. power-up: VAPWR and VDPWR 0 -> 3.3 V in 10 us through the switches, every node at 0 V (uic), macro
    #    lines at their reset values (they follow VDPWR), TX off, RX off
    # (ideal ramped supplies, as sim/top/top_pex.py startup: behind the TT switch (gate at 0 V) the tile floats near
    # 0 V until the chip supply passes the PFET's threshold and the transient stops on 'timestep too small')
    add('pwrup_c_tt', 'pwr', 4 * 3600, rev=2, supply='ideal', ramp=10e-6, ic='uic', step=20e-12, tstop=25e-6, save=SAVE['pwr'])
    # 5. debug mux (operating points, rx_en = 1): each select onto ua[0]; ua[1]
    # (an rcx copy, dbg_rcx_tt, was stopped after 97 min of operating points: the ~34 000 wire resistors make each op
    # slow; the mux's on-resistance is 0.9-1.6 kohm, so the wire R doesn't matter there)
    add('dbg_c_tt', 'dbg', 1800, pex='c', rx_en=1, ic=None)
    # 6. supply: VCO at 3.3 V -/+ 4.5 % (both supplies), the AC impedance at the VAPWR / VDPWR ports
    for v in (3.15, 3.45):
        add(f'vco_c_tt_k9_w512_v{v:.2f}', 'ring', 1800, vap=v, vdp=v, tstop=VCO_TSTOP)
    for sup in ('vap', 'vdp'):
        add(f'zac_c_tt_{sup}', 'zac', 600, ac=sup, ic=None, save=f'i(vs{sup[1]})')
    # after d606bd4 (supply straps over the TX driver's and LNA's rails), re-extracted: the VCO at tt / ss / ff
    for corner in ('typical', 'ss', 'ff'):
        add(f'vco2_c_{CN[corner]}_k{CODE[corner]}_w512', 'ring', 1800, corner=corner, code=CODE[corner], tstop=VCO_TSTOP)
    # after fca76de (TX VDPWR strap 8.5 um; tile_*.spice re-extracted, commit 244147a): VCO and TX again; the rcx TX
    # run puts the supply-grid resistance in the loop (the C-only netlist has none)
    for corner in ('typical', 'ss', 'ff'):
        add(f'vco3_c_{CN[corner]}_k{CODE[corner]}_w512', 'ring', 1800, corner=corner, code=CODE[corner], tstop=VCO_TSTOP)
        add(f'tx3_c_{CN[corner]}_on', 'tx', 3000, corner=corner, tx=1, supply='pg', save=SAVE['tx'])
    add('tx3_c_tt_on_k13', 'tx', 3000, tx=1, code=13, supply='pg', save=SAVE['tx'])
    add('tx3_rcx_tt_on_k13', 'tx', 4 * 3600, rev=1, pex='rcx', tx=1, code=13, supply='pg', tstop=150e-9, save=SAVE['tx'],
        threads=4)
    # RX, settled: a pre-run with the LO running and no RF gives the stage-1 / mixer running means (SETTLE), the
    # RX runs start from them, so the 8.5 kHz high-pass starts in its steady state
    sv = SAVE['ring'] + ' v(lo_i) v(lo_q) v(nb) ' + ' '.join(f'v({k})' for k in SETTLE)
    add('rxset_c_tt', 'ring', 3000, rx_en=1, step=20e-12, tstop=3e-6, hold=VBNF_RX['typical'], settle=True,
        save=sv, threads=4)
    for dbm in (-70, -90, -95, -100):
        add(f'rxs_c_tt_{dbm:+d}_p', 'rx', 4 * 3600, rx_en=1, step=20e-12, tstop=22e-6, tskip=6e-6, rfdf=(200e3, dbm),
            pre='rxset_c_tt', hold=VBNF_RX['typical'], save=SAVE['rx'] + ' ' + ' '.join(f'v({k})' for k in S1_NODES),
            threads=4)
    # iq-symmetry (2026-11-19, the Q level shifter inside vco_core): the I/Q LO phase on the tile, receiver on, vbnf
    # held, at the 433.92 MHz code of each corner; and its mutation, + 16.6 fF on a2 (the a2 load of the old layout)
    for corner in ('typical', 'ss', 'ff'):
        add(f'iq_c_{CN[corner]}', 'ring', 1500, corner=corner, rx_en=1, step=20e-12, tstop=1.2e-6, hold=VBNF_RX[corner],
            save=SAVE['ring'] + ' v(lo_i) v(lo_q) v(nb) v(a0)')
    add('mut_iq_a2c', 'ring', 1500, rx_en=1, step=20e-12, tstop=1.2e-6, hold=VBNF_RX['typical'], cadd=('a2', 16.6e-15),
        save=SAVE['ring'] + ' v(lo_i) v(lo_q) v(nb) v(a0)', mut=True)
    # mutations: the checks must fail on these
    add('mut_dbg_swap01', 'dbg', 1800, rx_en=1, ic=None, swap=('dbg_sel[0]', 'dbg_sel[1]'), mut=True)
    add('mut_dbg_c_rxoff', 'dbg', 1800, rx_en=0, ic=None, mut=True)                     # receiver bias off
    add('mut_vco_code', 'ring', 1800, code=9, swap=('ui_in[0]', 'ui_in[1]'), mut=True, tstop=VCO_TSTOP)  # code bits 0 / 1 swapped
    add('mut_tx_noen', 'tx', 2400, tx=0, supply='pg', save=SAVE['tx'], mut=True)          # TX enable dropped
    add('mut_tx_rsw10', 'tx', 2400, tx=1, supply='pg', rsw=10.0, save=SAVE['tx'], mut=True)  # weak supply
    add('mut_rx_off', 'rx', 2 * 3600, rx_en=0, step=20e-12, tstop=9e-6, threads=3, rfdf=(200e3, -70), pre='rxhpre_c_tt',
        hold=VBNF_RX['typical'],
        save=SAVE['rx'], mut=True)                                                           # receiver not enabled
    add('mut_pwrup_txon', 'pwr', 2 * 3600, rev=3, supply='ideal', ramp=10e-6, ic='uic', step=20e-12, tstop=12e-6, tx=1,
        save=SAVE['pwr'], mut=True)                                                          # TX on at power-up
    return C


# ------------------------------------------------------------------------------------------------ run
def run(name):
    c = cases()[name]
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    (d / '.spiceinit').write_text(f'set ng_nomodcheck\nset num_threads={c.get("threads", 1)}\noption noinit\n')
    (d / 'deck.cir').write_text(deck({k: v for k, v in c.items() if k not in ('est', 'threads', 'rev')}))
    (d / 'out.raw').unlink(missing_ok=True)
    (d / 'result.json').unlink(missing_ok=True)
    t = time.time()
    subprocess.run(['bash', '-c', f'cd {d} && nice -n 5 ngspice -b deck.cir > deck.log 2>&1'], check=False)
    (d / 'runtime.txt').write_text(f'{time.time() - t:.0f}\n')
    r = analyse(name)
    print(json.dumps(r, indent=1))
    return r


def log_flags(d):
    lg = (d / 'deck.log').read_text(errors='replace').lower() if (d / 'deck.log').exists() else 'missing'
    return [w for w in BAD if w in lg]


def xings(t, v, th, rising=True):
    a, b = v[:-1] - th, v[1:] - th
    i = np.where((a < 0) & (b >= 0))[0] if rising else np.where((a > 0) & (b <= 0))[0]
    return t[i] + (th - v[i]) * (t[i + 1] - t[i]) / (v[i + 1] - v[i])


def freq(t, v, th):
    r = xings(t, v, th)
    return (len(r) - 1) / (r[-1] - r[0]) if len(r) > 2 else float('nan')


def duty(t, v, th):
    r, f = xings(t, v, th), xings(t, v, th, False)
    d = [(f[(f > r[i]) & (f < r[i + 1])][0] - r[i]) / (r[i + 1] - r[i]) for i in range(len(r) - 1)
         if ((f > r[i]) & (f < r[i + 1])).any()]
    return float(np.mean(d)) if d else float('nan')


def mean(t, y):
    return float(np.trapezoid(y, t) / (t[-1] - t[0]))


def fund(t, y, f, t0, t1):
    """Amplitude and phase (deg) of the f component of y over whole periods in [t0, t1]."""
    n = int((t1 - t0) * f)
    t1 = t0 + n / f
    tu = np.linspace(t0, t1, max(n, 1) * 200, endpoint=False)
    c = 2 * np.mean(np.interp(tu, t, y) * np.exp(-2j * np.pi * f * tu))
    return abs(c), float(np.angle(c, deg=True))


def ring_meas(t, pl, vsup=VDD):
    """f at a2 (mid-swing), ls / ck / lsq, the ring's swing and the divider ratio over the given window."""
    a2 = pl['v(a2)']
    lo, hi = float(a2.min()), float(a2.max())
    r = dict(f_a2=freq(t, a2, (lo + hi) / 2), a2_min=lo, a2_max=hi)
    if 'v(ls)' in pl:
        r['f_ls'] = freq(t, pl['v(ls)'], vsup / 2)
        r['ls_duty'] = duty(t, pl['v(ls)'], vsup / 2)
        r['ls_min'], r['ls_max'] = float(pl['v(ls)'].min()), float(pl['v(ls)'].max())
    if 'v(ck)' in pl:
        r['f_ck'] = freq(t, pl['v(ck)'], vsup / 2)
        r['div'] = r['f_a2'] / r['f_ck'] if r['f_ck'] > 0 else float('nan')
    if 'v(lsq)' in pl:
        r['f_lsq'] = freq(t, pl['v(lsq)'], vsup / 2)
    h = (t[0] + t[-1]) / 2
    f1 = freq(t[t < h], a2[t < h], (lo + hi) / 2)
    f2 = freq(t[t >= h], a2[t >= h], (lo + hi) / 2)
    r['f_drift'] = f2 / f1 - 1
    # a2 -> ls phase (fraction of a period): checks that ls is the a0 tap's level shift, not a2
    if 'v(ls)' in pl:
        ra, rl = xings(t, a2, (lo + hi) / 2), xings(t, pl['v(ls)'], vsup / 2)
        per = 1 / r['f_a2']
        ph = [((rl[rl > x][0] - x) / per) % 1 for x in ra[:-2] if (rl > x).any()]
        r['a2_to_ls'] = float(np.median(ph)) if ph else float('nan')
    # I/Q LO phase (Q's lag behind I, deg of the LO period, rising edges at mid-supply): at the mixers' LO inputs
    # (lo_i / lo_q, the LO buffers on) and at the level-shifter outputs (ls / lsq)
    per = 1 / r['f_a2'] if r['f_a2'] == r['f_a2'] and r['f_a2'] > 0 else float('nan')
    for a, b, k in (('lo_i', 'lo_q', 'lo_iq_phase'), ('ls', 'lsq', 'ls_lsq_phase')):
        if f'v({a})' in pl and f'v({b})' in pl and per == per:
            ri, rq = xings(t, pl[f'v({a})'], vsup / 2), xings(t, pl[f'v({b})'], vsup / 2)
            ph = [((rq[rq > x][0] - x) / per * 360) % 360 for x in ri[:-2] if (rq > x).any()]
            r[k] = float(np.median(ph)) if ph else float('nan')
            r[k + '_spread'] = float(np.ptp(ph)) if ph else float('nan')
    if 'v(a0)' in pl and per == per:                 # the ring's own a0 -> a2 delay (two stages: about 144 deg)
        a0 = pl['v(a0)']
        r0, r2 = xings(t, a0, (a0.min() + a0.max()) / 2), xings(t, a2, (lo + hi) / 2)
        ph = [((r2[r2 > x][0] - x) / per * 360) % 360 for x in r0[:-2] if (r2 > x).any()]
        r['a0_a2_phase'] = float(np.median(ph)) if ph else float('nan')
    for k in ('vg', 'vbnf', 'vap', 'vdp'):
        if f'v({k})' in pl:
            r[k] = mean(t, pl[f'v({k})'])
    r['i_vap_ma'] = -mean(t, pl['i(vsa)']) * 1e3
    r['i_vdp_ma'] = -mean(t, pl['i(vsd)']) * 1e3
    return r


def analyse(name):
    c = dict(DEF, **cases()[name])
    d = OUT / name
    r = dict(name=name, flags=log_flags(d), case={k: v for k, v in cases()[name].items()})
    if (d / 'runtime.txt').exists():
        r['runtime_s'] = float((d / 'runtime.txt').read_text())
    if c['kind'] == 'dbg':
        log = (d / 'deck.log').read_text(errors='replace') if (d / 'deck.log').exists() else ''
        try:
            r.update(an_dbg(None, c, log))
        except Exception as e:  # noqa: BLE001
            r['error'] = f'analysis: {type(e).__name__}: {e}'
        (d / 'result.json').write_text(json.dumps(r, indent=1, default=float))
        return r
    try:
        pl = read_raw(d / 'out.raw')[0]['vars']
    except Exception as e:  # noqa: BLE001
        r['error'] = f'no raw: {e}'
        (d / 'result.json').write_text(json.dumps(r, indent=1))
        return r
    try:
        r.update(KIND[c['kind']](pl, c))
    except Exception as e:  # noqa: BLE001
        r['error'] = f'analysis: {type(e).__name__}: {e}'
    (d / 'result.json').write_text(json.dumps(r, indent=1, default=float))
    return r


def analyse_with(name, **over):
    """Re-analyse a finished run with changed analysis settings (analysis-level mutations); nothing is written."""
    c = dict(DEF, **cases()[name], **over)
    d = OUT / name
    r = dict(name=f'{name} {over}', flags=log_flags(d))
    try:
        r.update(KIND[c['kind']](read_raw(d / 'out.raw')[0]['vars'], c))
    except Exception as e:  # noqa: BLE001
        r['error'] = f'{type(e).__name__}: {e}'
    return r


def an_ring(pl, c):
    t = pl['time']
    m = t >= 0.6 * t[-1]
    r = ring_meas(t[m], {k: v[m] for k, v in pl.items()})
    if c.get('settle'):              # running means over the last 1 us (rxset: presets for the settled RX runs)
        m1 = t >= t[-1] - 1e-6
        r['settle'] = {k: mean(t[m1], pl[f'v({k})'][m1]) for k in SETTLE}
        r['settle_t0'] = {k: float(pl[f'v({k})'][0]) for k in SETTLE}
        m2 = (t >= t[-1] - 2e-6) & (t < t[-1] - 1e-6)
        r['settle_drift_mv'] = {k: (r['settle'][k] - mean(t[m2], pl[f'v({k})'][m2])) * 1e3 for k in SETTLE}
    return r


def an_tx(pl, c):
    t = pl['time']
    m = t >= 0.6 * t[-1]
    tm = t[m]
    p = {k: v[m] for k, v in pl.items()}
    r = ring_meas(tm, p)
    vr = p['v(pin3)'] - p['v(dmid)']                    # the 73 ohm part of the dipole
    r['p_dip_dbm'] = float(10 * np.log10(max(mean(tm, vr ** 2) / RDIP, 1e-21) / 1e-3))
    f = r['f_a2']
    if f == f:
        a1, _ = fund(tm, vr, f, tm[0], tm[-1])
        r['p1_dbm'] = float(10 * np.log10(max(a1 ** 2 / (2 * RDIP), 1e-21) / 1e-3))
        _, php = fund(tm, p['v(ua3)'], f, tm[0], tm[-1])
        _, phn = fund(tm, p['v(ua2)'], f, tm[0], tm[-1])
        r['ph_err_deg'] = float((php - phn) % 360 - 180)
    for k in ('ua2', 'ua3', 'pin2', 'pin3'):
        r[f'{k}_pp'] = float(np.ptp(p[f'v({k})']))
    r['vap_ripple_mv'] = float(np.ptp(p['v(vap)']) * 1e3)
    r['vdp_ripple_mv'] = float(np.ptp(p['v(vdp)']) * 1e3)
    r['i_vdp_rms_ma'] = float(np.sqrt(mean(tm, p['i(vsd)'] ** 2)) * 1e3)
    return r


def dft(t, y, f, t0):
    """Complex amplitude of the f component of y over whole periods after t0."""
    m = t >= t0
    n = int((t[m][-1] - t0) * f)
    if n < 1:
        return 0j
    tu = np.linspace(t0, t0 + n / f, n * 256, endpoint=False)
    return 2 * np.mean(np.interp(tu, t, y) * np.exp(-2j * np.pi * f * tu))


RX_TSKIP = 5e-6


def an_rx(pl, c):
    t = pl['time']
    tskip = c.get('tskip') or RX_TSKIP
    m = t >= tskip
    p = {k: v[m] for k, v in pl.items()}
    tm = t[m]
    r = ring_meas(tm, {k: p[k] for k in ('v(a2)', 'v(ls)', 'v(lsq)', 'v(vg)', 'v(vbnf)', 'v(vap)', 'i(vsa)', 'i(vsd)')})
    pr = pre_result(c['pre'])
    r['f_pre'] = pr['f_a2']
    r['f_tone'] = pr['f_a2'] + c['rfdf'][0]
    r['df_set'] = c['rfdf'][0]
    r['level_dbm'] = c['rfdf'][1]
    oi = pl['v(oi_p)'] - pl['v(oi_n)']
    oq = pl['v(oq_p)'] - pl['v(oq_n)']
    bi = pl['v(bi_p)'] - pl['v(bi_n)']
    # the actual baseband tone (the ring's f in this run may differ from the pre-run's): the DFT peak of the I output
    fr = np.arange(20e3, 1.0e6, 5e3)
    amp = [abs(dft(t, oi, x, tskip)) for x in fr]
    fb = float(fr[int(np.argmax(amp))])
    r['f_bb_peak'] = fb                 # information only: 9 us of window gives ~110 kHz of DFT resolution
    r['f_bb_expect'] = abs(r['f_tone'] - r['f_a2'])
    fb = r['f_bb'] = r['f_bb_expect']   # the DFT and the phase at the known offset (tone - this run's ring f)
    ci, cq, cb = dft(t, oi, fb, tskip), dft(t, oq, fb, tskip), dft(t, bi, fb, tskip)
    r['bb_i_v'], r['bb_q_v'], r['mix_i_v'] = float(abs(ci)), float(abs(cq)), float(abs(cb))
    r['bb_iq_phase'] = float(np.angle(cq / ci, deg=True)) if abs(ci) > 0 else float('nan')
    # limiter outputs: toggles, frequency, Q relative to I (deg of the baseband period)
    th = VDD / 2
    qi, qq = p['v(uo_out4)'], p['v(uo_out5)']
    if c.get('swap_out'):                  # analysis mutation: q_i and q_q exchanged
        qi, qq = qq, qi
    ri, rq = xings(tm, qi, th), xings(tm, qq, th)
    ai = np.sort(np.concatenate([ri, xings(tm, qi, th, False)]))      # every edge, rising and falling
    aq = np.sort(np.concatenate([rq, xings(tm, qq, th, False)]))
    r['qi_edges'], r['qq_edges'] = int(len(ai)), int(len(aq))
    r['f_qi'] = (len(ai) - 1) / (2 * (ai[-1] - ai[0])) if len(ai) > 2 else float('nan')
    r['f_qq'] = (len(aq) - 1) / (2 * (aq[-1] - aq[0])) if len(aq) > 2 else float('nan')
    r['qi_duty'] = duty(tm, qi, th)
    # Q's lead over I (deg of the baseband period), the same sign convention as bb_iq_phase (angle of cq / ci):
    # for each rising edge of q_i, the nearest rising edge of q_q
    ph = []
    for x in ri:
        if len(rq):
            d = rq[np.argmin(abs(rq - x))] - x
            ph.append(-d * fb * 360)
    ph = [((v + 180) % 360) - 180 for v in ph]
    r['q_iq_phase'] = float(np.median(ph)) if ph else float('nan')
    # the baseband's DC offset over the window (the 8.5 kHz high-pass still settling from the LO's start)
    r['oi_mean'], r['oq_mean'] = mean(tm, oi[m]), mean(tm, oq[m])
    h = (tm[0] + tm[-1]) / 2                         # drift of the baseband DC across the window
    r['oi_mean_1'], r['oi_mean_2'] = mean(tm[tm < h], oi[m][tm < h]), mean(tm[tm >= h], oi[m][tm >= h])
    r['tskip'] = tskip
    r['mix_i_mean_mv'] = mean(tm, bi[m]) * 1e3
    r['qi_min'], r['qi_max'] = float(qi.min()), float(qi.max())
    # LO: I / Q phase at the mixers (deg of the LO period), duty
    rli, rlq = xings(tm, p['v(lo_i)'], th), xings(tm, p['v(lo_q)'], th)
    per = 1 / r['f_a2']
    lph = [((rlq[rlq > x][0] - x) / per * 360) % 360 for x in rli[:-2] if (rlq > x).any()]
    r['lo_iq_phase'] = float(np.median(lph)) if lph else float('nan')
    r['lo_i_duty'] = duty(tm, p['v(lo_i)'], th)
    r['nb'] = mean(tm, p['v(nb)'])
    return r


def an_pwr(pl, c):
    t = pl['time']
    win = []
    for t0 in np.arange(0, t[-1] - 0.999e-6, 1e-6):
        m = (t >= t0) & (t < t0 + 1e-6)
        if m.sum() < 20:
            continue
        tm = t[m]
        a, ck, vap = pl['v(a2)'][m], pl['v(ck)'][m], float(pl['v(vap)'][m].mean())
        sw = float(a.max() - a.min())
        w = dict(t0=float(t0), vap=vap, vdp=float(pl['v(vdp)'][m].mean()), a2_swing=sw,
                 f_a2=freq(tm, a, (a.min() + a.max()) / 2) if sw > 0.3 else float('nan'),
                 f_ck=freq(tm, ck, vap / 2) if np.ptp(ck) > 0.5 * vap else float('nan'),
                 vbnf=float(pl['v(vbnf)'][m].mean()), vg=float(pl['v(vg)'][m].mean()),
                 nb=float(pl['v(nb)'][m].mean()),
                 ua2_pp=float(np.ptp(pl['v(ua2)'][m])), ua3_pp=float(np.ptp(pl['v(ua3)'][m])),
                 dip_pp=float(np.ptp(pl['v(pin3)'][m] - pl['v(dmid)'][m])),
                 lsq_pp=float(np.ptp(pl['v(lsq)'][m])), lo_i_pp=float(np.ptp(pl['v(lo_i)'][m])),
                 i_vap_ma=-mean(tm, pl['i(vsa)'][m]) * 1e3, i_vdp_ma=-mean(tm, pl['i(vsd)'][m]) * 1e3)
        win.append(w)
    r = dict(windows=win)
    ok = [w for w in win if w['a2_swing'] > 0.5 and w['f_a2'] == w['f_a2']]
    r['t_osc_us'] = ok[0]['t0'] * 1e6 if ok else None
    last = win[-1]
    r.update(f_end=last['f_a2'], f_ck_end=last['f_ck'], vbnf_end=last['vbnf'], vg_end=last['vg'],
             i_vap_end_ma=last['i_vap_ma'], i_vdp_end_ma=last['i_vdp_ma'],
             ua_tx_pp_max=max(max(w['ua2_pp'], w['ua3_pp']) for w in win),
             dip_pp_max=max(w['dip_pp'] for w in win),
             i_vap_peak_ma=float(-pl['i(vsa)'].min() * 1e3), i_vdp_peak_ma=float(-pl['i(vsd)'].min() * 1e3))
    return r


def an_dbg(pl, c, log):
    cols = ('pin0', 'ua0') + DBG_NODES + ('ua1',)
    rows = {}
    for m in re.finditer(r'^DBG sel (\S+) iprb (\S+) (.*)$', log, re.M):
        rows[f'sel{m.group(1)}_i{m.group(2)}'] = dict(zip(cols, [float(x) for x in m.group(3).split()]))
    for m in re.finditer(r'^FRC sel (\S+) vf (\S+) (.*)$', log, re.M):
        rows[f'frc_sel{m.group(1)}_v{float(m.group(2)):g}'] = dict(zip(cols, [float(x) for x in m.group(3).split()]))
    m = re.search(r'^UA1 (\S+)', log, re.M)
    r = dict(ops=rows, ua1_1ma=float(m.group(1)) if m else None)
    sel = {}
    for k, n in enumerate(DBG_NODES):
        a, b = rows.get(f'sel{k}_i0'), rows.get(f'sel{k}_i1e-06')
        if not a or not b:
            continue
        n0 = rows.get('sel-1_i0', a)
        sel[n] = dict(node=a[n], pin=a['pin0'], err_mv=(a['pin0'] - a[n]) * 1e3,
                      probe_shift_mv=(a[n] - n0[n]) * 1e3,                            # the 10 Mohm probe's load
                      others={m: a[m] for m in DBG_NODES if m != n},
                      r_out_ohm=(b['pin0'] - a['pin0']) / 1e-6,                       # seen at the board pin
                      r_switch_ohm=((b['pin0'] - b[n]) - (a['pin0'] - a[n])) / 1e-6,  # pin -> node (switch + pad)
                      node_pull_mv_per_ua=(b[n] - a[n]) * 1e3)
    r['sel'] = sel
    a, b = rows.get('frc_sel-1_v0'), rows.get('frc_sel-1_v3.3')
    if a and b:
        r['off_shift_mv'] = {n: (b[n] - a[n]) * 1e3 for n in DBG_NODES}
    f = rows.get('frc_sel3_v1.65')
    if f:
        r['vctrl_override'] = f['vctrl']
    n0 = rows.get('sel-1_i0')
    if n0:
        r['none_pin0'] = n0['pin0']
        r['ua1'] = n0['ua1']
    return r


def an_zac(pl, c):
    f = np.real(pl['frequency'])
    i = pl[f'i(vs{c["ac"][1]})']
    z = 1 / np.abs(i)
    r = dict(f=[float(x) for x in f], z=[float(x) for x in z])
    for fx in (1e5, 1e6, 1e7, 2.5e7, 1e8, 4.34e8):
        k = int(np.argmin(abs(f - fx)))
        r[f'z_{fx:g}'] = float(z[k])
        r[f'c_eff_pf_{fx:g}'] = float(abs(np.imag(i[k])) / (2 * np.pi * f[k]) * 1e12)
    return r


KIND = dict(ring=an_ring, tx=an_tx, rx=an_rx, pwr=an_pwr, zac=an_zac)



def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('what', choices=['list', 'run', 'analyse', 'deck'])
    ap.add_argument('names', nargs='*')
    ap.add_argument('--rev', default='0', help='job revision (the scheduler re-runs a failed job when it changes)')
    a = ap.parse_args()
    if a.what == 'list':
        for k, v in cases().items():
            print(f'{k:36s} {v["kind"]:6s} est {v["est"]:6d} s')
    elif a.what == 'deck':
        c = cases()[a.names[0]]
        print(deck({k: v for k, v in c.items() if k not in ('est', 'threads', 'rev')}))
    else:
        rc = 0
        for n in a.names:
            r = (run if a.what == 'run' else analyse)(n)
            if a.what == 'analyse':
                print(json.dumps(r, indent=1))
            if 'error' in r or r.get('flags'):
                rc = 1                     # the scheduler marks the job failed (and re-runs it if its command changes)
        sys.exit(rc)


if __name__ == '__main__':
    main()
