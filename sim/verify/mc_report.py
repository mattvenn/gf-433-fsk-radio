#!/usr/bin/env python3
"""Gap 1: the Monte Carlo samples (sim/verify/chain_x.py mc, build/verify/chain/mc_*/result.json) -> checks and the
model's sensitivity spread (sim/verify/rxm.py) -> build/verify/chain/mc_report.json.

Per sample (extracted blocks, 'pex'): comparator offset + hysteresis against half the -105 dBm signal at the
comparator (rxm.sig_cmp_mv); the stage-1 output offset (the only DC-coupled stage, so the only one the LO start-up
offset and mismatch can push towards a rail once the high-pass has settled) under 0.5 V of its +-2 V range; the
model's sensitivity (BER 1e-3 at 10 kbit/s, as Table VII of docs/rx_design.md) with the sample's comparator offsets,
hysteresis, I/Q gain ratio and phase, within 3 dB of the same model with no mismatch. Each must hold for >= 99 % of
the samples per corner. The mismatch-off sample is the nominal reference (I/Q conversion phase, gains).
Mutation checks: the mismatch-off run must show no spread (and a 'spread' check run on mismatch-off copies of the
samples fails); the 'merge' runs must be flagged by the static unit-instance check and their stage-1 offset spread
must differ from the unit-instance runs (F-test, p < 0.01).

    python3 sim/verify/mc_report.py [--nsens N]
"""
import argparse
import json
import sys
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import rxm  # noqa: E402

D = REPO / 'build' / 'verify' / 'chain'
S1_MAX = 0.5          # V
SENS_DB = 3.0
YIELD = 0.99


def load(pattern):
    out = []
    for p in sorted(D.glob(pattern + '/result.json')):
        try:
            out.append(json.loads(p.read_text()))
        except ValueError:
            pass
    return out


def sens_one(args):
    kw = args
    return rxm.sens(target=1e-3, lo=-118, hi=-100, tol=0.25, rate=10e3, nbits=10000, **kw)


