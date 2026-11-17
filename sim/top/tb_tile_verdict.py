#!/usr/bin/env python3
"""Verdicts for the extracted-tile runs (sim/top/tb_tile.py, references sim/top/tb_tile_ref.py), from
build/tile_sims/<name>/result.json.

    python3 sim/top/tb_tile_verdict.py              # every check -> build/tile_sims/verdict.json, prints the tables
    python3 sim/top/tb_tile_verdict.py --mutants    # the same checks on the mutated runs: every one must FAIL

Each check function takes results and returns (ok, detail). Missing results are 'pending', not a pass.
Pass criteria (and why):
  1 VCO   every run: no log flags, a2 swings from vg up to near VDD (a2_min > 0.8 V, a2_max > 3.0 V), ls rail to rail,
          f(a2) / f(ck) = 4 (+-0.1 %), ls duty 40-60 %; (1b) tile / reference at one corner the same within 1 % across
          codes and words (a constant wiring shift; a wrong code moves one point by a whole step, about 5 %); (1e) the
          shift within -5 ... +2 % (the layout's estimate); at tt: medium DAC range / coarse step >= 1.3 and codes
          0 ... 31 bracket 433.92 MHz.
  2 TX    on: fundamental into the dipole within 1.5 dB of the extracted-vco_top bench (sim/tx/results/top.md, case
          pg) and >= +3 dBm, arm phase error < 10 deg, VDPWR ripple < 30 mV (2 x the 13-15 mV of that bench behind the
          same switch); off: < -60 dBm, ua[2] / ua[3] < 50 mV p-p;
          the ring (VAPWR) moves < 0.2 % with the TX on against off.
  3 RX    q_i and q_q both toggle at the baseband frequency (edges >= 80 % of 2 x f_bb x window, f within 10 %);
          the baseband tone is |f_tone - f_ring| within 10 % (or 15 kHz); |I/Q phase| 50 ... 110 deg (the taps are 72 deg
          apart by design), the limiter phase agrees in sign with the analog baseband phase, and flips sign with the
          sign of the offset.
  4 Power-up  the ring oscillates by the end of the ramp + 5 us, ck = f / 4 at the end, vbnf rising in the last 5 us,
          no TX output (ua[2] / ua[3] < 50 mV p-p, dipole < 20 mV p-p) with the TX enables low.
  5 Debug each select reads its own node on ua[0] (within 2 mV with the 10 Mohm probe) and not the others (> 5 mV
          away, markers on oi_p / oq_p), no select moves no node (< 1 mV with ua[0] at 0 / 3.3 V), the vctrl
          override within 20 mV of 1.65 V, ua[1] < 1 mV with 1 mA in (the ground-sense pin).
  6 Supply  f moves < 0.5 % at VAPWR = VDPWR = 3.15 / 3.45 V; during TX the VAPWR ripple < 3 mV (3 x the 1.0 mV
          with the TX off) and the VDPWR ripple < 30 mV.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import tb_tile as T  # noqa: E402

OUT = T.OUT
FLO = 433.92e6
# the TX reference: tb_tx_top.py (extracted vco_top + schematic tx_drv + pads, behind the power switch), fundamental
# (dBm); sf / fs: the extracted tx_drv block bench (sim/tx/results/block_pex.txt, pexc)
TX_REF = dict(tt=6.31, ss=4.80, ff=7.31, sf=6.14, fs=6.57)


def res(name):
    p = OUT / name / 'result.json'
    if not p.exists():
        return None
    return json.loads(p.read_text())


def pending(name):
    return None, f'{name}: pending'


def bad(r):
    if r is None:
        return 'pending'
    if 'error' in r:
        return r['error']
    if r.get('flags'):
        return 'log: ' + ', '.join(r['flags'])
    return None


# ------------------------------------------------------------------------------------------------ 1 VCO
def ring_ok(r):
    b = bad(r)
    if b:
        return (None if b == 'pending' else False), b
    p = []
    if not r['a2_min'] > 0.8 or not r['a2_max'] > 3.0:
        p.append(f"a2 swing {r['a2_min']:.2f}-{r['a2_max']:.2f} V")
    if not (r['ls_min'] < 0.3 and r['ls_max'] > 3.0):
        p.append(f"ls {r['ls_min']:.2f}-{r['ls_max']:.2f} V")
    if not abs(r['div'] / 4 - 1) < 1e-3:
        p.append(f"f/f(ck) {r['div']:.4f}")
    if not 0.40 < r['ls_duty'] < 0.60:
        p.append(f"ls duty {r['ls_duty'] * 100:.1f} %")
    return (not p), '; '.join(p) or f"f {r['f_a2'] / 1e6:.2f} MHz"


def vco_pairs(mut=False):
    """(tile run, reference run) per point."""
    pairs = []
    for name, c in T.cases().items():
        if c['kind'] != 'ring' or not name.startswith('vco_c_') or name.endswith('_rx') or '_v3' in name:
            continue
        if name.startswith('vco_c_sf_k') and not name.startswith('vco_c_sf_k9'):
            continue                                  # code sweep at sf: no block reference
        pairs.append((name, 'ref_' + name[len('vco_c_'):]))
    if mut:
        pairs = [('mut_vco_code', 'ref_tt_k9_w512')] + [p for p in pairs if p[0] != 'vco_c_tt_k9_w512']
    return pairs


def check_vco(mut=False):
    rows, out = [], []
    ratios = {}
    for tn, rn in vco_pairs(mut):
        t, r = res(tn), res(rn)
        ok, why = ring_ok(t)
        if r is not None and bad(r):
            ok, why = False, f'reference {rn}: {bad(r)}'
        ratio = t['f_a2'] / r['f_a0'] - 1 if ok is not None and r is not None and not bad(r) and ok else None
        corner = tn.split('_')[2]
        if ratio is not None:
            ratios.setdefault(corner, []).append(ratio)
        rows.append(dict(tile=tn, ref=rn, ok=ok, why=why, f_tile=t and t.get('f_a2'), f_ref=r and r.get('f_a0'),
                         shift=ratio))
    out.append(('1a every ring run sane', all_ok([x['ok'] for x in rows]),
                '; '.join(f"{x['tile']}: {x['why']}" for x in rows if x['ok'] is False) or f'{len(rows)} runs'))
    sp = []
    okc = True if ratios else None
    okm = True if ratios else None
    for corner, rs in ratios.items():
        spread = max(rs) - min(rs)
        sp.append(f'{corner} {min(rs) * 100:+.2f} ... {max(rs) * 100:+.2f} %')
        if spread > 0.01:
            okc = False
        if min(rs) < -0.05 or max(rs) > 0.02:
            okm = False
    out.append(('1b tile / reference: the same shift at every code and word of a corner (spread < 1 %)', okc,
                ', '.join(sp)))
    out.append(('1e tile / reference within -5 ... +2 % (docs/tile_layout.md expected about -5 % from a2)', okm,
                ', '.join(sp)))
    # medium DAC range against the coarse step at tt, and 433.92 MHz in reach
    f = {k: (res(k) or {}).get('f_a2') for k in ('vco_c_tt_k9_w0', 'vco_c_tt_k9_w1023', 'vco_c_tt_k8_w512',
                                                 'vco_c_tt_k10_w512', 'vco_c_tt_k0_w512', 'vco_c_tt_k31_w512')}
    if mut:
        f['vco_c_tt_k9_w512'] = None
    if None in f.values():
        out.append(('1c medium DAC range / coarse step >= 1.3 at tt', None, 'pending'))
        out.append(('1d codes 0 ... 31 bracket 433.92 MHz at tt', None, 'pending'))
    else:
        step = (f['vco_c_tt_k10_w512'] - f['vco_c_tt_k8_w512']) / 2
        rng = f['vco_c_tt_k9_w1023'] - f['vco_c_tt_k9_w0']
        out.append(('1c medium DAC range / coarse step >= 1.3 at tt', rng / step >= 1.3,
                    f'range {rng / 1e6:.2f} MHz, step {step / 1e6:.2f} MHz, ratio {rng / step:.2f}'))
        out.append(('1d codes 0 ... 31 bracket 433.92 MHz at tt',
                    f['vco_c_tt_k0_w512'] < FLO < f['vco_c_tt_k31_w512'],
                    f"{f['vco_c_tt_k0_w512'] / 1e6:.1f} ... {f['vco_c_tt_k31_w512'] / 1e6:.1f} MHz"))
    fs = {c: (res(f'vco_c_sf_k{c}_w512') or {}).get('f_a2') for c in (9, 15, 23, 31)}
    if fs[31] is None:
        out.append(('1f 433.92 MHz in reach at sf (code 31, word 512 above it)', None, 'pending'))
    else:
        out.append(('1f 433.92 MHz in reach at sf (code 31, word 512 above it)', fs[31] > FLO,
                    ', '.join(f'code {c} {v / 1e6:.1f} MHz' for c, v in fs.items() if v)))
    return out, rows


# ------------------------------------------------------------------------------------------------ 2 TX
def check_tx(mut=False):
    out = []
    names = [n for n, c in T.cases().items() if c['kind'] == 'tx' and n.startswith('tx_') and n.endswith('_on')]
    if mut:
        names = ['mut_tx_noen', 'mut_tx_rsw10']
    for n in names:
        r = res(n)
        b = bad(r)
        corner = 'tt' if n.startswith('mut') else n.split('_')[2]
        if b:
            out.append((f'2 TX on {n}', None if b == 'pending' else False, b))
            continue
        ref = TX_REF[corner]
        p = []
        p1 = r.get('p1_dbm', -200)
        if not (abs(p1 - ref) <= 1.5 and p1 >= 3.0):
            p.append(f'P1 {p1:+.2f} dBm (ref {ref:+.2f})')
        if not abs(r.get('ph_err_deg', 999)) < 10:
            p.append(f"phase error {r.get('ph_err_deg', float('nan')):+.1f} deg")
        if not r['vdp_ripple_mv'] < 30:
            p.append(f"VDPWR ripple {r['vdp_ripple_mv']:.0f} mV")
        out.append((f'2 TX on {n}', not p, '; '.join(p) or
                    f"P1 {p1:+.2f} dBm (ref {ref:+.2f}), P {r['p_dip_dbm']:+.2f} dBm, phase {r['ph_err_deg']:+.2f} deg, "
                    f"I(VDPWR) {r['i_vdp_ma']:.2f} mA, ripple VDPWR / VAPWR {r['vdp_ripple_mv']:.1f} / "
                    f"{r['vap_ripple_mv']:.1f} mV"))
    if not mut:
        r = res('tx_c_tt_off')
        b = bad(r)
        if b:
            out.append(('2 TX off: no output', None if b == 'pending' else False, b))
        else:
            ok = r['p_dip_dbm'] < -60 and r['ua2_pp'] < 0.05 and r['ua3_pp'] < 0.05
            out.append(('2 TX off: no output', ok, f"P {r['p_dip_dbm']:+.1f} dBm, ua[2] / ua[3] "
                        f"{r['ua2_pp'] * 1e3:.2f} / {r['ua3_pp'] * 1e3:.2f} mV p-p"))
    return out


# ------------------------------------------------------------------------------------------------ 3 RX
def rx_one(r):
    b = bad(r)
    if b:
        return (None if b == 'pending' else False), b
    p = []
    win = T.RX_TSTOP - T.RX_TSKIP
    need = 0.8 * 2 * r['f_bb_expect'] * win
    if not (r['qi_edges'] >= need and r['qq_edges'] >= need):
        p.append(f"edges {r['qi_edges']} / {r['qq_edges']} (need {need:.0f})")
    for k in ('f_qi', 'f_qq'):
        if not abs(r[k] / r['f_bb_expect'] - 1) < 0.10:
            p.append(f"{k} {r[k] / 1e3:.1f} kHz vs {r['f_bb_expect'] / 1e3:.1f}")
    if not (abs(r['f_bb'] - r['f_bb_expect']) < max(15e3, 0.1 * r['f_bb_expect'])):
        p.append(f"baseband {r['f_bb'] / 1e3:.1f} kHz vs {r['f_bb_expect'] / 1e3:.1f}")
    q = r['q_iq_phase']
    if not 50 <= abs(q) <= 110:
        p.append(f'limiter I/Q phase {q:+.1f} deg')
    if not (q * r['bb_iq_phase'] > 0):
        p.append(f"limiter phase {q:+.1f} vs baseband {r['bb_iq_phase']:+.1f} deg: signs differ")
    return (not p), '; '.join(p) or (f"f_bb {r['f_bb'] / 1e3:.0f} kHz, q_i / q_q {r['f_qi'] / 1e3:.0f} / "
                                      f"{r['f_qq'] / 1e3:.0f} kHz, I/Q {q:+.1f} deg (baseband {r['bb_iq_phase']:+.1f})")


def check_rx(mut=False):
    out = []
    names = [n for n, c in T.cases().items() if c['kind'] == 'rx' and n.startswith('rxh_')]
    rs = {n: res(n) for n in names}
    if mut:
        names = ['mut_rx_off', 'mut_rx_swapout']
        rs = {'mut_rx_off': res('mut_rx_off')}
        r = res('rxh_c_tt_-70_p')
        if r is not None and 'error' not in r:      # q_i / q_q exchanged: re-analysed from the same raw
            rs['mut_rx_swapout'] = T.analyse_with('rxh_c_tt_-70_p', swap_out=True)
        else:
            rs['mut_rx_swapout'] = r
    for n in names:
        ok, why = rx_one(rs[n])
        out.append((f'3 RX {n}', ok, why))
    # the sign of the I/Q phase follows the sign of the offset
    p, m = (rs.get('rxh_c_tt_-70_p'), rs.get('rxh_c_tt_-70_n')) if not mut else (rs.get('mut_rx_swapout'),
                                                                                  res('rxh_c_tt_-70_n'))
    if p is None or m is None or bad(p) or bad(m):
        out.append(('3 RX I/Q sign flips with the offset sign', None if (p is None or m is None) else False,
                    'pending' if (p is None or m is None) else 'a run failed'))
    else:
        ok = p['q_iq_phase'] * m['q_iq_phase'] < 0 and p['bb_iq_phase'] * m['bb_iq_phase'] < 0
        out.append(('3 RX I/Q sign flips with the offset sign', ok,
                    f"+df {p['q_iq_phase']:+.1f} deg, -df {m['q_iq_phase']:+.1f} deg (baseband "
                    f"{p['bb_iq_phase']:+.1f} / {m['bb_iq_phase']:+.1f})"))
    return out


# ------------------------------------------------------------------------------------------------ 4 power-up
def check_pwr(mut=False):
    out = []
    for n in (['mut_pwrup_txon'] if mut else ['pwrup_c_tt']):
        r = res(n)
        b = bad(r)
        if b:
            out.append((f'4 power-up {n}', None if b == 'pending' else False, b))
            continue
        w = r['windows']
        p = []
        if r['t_osc_us'] is None or r['t_osc_us'] > 15:
            p.append(f"ring not running by 15 us (t_osc {r['t_osc_us']})")
        if not (r['f_ck_end'] == r['f_ck_end'] and abs(r['f_end'] / r['f_ck_end'] / 4 - 1) < 2e-3):
            p.append(f"f / f(ck) at the end {r['f_end'] / r['f_ck_end']:.3f}")
        if not w[-1]['vbnf'] > w[-5]['vbnf'] - 1e-3:
            p.append('vbnf falling at the end')
        if not (r['ua_tx_pp_max'] < 0.05 and r['dip_pp_max'] < 0.02):
            p.append(f"TX output {r['ua_tx_pp_max'] * 1e3:.1f} mV p-p at ua[2/3], {r['dip_pp_max'] * 1e3:.1f} mV "
                     'on the dipole')
        out.append((f'4 power-up {n}', not p, '; '.join(p) or
                    f"oscillates from {r['t_osc_us']:.0f} us, f at the end {r['f_end'] / 1e6:.1f} MHz, vbnf "
                    f"{r['vbnf_end']:.3f} V, TX output {r['ua_tx_pp_max'] * 1e3:.2f} mV p-p, I(VAPWR) / I(VDPWR) "
                    f"{r['i_vap_end_ma']:.2f} / {r['i_vdp_end_ma']:.2f} mA (peaks {r['i_vap_peak_ma']:.1f} / "
                    f"{r['i_vdp_peak_ma']:.1f})"))
    return out


# ------------------------------------------------------------------------------------------------ 5 debug
def check_dbg(mut=False):
    out = []
    for n in (['mut_dbg_swap01', 'mut_dbg_c_rxoff'] if mut else ['dbg_c_tt']):
        r = res(n)
        b = bad(r)
        if b:
            out.append((f'5 debug mux {n}', None if b == 'pending' else False, b))
            continue
        p = []
        for k, node in enumerate(T.DBG_NODES):
            s = r['sel'].get(node)
            if s is None:
                p.append(f'{node}: no op')
                continue
            if not abs(s['err_mv']) < 2:
                p.append(f"sel {k}: ua[0] {s['pin']:.4f} V vs {node} {s['node']:.4f} V")
            near = [m for m, v in s.get('others', {}).items() if abs(s['pin'] - v) < 5e-3]
            if near:
                p.append(f"sel {k}: ua[0] also within 5 mV of {', '.join(near)}")
        if not all(abs(v) < 1 for v in r.get('off_shift_mv', {'x': 99}).values()):
            p.append(f"off isolation {r.get('off_shift_mv')}")
        if not abs(r.get('vctrl_override', 0) - 1.65) < 0.02:
            p.append(f"vctrl override {r.get('vctrl_override')}")
        if not (r.get('ua1_1ma') is not None and abs(r['ua1_1ma']) < 1e-3):
            p.append(f"ua[1] {r.get('ua1_1ma')} V at 1 mA")
        out.append((f'5 debug mux {n}', not p, '; '.join(p) or ', '.join(
            f"{nd}: err {s['err_mv']:+.2f} mV, R(pin->node) {s['r_switch_ohm'] / 1e3:.2f} kohm, probe pulls the node "
            f"{s.get('probe_shift_mv', float('nan')):+.1f} mV" for nd, s in r['sel'].items())))
    return out


# ------------------------------------------------------------------------------------------------ 6 supply
def check_supply(mut=False):
    out = []
    b0 = res('vco_c_tt_k9_w512')
    for v in ('3.15', '3.45'):
        r = res(f'vco_c_tt_k9_w512_v{v}')
        if bad(r) or bad(b0):
            out.append((f'6 VCO at {v} V', None if 'pending' in (bad(r), bad(b0)) else False, bad(r) or bad(b0)))
            continue
        d = r['f_a2'] / b0['f_a2'] - 1
        out.append((f'6 VCO at {v} V', abs(d) < 5e-3, f'{d * 100:+.3f} % ({d * 1e4 / ((float(v) - 3.3) * 100):+.4f} %/10 mV)'))
    on, off = (res('mut_tx_rsw10') if mut else res('tx_c_tt_on')), res('tx_c_tt_off')
    if bad(on) or bad(off):
        out.append(('6 ring supply during TX', None if 'pending' in (bad(on), bad(off)) else False, bad(on) or bad(off)))
    else:
        d = on['f_a2'] / off['f_a2'] - 1
        ok = abs(d) < 2e-3 and on['vap_ripple_mv'] < 3 and on['vdp_ripple_mv'] < 30
        out.append(('6 ring supply during TX', ok, f"f on / off {d * 100:+.3f} %, VAPWR ripple {on['vap_ripple_mv']:.1f} "
                    f"mV p-p (off {off['vap_ripple_mv']:.1f}), VDPWR {on['vdp_ripple_mv']:.1f} mV p-p"))
    for s in ('vap', 'vdp'):
        r = res(f'zac_c_tt_{s}')
        if bad(r):
            out.append((f'6 supply impedance {s}', None, bad(r)))
            continue
        out.append((f'6 supply impedance {s}', True, ', '.join(
            f"{f / 1e6:g} MHz {r[f'z_{f:g}']:.1f} ohm ({r[f'c_eff_pf_{f:g}']:.0f} pF)" for f in (1e6, 2.5e7, 1e8, 4.34e8))))
    return out


def all_ok(xs):
    if any(x is False for x in xs):
        return False
    if any(x is None for x in xs):
        return None
    return True


def main():
    mut = '--mutants' in sys.argv
    checks = []
    v, rows = check_vco(mut)
    checks += v
    for f in (check_tx, check_rx, check_pwr, check_dbg, check_supply):
        checks += f(mut)
    sym = {True: 'PASS', False: 'FAIL', None: 'pending'}
    for name, ok, why in checks:
        print(f'{sym[ok]:8s} {name}: {why}')
    if mut:
        # every mutated check must fail (the supply impedance rows don't take mutants)
        mc = [(n, ok) for n, ok, _ in checks if n.startswith(('1b', '2 TX on mut', '3 RX mut', '3 RX I/Q', '4 power-up mut',
                                                              '5 debug mux mut', '6 ring supply'))]
        caught = [n for n, ok in mc if ok is False]
        miss = [n for n, ok in mc if ok is True]
        pend = [n for n, ok in mc if ok is None]
        print(f'\nmutations caught {len(caught)} / {len(mc)}; missed: {miss or "none"}; pending: {pend or "none"}')
        (OUT / 'verdict_mutants.json').write_text(json.dumps(dict(checks=checks, caught=caught, missed=miss,
                                                                   pending=pend), indent=1, default=str))
    else:
        (OUT / 'verdict.json').write_text(json.dumps(dict(checks=checks, vco=rows), indent=1, default=str))


if __name__ == '__main__' and '--tables' not in sys.argv:
    main()


# ------------------------------------------------------------------------------------------------ tables
def f6(x, k=1e6, d=2):
    return '-' if x is None or x != x else f'{x / k:.{d}f}'


def tables():
    """Markdown tables of the numbers (build/tile_sims/tables.md), quoted by sim/top/tile_results.md."""
    L = ['### VCO', '', '| corner, code, word | block f (MHz) | tile f (MHz) | tile / block | f/f(ck) | ls duty | vg (V) '
         '| vbnf (V) | I(VAPWR) (mA) | flags |', '|---|---|---|---|---|---|---|---|---|---|']
    for tn, rn in vco_pairs():
        t, r = res(tn), res(rn)
        if not t or 'error' in t:
            L.append(f'| {tn} | {f6(r and r.get("f_a0"))} | {"pending" if not t else t["error"]} |' + ' |' * 7)
            continue
        sh = (t['f_a2'] / r['f_a0'] - 1) * 100 if r and r.get('f_a0') else float('nan')
        L.append(f"| {tn[6:].replace('_', ' ')} | {f6(r and r.get('f_a0'))} | {f6(t['f_a2'])} | {sh:+.2f} % | "
                 f"{t['div']:.4f} | {t['ls_duty'] * 100:.1f} % | {t['vg']:.3f} | {t['vbnf']:.4f} | {t['i_vap_ma']:.2f} | "
                 f"{', '.join(t['flags']) or 'none'} |")
    for n in ('vco_c_tt_k9_w512_rx', 'vco_rcx_tt_k9_w512', 'vco_c_tt_k9_w512_v3.15', 'vco_c_tt_k9_w512_v3.45',
              'rxpre_c_tt', 'rxpre_c_ss', 'rxpre_c_ff'):
        t = res(n)
        if t and 'error' not in t:
            L.append(f"| {n} | - | {f6(t['f_a2'])} | - | {t['div']:.4f} | {t['ls_duty'] * 100:.1f} % | {t['vg']:.3f} | "
                     f"{t['vbnf']:.4f} | {t['i_vap_ma']:.2f} | {', '.join(t['flags']) or 'none'} |")
    L += ['', '### TX', '', '| run | f(a2) (MHz) | P dipole / fundamental (dBm) | reference fund. (dBm) | phase error (deg) '
          '| I(VDPWR) avg / rms (mA) | ripple VDPWR / VAPWR (mV p-p) | flags |', '|---|---|---|---|---|---|---|---|']
    for n in [k for k, c in T.cases().items() if c['kind'] == 'tx']:
        r = res(n)
        if not r or 'error' in r:
            L.append(f'| {n} | {"pending" if not r else r["error"]} |' + ' |' * 6)
            continue
        cn = 'tt' if n.startswith('mut') else n.split('_')[2]
        L.append(f"| {n} | {f6(r['f_a2'])} | {r['p_dip_dbm']:+.2f} / {r.get('p1_dbm', float('nan')):+.2f} | "
                 f"{TX_REF.get(cn, float('nan')):+.2f} | {r.get('ph_err_deg', float('nan')):+.2f} | {r['i_vdp_ma']:.2f} / "
                 f"{r['i_vdp_rms_ma']:.2f} | {r['vdp_ripple_mv']:.1f} / {r['vap_ripple_mv']:.1f} | "
                 f"{', '.join(r['flags']) or 'none'} |")
    L += ['', '### RX', '', '| run | ring f (MHz) | tone - ring (kHz) | baseband f (kHz) | q_i / q_q f (kHz) | edges i / q '
          '| I/Q limiter / baseband (deg) | LO I/Q (deg) | baseband I / Q (V) | mixer I (mV) | flags |',
          '|---|---|---|---|---|---|---|---|---|---|---|']
    for n in [k for k, c in T.cases().items() if c['kind'] == 'rx']:
        r = res(n)
        if not r or 'error' in r:
            L.append(f'| {n} | {"pending" if not r else r["error"]} |' + ' |' * 9)
            continue
        if r['qi_edges'] < 2:
            L.append(f"| {n} | {f6(r['f_a2'], 1e6, 3)} | {(r['f_tone'] - r['f_a2']) / 1e3:+.1f} | {r['f_bb'] / 1e3:.0f} | "
                     f"no toggles | {r['qi_edges']} / {r['qq_edges']} | - / {r['bb_iq_phase']:+.1f} | "
                     f"{r['lo_iq_phase']:.1f} | {r['bb_i_v']:.3f} / {r['bb_q_v']:.3f} | {r['mix_i_v'] * 1e3:.2f} | "
                     f"{', '.join(r['flags']) or 'none'} |")
            continue
        L.append(f"| {n} | {f6(r['f_a2'], 1e6, 3)} | {(r['f_tone'] - r['f_a2']) / 1e3:+.1f} | {r['f_bb'] / 1e3:.0f} | "
                 f"{f6(r['f_qi'], 1e3, 1)} / {f6(r['f_qq'], 1e3, 1)} | {r['qi_edges']} / {r['qq_edges']} | "
                 f"{r['q_iq_phase']:+.1f} / {r['bb_iq_phase']:+.1f} | {r['lo_iq_phase']:.1f} | {r['bb_i_v']:.3f} / "
                 f"{r['bb_q_v']:.3f} | {r['mix_i_v'] * 1e3:.2f} | {', '.join(r['flags']) or 'none'} |")
    for n in ('pwrup_c_tt', 'mut_pwrup_txon'):
        r = res(n)
        if not r or 'windows' not in r:
            continue
        L += ['', f'### Power-up {n}', '', '| t (us) | VAPWR (V) | a2 swing (V) | f(a2) (MHz) | f(ck) (MHz) | vg (V) | vbnf (V) '
              '| nb (V) | ua[2] / ua[3] p-p (mV) | I(VAPWR) / I(VDPWR) (mA) |', '|---|---|---|---|---|---|---|---|---|---|']
        for w in r['windows']:
            L.append(f"| {w['t0'] * 1e6:.0f} | {w['vap']:.2f} | {w['a2_swing']:.2f} | {f6(w['f_a2'], 1e6, 1)} | "
                     f"{f6(w['f_ck'], 1e6, 1)} | {w['vg']:.3f} | {w['vbnf']:.3f} | {w['nb']:.3f} | {w['ua2_pp'] * 1e3:.2f} / "
                     f"{w['ua3_pp'] * 1e3:.2f} | {w['i_vap_ma']:.2f} / {w['i_vdp_ma']:.2f} |")
    for n in ('dbg_c_tt', 'dbg_rcx_tt'):
        r = res(n)
        if not r or 'sel' not in r:
            continue
        L += ['', f'### Debug mux {n}', '', '| select | node (V) | ua[0] pin (V) | error (mV) | probe pulls node (mV) '
              '| R pin -> node (kohm) | R seen at the pin (kohm) |', '|---|---|---|---|---|---|---|']
        for k, nd in enumerate(T.DBG_NODES):
            s = r['sel'].get(nd)
            if s:
                L.append(f"| dbg_sel[{k}] -> {nd} | {s['node']:.4f} | {s['pin']:.4f} | {s['err_mv']:+.2f} | "
                         f"{s.get('probe_shift_mv', float('nan')):+.1f} | {s['r_switch_ohm'] / 1e3:.2f} | {s['r_out_ohm'] / 1e3:.1f} |")
        L.append(f"\nno select: ua[0] {r.get('none_pin0')} V; nodes moved by ua[0] 0 -> 3.3 V: {r.get('off_shift_mv')} mV; "
                 f"vctrl with ua[0] forced to 1.65 V: {r.get('vctrl_override')} V; ua[1] with 1 mA in: {r.get('ua1_1ma')} V")
    for s in ('vap', 'vdp'):
        r = res(f'zac_c_tt_{s}')
        if r and 'error' not in r:
            if s == 'vap':
                L += ['', '### Supply impedance', '', '| port | 100 kHz | 1 MHz | 10 MHz | 25 MHz | 100 MHz | 434 MHz |',
                      '|---|---|---|---|---|---|---|']
            L.append(f"| {s} |" + ' |'.join(f" {r[f'z_{f:g}']:.1f} ohm ({r[f'c_eff_pf_{f:g}']:.0f} pF)"
                                             for f in (1e5, 1e6, 1e7, 2.5e7, 1e8, 4.34e8)) + ' |')
    (OUT / 'tables.md').write_text('\n'.join(L) + '\n')
    return L


if __name__ == '__main__' and '--tables' in sys.argv:
    print('\n'.join(tables()))
