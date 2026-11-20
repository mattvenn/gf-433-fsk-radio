#!/usr/bin/env python3
"""The single top-level verdict of the full verification run (docs/handoff_full_verification.md): every EXISTING check
of docs/verification.md and the NEW gap 1-6 checks of docs/plan_verify_gaps.md, each PASS / FAIL / pending, and every
planted error (mutation) caught / missed / pending. Missing results are 'pending', never a pass.

    python3 sim/verify/verdict.py [--smoke]     -> build/verify/verdict.md, verdict.json (exit 0 always: read the file)

Where the results are (the full run's job file sim/verify/jobs_full.py writes them there):
  existing digital / layout   build/verify/existing/<check>.log, last line "RESULT <check> PASS|FAIL ..." (existing.sh)
  mixed-signal                build/mixed/verdict.json + verdict_mutants (sim/mixed/verdict.py --mutants, rerun here)
  extracted tile (existing)   build/verify/tile_existing (sim/top/tb_tile_verdict.py, with and without --mutants)
  power grid                  build/power/res_*/result.json (criterion below: none was coded in sim/power)
  gaps 2-6 on the tile        build/verify/tile/<case>/result.json (sim/verify/tile_verify.py)
  gaps 1, 2, 4 on the chain   build/verify/chain/... (sim/verify/chain_x.py, mc_report.py); gap 5 build/verify/coupling
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
B = REPO / 'build' / 'verify'
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(REPO / 'sim' / 'top'))

CHECKS, MUTS = [], []
SMOKE = '--smoke' in sys.argv


def chk(area, name, ok, detail=''):
    CHECKS.append(dict(area=area, check=name, status={True: 'PASS', False: 'FAIL', None: 'pending'}[ok], detail=detail))


def mut(area, name, caught, detail=''):
    MUTS.append(dict(area=area, mutation=name, status={True: 'caught', False: 'MISSED', None: 'pending'}[caught],
                     detail=detail))


def jload(p):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return None


def bad(r):
    if r is None:
        return 'pending'
    if 'error' in r:
        return str(r['error'])[:200]
    if r.get('flags'):
        return 'log: ' + ', '.join(r['flags'])
    return None


def okb(r):
    """None (pending) / False (failed run) / True."""
    b = bad(r)
    return None if b == 'pending' else (False if b else True)


# ================================================================================================ existing checks
EXIST = [('digital', 'pinout'), ('digital', 'mutations'), ('digital', 'cocotb_macro'), ('digital', 'cocotb_macro_gl'),
         ('digital', 'cocotb_tt'), ('digital', 'cocotb_tt_gl'), ('digital', 'formal_prove'),
         ('digital', 'formal_gates_bmc'), ('digital', 'formal_mutate'), ('digital', 'eqy'),
         ('layout', 'floorplan'), ('layout', 'xschem'), ('layout', 'layout')]


def existing():
    for area, c in EXIST:
        p = B / 'existing' / f'{c}.log'
        line = None
        if p.exists():
            for ln in p.read_text(errors='replace').splitlines():
                if ln.startswith(f'RESULT {c} '):
                    line = ln
        if line is None:
            chk(area, c, None, 'pending')
            continue
        st, det = line.split(' ', 3)[2], line.split(' ', 3)[3] if len(line.split(' ', 3)) > 3 else ''
        chk(area, c, st == 'PASS', det)
        m = re.search(r'(?:mutants|planted bugs|mutations) caught (\d+) / (\d+)', det)
        if m:
            mut(area, f'{c}: planted bugs', int(m.group(1)) == int(m.group(2)), f'{m.group(1)} / {m.group(2)}')
    if (B / 'existing' / 'layout.log').exists():          # tile_driver's own mutation lines (LVS 14, DRC, antenna)
        t = (B / 'existing' / 'layout.log').read_text(errors='replace') + (
            (REPO / 'build/tile/run/status.txt').read_text(errors='replace') if (REPO / 'build/tile/run/status.txt').exists() else '')
        m = re.findall(r'(\d+) / (\d+) mutations', t)
        if m:
            a, b_ = m[-1]
            mut('layout', 'tile_driver: LVS / DRC / antenna planted errors', a == b_, f'{a} / {b_}')
    # mixed-signal: sim/mixed/verdict.py --mutants (its own check lines) on build/mixed
    if (REPO / 'build/mixed/status.json').exists():
        r = subprocess.run([sys.executable, 'sim/mixed/verdict.py', '--mutants'], cwd=REPO, capture_output=True, text=True)
        for ln in r.stdout.splitlines():
            m = re.match(r'^\s*(PASS|FAIL|pending|PEND\w*)\s+(.*)$', ln)
            if m:
                st = m.group(1)
                name = m.group(2)[:110]
                if 'mutant' in name.lower():
                    mut('mixed', name, True if st == 'FAIL' else (False if st == 'PASS' else None))
                else:
                    chk('mixed', name, True if st == 'PASS' else (False if st == 'FAIL' else None))
        if not any(c['area'] == 'mixed' for c in CHECKS):
            chk('mixed', 'sim/mixed/verdict.py', r.returncode == 0, r.stdout[-300:])
    else:
        chk('mixed', 'co-simulation (sim/mixed)', None, 'pending')
    # extracted tile, existing checks
    out = B / 'tile_existing'
    if out.exists():
        env = dict(os.environ, TILE_SIMS_OUT=str(out))
        for mode in ('', '--mutants'):
            r = subprocess.run([sys.executable, 'sim/top/tb_tile_verdict.py'] + ([mode] if mode else []), cwd=REPO,
                               capture_output=True, text=True, env=env)
            for ln in r.stdout.splitlines():
                m = re.match(r'^(PASS|FAIL|pending)\s+(.*?): (.*)$', ln)
                if not m:
                    continue
                st, name, det = m.groups()
                if mode:
                    if name.startswith(('1b', '2 TX on mut', '3 RX mut', '3 RX rxs_c_tt_-95_p (f_qi', '3 RX I/Q',
                                        '4 power-up mut', '5 debug mux mut', '6 ring supply', '7 I/Q LO mut')):
                        mut('tile (existing)', name, True if st == 'FAIL' else (False if st == 'PASS' else None), det[:160])
                else:
                    chk('tile (existing)', name, True if st == 'PASS' else (False if st == 'FAIL' else None), det[:200])
    else:
        chk('tile (existing)', 'tb_tile_verdict.py', None, 'pending')
    power()


EM_85C = 3.1     # the 85 C EM limit / the LEF figure (sim/power/results.md: Metal 2.09 / 0.67 mA/um)


def power():
    """Criterion added for this run (the power study had none coded): every solve finished; worst EM ratio against
    the LEF figure < 3.1 (= the 85 C limit) on the real grid; each mutated grid is worse than the real one."""
    def worst(r):
        w = 0.0
        for case in r['cases'].values():
            for net in case.values():
                for mode in net.get('modes', {}).values():
                    for lay in mode.get('em', {}).values():
                        if isinstance(lay, dict) and 'ratio' in lay:
                            w = max(w, lay['ratio'])
        return w
    base = jload(REPO / 'build/power/res_p0.5/result.json')
    if base is None:
        chk('power', 'IR drop / EM (sim/power)', None, 'pending')
        return
    wb = worst(base)
    det = [f'p0.5 worst EM {wb:.2f} x LEF ({wb / EM_85C:.2f} x 85 C)']
    ok = wb < EM_85C
    for tag in ('p0.25', 'p0.5_ss', 'p0.5_ff'):
        r = jload(REPO / f'build/power/res_{tag}/result.json')
        if r is None:
            ok = None if ok is not False else ok
            det.append(f'{tag} pending')
        else:
            w = worst(r)
            det.append(f'{tag} {w:.2f}')
            ok = ok and w < EM_85C
    chk('power', 'EM worst < the 85 C limit, every solve done', ok, '; '.join(det))
    for tag in ('mut_via', 'mut_narrow', 'mut_rs2'):
        r = jload(REPO / f'build/power/res_p0.5_{tag}/result.json')
        mut('power', f'power grid {tag}: worse than the real grid', None if r is None else worst(r) > wb,
            '' if r is None else f'{worst(r):.2f} vs {wb:.2f}')


# ================================================================================================ gap 1
def gap1():
    r = jload(B / 'chain' / 'mc_report.json')
    if r is None:
        chk('gap 1 MC', 'receiver mismatch MC (extracted blocks)', None, 'pending')
        mut('gap 1 MC', 'mismatch off: the spread check must fail', None)
        mut('gap 1 MC', 'stage-1 fingers merged into m=16: the unit-instance check must flag it', None)
        return
    for cn, c in r['corners'].items():
        if c.get('status') == 'pending':
            chk('gap 1 MC', f'{cn}: MC samples', None, f"{c.get('n', 0)} samples")
            continue
        chk('gap 1 MC', f'{cn}: every MC run clean (N = {c["n"]})', c['n_bad_runs'] == 0, f"{c['n_bad_runs']} bad")
        chk('gap 1 MC', f'{cn}: |comparator offset| + hysteresis <= {r["cmp_limit_mv"]:.0f} mV (half the -105 dBm signal) '
            f'in >= 99 %', c['cmp_yield'] >= 0.99, f"yield {c['cmp_yield'] * 100:.1f} %, worst {c['cmp_worst_mv']:.1f} mV; "
            f"offset sigma {c['vos_i_mv']['std']:.2f} mV, hysteresis {c['hyst_i_mv']['mean']:.1f} mV")
        chk('gap 1 MC', f'{cn}: stage-1 output offset < {r["s1_max_v"]} V (no rail) in >= 99 %', c['s1_yield'] >= 0.99,
            f"yield {c['s1_yield'] * 100:.1f} %, worst {c['s1_worst_v'] * 1e3:.0f} mV; mixer offset "
            f"{c['mix_i_off_mv']['mean']:.2f} +- {c['mix_i_off_mv']['std']:.2f} mV")
        chk('gap 1 MC', f'{cn}: model sensitivity within {r["sens_db"]:.0f} dB of nominal in >= 99 %',
            c['sens_yield'] >= 0.99, f"nominal {c['sens_nominal']:.1f} dBm, worst +{c['sens_delta_db']['max']:.2f} dB "
            f"(mean {c['sens_delta_db']['mean']:+.2f}, n {c['sens_delta_db']['n']}); I/Q conv. phase sigma "
            f"{c['conv_phase']['std']:.2f} deg, gain ratio sigma {c['conv_gq']['std']:.3f}")
        chk('gap 1 MC', f'{cn}: one mismatch draw per device (no fet with m > 1 in the MC decks)', not c['merged_fets'],
            str(c['merged_fets'][:5]))
    sc = r.get('spread_check', {})
    chk('gap 1 MC', 'the MC varies (comparator offset spread > 0.01 mV)', sc.get('pass_'),
        f"std {sc.get('std_vos_i_mv')}")
    mm = r.get('mut_mmoff', {})
    mut('gap 1 MC', 'mismatch off: no spread (the spread check fails on it)', mm.get('caught') if mm.get('vos_i_mv') else None,
        f"offsets {mm.get('vos_i_mv')}")
    mg = r.get('mut_merge', {})
    mut('gap 1 MC', 'stage-1 fingers merged into one m=16 instance: the unit-instance check flags it', mg.get('caught'),
        f"n {mg.get('n')}, stage-1 offset sigma {mg.get('std_merged', float('nan')) * 1e3:.1f} vs unit {mg.get('std_unit', float('nan')) * 1e3:.1f} mV "
        f"(F {mg.get('f_ratio', float('nan')):.1f}, p {mg.get('p', float('nan')):.2g})" if mg.get('n') else '')
    if r.get('sch_extra'):
        s = r['sch_extra']
        chk('gap 1 MC', 'schematic MC, unit instances (extra, not evidence)', True,
            f"n {s['n']}: offset sigma {s['vos_i_mv']['std']:.2f} mV, mixer {s['mix_i_off_mv']['mean']:.2f} +- "
            f"{s['mix_i_off_mv']['std']:.2f} mV")


# ================================================================================================ gap 2 / 6
def ber_check(errs, n, p, alpha=0.01):
    """Two-sided binomial test of errs in n bits against BER p: (ok, P[X>=errs], P[X<=errs])."""
    import rxm
    hi, lo = rxm.binom_p(errs, n, p)
    return (hi >= alpha and lo >= alpha), hi, lo


def model_p(level, nf):
    import rxm
    return rxm.ber(level, nf_db=nf if nf is not None else None, nbits=40000, seed=11) if nf is not None else 0.0


NF_NOM = 7.3


def gap2():
    # tile, with noise
    import tile_verify as V
    for n, c in V.cases().items():
        if not n.startswith('fskn_') or (('_n2_' in n) != SMOKE):
            continue
        r = jload(B / 'tile' / n / 'result.json')
        if okb(r) is not True:
            chk('gap 2 noise', f'tile {n}', okb(r), bad(r) or '')
            continue
        lv = c['fsk']['level']
        p = model_p(lv, c['nf'])
        ok, hi, lo = ber_check(r['bit_errors'], r['n_data'], p)
        chk('gap 2 noise', f'tile {n}: bit errors vs the model (two-sided binomial, 1 %), no glitches',
            ok and r['glitches'] == 0, f"{r['bit_errors']} / {r['n_data']} errors, model BER {p:.2g} "
            f"(P[>=] {hi:.2g}, P[<=] {lo:.2g}), glitches {r['glitches']}, counts {r['counts']}")
    # extracted chain: pooled per level and NF
    pool = {}
    for p_ in sorted((B / 'chain').glob('fsk_pex_tt_*_nf*_s*/result.json')):
        r = jload(p_)
        if r is None:
            continue
        key = (r['level'], r['nf'])
        pool.setdefault(key, []).append(r)
    if not pool:
        chk('gap 2 noise', 'extracted chain BER statistics', None, 'pending')
    for (lv, nf), rs in sorted(pool.items()):
        good = [r for r in rs if okb(r) is True]
        e, n = sum(r['bit_errors'] for r in good), sum(r['n_data'] for r in good)
        gl = sum(r['glitches'] for r in good)
        p = model_p(lv, NF_NOM)                       # the checker always compares with the nominal NF's BER
        ok, hi, lo = ber_check(e, n, p) if n else (None, 1, 1)
        det = (f'{e} / {n} errors in {len(good)} runs ({len(rs) - len(good)} bad), model BER at NF {NF_NOM} dB {p:.2g} '
               f'(P[>=] {hi:.2g}, P[<=] {lo:.2g}), glitches {gl}')
        okall = (ok and gl == 0 and len(good) == len(rs)) if n else None
        if abs(nf - NF_NOM) < 0.05:
            chk('gap 2 noise', f'extracted chain {lv} dBm, NF {nf} dB: errors vs the model, no glitches', okall, det)
        else:
            what = 'NF 0 dB (errors must fall)' if nf < 1 else 'noise x 10 (errors must rise)'
            mut('gap 2 noise', f'{what}: {lv} dBm', None if okall is None else (not ok), det)


def gap6():
    import tile_verify as V
    for n, c in V.cases().items():
        if not n.startswith('fsk_c_') or (('_n2' in n) != SMOKE):
            continue
        r = jload(B / 'tile' / n / 'result.json')
        if okb(r) is not True:
            chk('gap 6 FSK', f'tile {n}', okb(r), bad(r) or '')
            mut('gap 6 FSK', f'{n}: reference data inverted (errors must be all bits)', None)
            continue
        chk('gap 6 FSK', f'tile {n}: 0 bit errors, no glitches', r['bit_errors'] == 0 and r['glitches'] == 0,
            f"{r['bit_errors']} / {r['n_data']} errors, counts {r['counts']}, sign {r['sign']}, delay {r['delay_us']:.2f} us, "
            f"glitches {r['glitches']}")
        # mutations (analysis level, from the stored counts): data reference inverted; preamble corrupted
        cnt = np.array(r['counts'])
        bits = np.array(r['bits_sent'])
        npre = c['npre']
        dec = (r['sign'] * cnt[npre:]) > 0
        inv = int(np.sum(dec != (1 - bits[npre:npre + len(dec)] > 0)))
        mut('gap 6 FSK', f'{n}: reference data bits inverted', inv == len(dec), f'{inv} / {len(dec)} errors')
        s2 = 1 if np.sum(np.where(1 - bits[:npre] > 0, 1, -1) * cnt[:npre]) >= 0 else -1
        e2 = int(np.sum(((s2 * cnt[npre:]) > 0) != (bits[npre:npre + len(dec)] > 0)))
        mut('gap 6 FSK', f'{n}: preamble inverted (the decoder learns the wrong sign)', e2 == len(dec), f'{e2} / {len(dec)} errors')
    for lv in (-70, -95):
        r = jload(B / 'chain' / f'fsk_pex_tt_{lv}_n16' / 'result.json')
        if r is not None or not SMOKE:
            chk('gap 6 FSK', f'extracted chain {lv} dBm 16 bits (ideal LO)', okb(r) and r['bit_errors'] == 0 if okb(r) else okb(r),
                bad(r) or f"{r['bit_errors']} / {r['n_data']} errors, counts {r['counts']}")


# ================================================================================================ gap 3
def gap3():
    import tile_verify as V
    C = V.cases()
    tags = sorted({n.rsplit('_', 1)[0] for n in C if n.startswith('pvt_')})
    for tag in tags:
        res = {k: jload(B / 'tile' / f'{tag}_{k}' / 'result.json') for k in ('op', 'k31', 'k0', 'set', 'rxs', 'tx', 'pu')}
        if all(v is None for v in res.values()):
            if not SMOKE:
                chk('gap 3 PVT', tag, None, 'pending')
            continue
        cn, tc, v = tag.split('_')[1], float(tag.split('_')[2]), float(tag.split('_')[3])
        p, det = [], []
        for k, r in res.items():
            if f'{tag}_{k}' not in C:
                continue
            b = bad(r)
            if b:
                p.append(f'{k}: {b}')
                continue
            if r.get('deck_temp') is not None and abs(r['deck_temp'] - tc) > 0.01:
                p.append(f"{k}: deck temp {r['deck_temp']} vs {tc}")
            if r.get('deck_vsa') is not None and abs(r['deck_vsa'] - v) > 0.01 * v:
                p.append(f"{k}: VAPWR {r['deck_vsa']} vs {v}")
        F = 433.92e6
        if res['k31'] and not bad(res['k31']):
            ok = res['k31']['f_a2'] > F
            det.append(f"k31 {res['k31']['f_a2'] / 1e6:.1f} MHz")
            if not ok:
                p.append('433.92 MHz above code 31')
        if res['k0'] and not bad(res['k0']):
            det.append(f"k0 {res['k0']['f_a2'] / 1e6:.1f} MHz")
            if not res['k0']['f_a2'] < F:
                p.append('433.92 MHz below code 0')
        if res['set'] and not bad(res['set']):
            ph = res['set']['lo_iq_phase']
            nominal = cn == 'tt' and tc == 27 and abs(v - 3.3) < 0.01
            lim = (69, 75) if nominal else (50, 110)
            det.append(f'I/Q LO {ph:.1f} deg')
            if not lim[0] <= ph <= lim[1]:
                p.append(f'I/Q LO {ph:.1f} deg outside {lim}')
        if res['rxs'] and not bad(res['rxs']):
            import tb_tile_verdict as TV
            TV.T.OUT = B / 'tile'
            TV.OUT = B / 'tile'
            r = res['rxs']
            need = 0.8 * 2 * r['f_bb_expect'] * 16e-6
            okr = (r['qi_edges'] >= need and r['qq_edges'] >= need and abs(r['f_qi'] / r['f_bb_expect'] - 1) < 0.15
                   and abs(r['f_qq'] / r['f_bb_expect'] - 1) < 0.15 and 50 <= abs(r['q_iq_phase']) <= 110
                   and r['q_iq_phase'] * r['bb_iq_phase'] > 0)
            det.append(f"RX -95 dBm q_i / q_q {r['f_qi'] / 1e3:.0f} / {r['f_qq'] / 1e3:.0f} kHz, I/Q {r['q_iq_phase']:+.1f} deg")
            if not okr:
                p.append(f"RX -95 dBm: edges {r['qi_edges']} / {r['qq_edges']}, f {r['f_qi'] / 1e3:.0f} / {r['f_qq'] / 1e3:.0f} "
                         f"kHz for {r['f_bb_expect'] / 1e3:.0f}, I/Q {r['q_iq_phase']:+.1f} (bb {r['bb_iq_phase']:+.1f})")
        if res['tx'] and not bad(res['tx']):
            det.append(f"TX {res['tx']['p1_dbm']:+.2f} dBm")
            if not res['tx']['p1_dbm'] >= 3.0:
                p.append(f"TX {res['tx']['p1_dbm']:+.2f} dBm < +3")
        if res['pu'] and not bad(res['pu']):
            r = res['pu']
            det.append(f"starts {r['t_osc_us']} us")
            if r['t_osc_us'] is None or r['t_osc_us'] > 15 or not abs(r['f_end'] / r['f_ck_end'] / 4 - 1) < 2e-3:
                p.append(f"power-up: t_osc {r['t_osc_us']}, f / f(ck) {r['f_end'] / r['f_ck_end']:.3f}")
        pend = [k for k, r in res.items() if f'{tag}_{k}' in C and r is None]
        ok = False if p else (None if pend else True)
        chk('gap 3 PVT', tag, ok, '; '.join(p + det) + (f'; pending {pend}' if pend else ''))
    # mutations
    r = jload(B / 'tile' / 'mut_pvt_v300' / 'result.json')
    if r is None or bad(r):
        mut('gap 3 PVT', '3.45 V point run at 3.0 V: the supply check flags it', None if r is None else False, bad(r) or '')
    else:
        vn = r['case']['vnom']
        mut('gap 3 PVT', '3.45 V point run at 3.0 V: the supply check flags it',
            abs(r['deck_vsa'] - vn) > 0.01 * vn or abs(r.get('vap_mean', vn) - vn) > 0.01 * vn,
            f"deck VAPWR {r['deck_vsa']}, measured {r.get('vap_mean', float('nan')):.3f} V vs {vn}")
    r = jload(B / 'tile' / 'mut_pvt_notemp' / 'result.json')
    mut('gap 3 PVT', '70 C not passed to the deck: the temperature check flags it', None if r is None else
        (r.get('deck_temp') is not None and abs(r['deck_temp'] - r['case']['temp']) > 0.01),
        '' if r is None else f"deck temp {r.get('deck_temp')} vs case {r['case']['temp']}")


# ================================================================================================ gap 4
def gap4():
    lv_set = (6,) if SMOKE else (-10, 0, 6)
    for lv in lv_set:
        r = jload(B / 'chain' / f'rate_tt_{lv}' / 'result.json')
        chk('gap 4 overload', f'{lv:+d} dBm at the RX pins: every LNA / mixer device within 3.63 V', okb(r) and r['n_over'] == 0
            if okb(r) else okb(r), bad(r) or f"{r['n_over']} over; worst {r['worst'][0]}; inp {r['inp_min']:.2f} ... {r['inp_max']:.2f} V")
    r = jload(B / 'chain' / 'rate_tt_6_vdd4.5' / 'result.json')
    mut('gap 4 overload', 'LNA / mixer at 4.5 V: the rating check flags it', None if okb(r) is None else
        (okb(r) and r['n_over'] > 0), bad(r) or f"{r['n_over']} devices over")
    ref = jload(B / 'chain' / 'bbrec_tt_-95_0ms' / 'result.json')
    chk('gap 4 overload', 'baseband bench, no burst: decodes from the start (split-bench sanity)',
        okb(ref) and ref.get('t_rec') is not None and ref.get('rec_after_ref_ms', 9) < 0.2 if okb(ref) else okb(ref),
        bad(ref) or f"recovered {ref.get('rec_after_ref_ms')} ms after the start")
    for lv in (-10, 0, 6):
        r = jload(B / 'chain' / f'bbrec_tt_{lv}_1ms' / 'result.json')
        ok = okb(r)
        if ok:
            ok = r.get('rec_after_ref_ms') is not None and r['rec_after_ref_ms'] <= 2.0
        chk('gap 4 overload', f'{lv:+d} dBm burst of 1 ms, then -95 dBm FSK: decodes within 2 ms', ok,
            bad(r) or f"recovery {r.get('rec_after_ref_ms')} ms after the burst ({r.get('why', '')})")
    r = jload(B / 'chain' / 'bbrec_tt_-10_1ms_burston' / 'result.json')
    mut('gap 4 overload', 'burst left on: no recovery may be found', None if okb(r) is None else
        (okb(r) and r.get('t_rec') is None), bad(r) or f"t_rec {r.get('t_rec')}")
    t = jload(B / 'tile' / 'txrx_c_tt' / 'result.json')
    chk('gap 4 overload', 'tile TX on (RX off) then TX off / rx_en on: run clean, LNA pins within the rails during TX',
        okb(t) and -0.5 < t['ua4_min_tx'] and t['ua4_max_tx'] < 3.8 if okb(t) else okb(t),
        bad(t) or f"LNA input {t['lna_in_pp_tx_mv']:.1f} mV p-p during TX, VAPWR ripple {t['vap_ripple_tx_mv']:.1f} mV, "
        f"mixer offset I {t['bi_off_mv_before']:.2f} -> {t['bi_off_mv_after']:.2f} mV, stage-1 nodes vs settled "
        f"{ {k[-12:]: round(v, 1) for k, v in (t['s1_vs_settled_mv'] or {}).items()} } mV")
    r = jload(B / 'chain' / 'bbrec_tt_txrx' / 'result.json')
    import tile_verify as V
    fw = V.FW_WAIT_MS
    ok = okb(r)
    if ok:
        ok = r.get('rec_after_ref_ms') is not None and r['rec_after_ref_ms'] <= fw
    chk('gap 4 overload', f'TX -> RX: -95 dBm decodes within the firmware wait ({fw} ms after rx_en)', ok,
        bad(r) or f"recovery {r.get('rec_after_ref_ms')} ms after rx_en")
    mut('gap 4 overload', 'firmware wait set to 0 ms: the turnaround check fails', None if not okb(r) or r.get('rec_after_ref_ms') is None
        else r['rec_after_ref_ms'] > 0.0, '' if not r else f"recovery {r.get('rec_after_ref_ms')} ms > 0")


# ================================================================================================ gap 5
def gap5():
    r = jload(B / 'coupling' / 'budget.json')
    if r is None or 'error' in r:
        chk('gap 5 coupling', 'q_i / q_q -> baseband coupling within budget', None if r is None else False,
            '' if r is None else r['error'])
    else:
        w = r['worst'][0] if r['worst'] else {}
        chk('gap 5 coupling', 'every extracted q_i / q_q coupling into the baseband within its budget', r['pass'],
            f"{r['n_in_baseband']} couplings into baseband nets of {r['n_couplings']}; tightest {w.get('net')} "
            f"{w.get('c_f', 0) * 1e18:.0f} aF vs budget {w.get('budget_f', 0) * 1e18:.0f} aF (margin {w.get('margin', 0):.1f}x); "
            f"min budget {r['min_budget'] * 1e18:.0f} aF")
    m = jload(B / 'coupling' / 'budget_mut.json')
    mut('gap 5 coupling', '10 x budget cap from q_i to the most sensitive node: the budget check fails',
        None if m is None else (m.get('pass') is False), '' if m is None else f"pass={m.get('pass')}")
    t = jload(B / 'tile' / 'rx0_c_tt' / 'result.json')
    chk('gap 5 coupling', 'tile, settled, no RF input: the limiters do not toggle', okb(t) and t['q_i_edges'] == 0 and
        t['q_q_edges'] == 0 if okb(t) else okb(t), bad(t) or f"edges q_i / q_q {t['q_i_edges']} / {t['q_q_edges']} in "
        f"{t['window_us']:.0f} us; baseband p-p I / Q {t['oi_pp'] * 1e3:.0f} / {t['oq_pp'] * 1e3:.0f} mV")
    t = jload(B / 'tile' / 'mut_rx0_ccoup' / 'result.json')
    if t is not None or not SMOKE:
        mut('gap 5 coupling', 'tile: 10 x budget cap q_i -> most sensitive node: the no-input run toggles',
            None if okb(t) is None else (okb(t) and t['q_i_edges'] + t['q_q_edges'] > 0), bad(t) or
            f"edges {t['q_i_edges']} / {t['q_q_edges']}")


def main():
    existing()
    for g in (gap1, gap2, gap3, gap4, gap5, gap6):
        try:
            g()
        except Exception as e:  # noqa: BLE001
            chk(g.__name__, 'verdict code', False, f'{type(e).__name__}: {e}')
    L = ['# Full verification: verdict', '', f'Generated by sim/verify/verdict.py{" (smoke set)" if SMOKE else ""}.', '',
         '| Area | Check | Status | Detail |', '|---|---|---|---|']
    L += [f"| {c['area']} | {c['check']} | {c['status']} | {c['detail'].replace('|', '/')} |" for c in CHECKS]
    L += ['', '| Area | Mutation (planted error) | Status | Detail |', '|---|---|---|---|']
    L += [f"| {m['area']} | {m['mutation']} | {m['status']} | {m['detail'].replace('|', '/')} |" for m in MUTS]
    cnt = {k: sum(1 for c in CHECKS if c['status'] == k) for k in ('PASS', 'FAIL', 'pending')}
    mc = {k: sum(1 for m in MUTS if m['status'] == k) for k in ('caught', 'MISSED', 'pending')}
    L += ['', f"Checks: {cnt['PASS']} PASS, {cnt['FAIL']} FAIL, {cnt['pending']} pending. "
              f"Mutations: {mc['caught']} caught, {mc['MISSED']} missed, {mc['pending']} pending."]
    B.mkdir(parents=True, exist_ok=True)
    name = 'verdict_smoke' if SMOKE else 'verdict'
    (B / f'{name}.md').write_text('\n'.join(L) + '\n')
    (B / f'{name}.json').write_text(json.dumps(dict(checks=CHECKS, mutations=MUTS, counts=cnt, mut_counts=mc), indent=1))
    print('\n'.join(L))


if __name__ == '__main__':
    main()