def model_kw(r, nom):
    dph = (r['conv_phase'] - nom['conv_phase']) + (r['bb_dphase'] - nom['bb_dphase'])
    p0 = rxm.meas()[0]['dphi']
    return dict(vos=(r['vos_i_mv'], r['vos_q_mv']), hyst_mv=(r['hyst_i_mv'], r['hyst_q_mv']),
                gq=(r['conv_gq'] * r['bb_gq']) / (nom['conv_gq'] * nom['bb_gq']), dphi=p0 - dph)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--nsens', type=int, default=0, help='samples per corner for the sensitivity (0 = all)')
    a = ap.parse_args()
    lim = 0.5 * rxm.sig_cmp_mv(-105)
    rep = dict(cmp_limit_mv=lim, s1_max_v=S1_MAX, sens_db=SENS_DB, corners={})
    for cn in ('tt', 'ss', 'ff'):
        rs = [r for r in load(f'mc_pex_{cn}_s*') if not r.get('mut')]
        nom = load(f'mc_pex_{cn}_s1_mmoff')
        if not rs or not nom:
            rep['corners'][cn] = dict(status='pending', n=len(rs))
            continue
        nom = nom[0]
        bad = [r['name'] for r in rs if 'error' in r or r['flags']]
        ok = [r for r in rs if 'error' not in r and not r['flags']]
        c = dict(n=len(rs), n_bad_runs=len(bad), bad_runs=bad[:10])
        cm = [max(abs(r['vos_i_mv']) + r['hyst_i_mv'], abs(r['vos_q_mv']) + r['hyst_q_mv']) for r in ok]
        s1 = [max(abs(r['s1_i_off_v']), abs(r['s1_q_off_v'])) for r in ok]
        c['cmp_worst_mv'] = float(max(cm))
        c['cmp_yield'] = float(np.mean(np.array(cm) <= lim))
        c['s1_worst_v'] = float(max(s1))
        c['s1_yield'] = float(np.mean(np.array(s1) < S1_MAX))
        for k in ('vos_i_mv', 'hyst_i_mv', 'mix_i_off_mv', 's1_i_off_v', 'conv_gq', 'conv_phase', 'bb_gq', 'bb_dphase',
                  'lna_i_off_mv'):
            v = np.array([r[k] for r in ok])
            c[k] = dict(mean=float(v.mean()), std=float(v.std(ddof=1)) if len(v) > 1 else 0.0, min=float(v.min()),
                        max=float(v.max()))
        c['nominal'] = {k: nom.get(k) for k in ('vos_i_mv', 'hyst_i_mv', 'mix_i_off_mv', 's1_i_off_v', 'conv_gq',
                                                 'conv_phase', 'bb_gq', 'bb_dphase')}
        c['merged_fets'] = sorted({tuple(x) for r in ok for x in r['merged_fets']})
        # sensitivity: the nominal (no mismatch) and each sample, same seeds
        sub = ok if not a.nsens else ok[:a.nsens]
        kws = [{}] + [model_kw(r, nom) for r in sub]
        with Pool(8) as p:
            sv = p.map(sens_one, kws)
        c['sens_nominal'] = sv[0]
        d = np.array(sv[1:]) - sv[0]
        c['sens_delta_db'] = dict(max=float(d.max()), mean=float(d.mean()), n=len(d))
        c['sens_yield'] = float(np.mean(d <= SENS_DB))
        c['pass'] = (not bad) and c['cmp_yield'] >= YIELD and c['s1_yield'] >= YIELD and c['sens_yield'] >= YIELD \
            and not c['merged_fets']
        rep['corners'][cn] = c
    # mutation 1: mismatch off -> no spread. The spread check (std of the comparator offset > 0.01 mV) on the
    # samples, and on the mismatch-off run repeated (its offsets are the same whatever the seed: one value)
    tt = [r for r in load('mc_pex_tt_s*') if not r.get('mut') and 'error' not in r]
    off = load('mc_pex_*_s1_mmoff')
    sp = float(np.std([r['vos_i_mv'] for r in tt])) if len(tt) > 1 else None
    rep['spread_check'] = dict(std_vos_i_mv=sp, pass_=sp is not None and sp > 0.01)
    offv = [r.get('vos_i_mv') for r in off if 'error' not in r]
    rep['mut_mmoff'] = dict(vos_i_mv=offv, spread=float(np.std(offv)) if offv else None,
                            caught=bool(offv) and all(abs(v) < 0.01 for v in offv))
    # mutation 2: merged stage-1 fingers: the static check must flag them; the stage-1 offset spread changes
    mg = [r for r in load('mc_pex_tt_s*_merge') if 'error' not in r]
    if mg and len(tt) > 2:
        from scipy.stats import f as fdist
        a1 = np.array([r['s1_i_off_v'] for r in tt])
        a2 = np.array([r['s1_i_off_v'] for r in mg])
        F = a2.var(ddof=1) / a1.var(ddof=1)
        p = float(2 * min(fdist.sf(F, len(a2) - 1, len(a1) - 1), fdist.cdf(F, len(a2) - 1, len(a1) - 1)))
        rep['mut_merge'] = dict(n=len(mg), flagged=all(r['merged_fets'] for r in mg), std_unit=float(a1.std(ddof=1)),
                                std_merged=float(a2.std(ddof=1)), f_ratio=float(F), p=p,
                                caught=all(r['merged_fets'] for r in mg))
    else:
        rep['mut_merge'] = dict(n=len(mg), caught=None)
    sch = [r for r in load('mc_sch_tt_s*') if 'error' not in r]
    if sch:
        rep['sch_extra'] = {k: dict(mean=float(np.mean([r[k] for r in sch])), std=float(np.std([r[k] for r in sch], ddof=1)))
                            for k in ('vos_i_mv', 'mix_i_off_mv', 's1_i_off_v', 'conv_phase')}
        rep['sch_extra']['n'] = len(sch)
    (D / 'mc_report.json').write_text(json.dumps(rep, indent=1, default=float))
    print(json.dumps(rep, indent=1, default=float))


if __name__ == '__main__':
    main()
