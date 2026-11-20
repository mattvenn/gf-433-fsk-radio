#!/usr/bin/env python3
"""The receiver model (sim/rx/rx_model.py) with the measured receiver (sim/rx/rx_model_meas.py, 'measured tt'), as the
verification checks use it: BER at 50 kbit/s with per-arm comparator offsets / hysteresis / gain and I/Q phase
(gap 1: the Monte Carlo spread into a sensitivity spread; gaps 2 / 6: the BER a bit-error count is judged against).

All levels are antenna dBm; offsets and hysteresis are given in mV at the comparator input and referred to the model's
noise units through the noise rms at the comparator (sim/rx/results/budget.json, tt: 100 mV for 7.27 dB).
"""
import json
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / 'sim' / 'rx'))
import rx_model_meas as MM  # noqa: E402  (patches rx_model's chain_b / noise_rms with the measured filter)
import rx_model as m  # noqa: E402

RATE, DEV, FS = 50e3, 100e3, 8e6


@lru_cache(None)
def meas():
    """(params, nf_db, hyst_ratio, noise_at_comparator_mV, hysteresis_mV) of the measured tt receiver."""
    cs, tt, worst, ph = MM.cases()
    c = cs['measured tt']
    p = dict(m.B_DEF, **c['over'])
    return p, float(c['nf_db']), float(c['hyst']), float(tt.get('noise_cmp_mv', tt.get('vn_cmp_mv', 100.0))), \
        float(tt.get('hyst_mv', 36.1))


def ber(level, nf_db=None, nbits=4000, seed=0, vos=(0.0, 0.0), hyst_mv=None, gq=1.0, dphi=None, rate=RATE):
    """BER of the measured receiver at `level` dBm. vos: comparator offsets I, Q (mV); hyst_mv: per-arm hysteresis
    (mV, default the measured one); gq: Q / I gain ratio; dphi: 90 - I/Q phase (deg)."""
    p, nf0, hr, ncmp, h0 = meas()
    nf = nf0 if nf_db is None else nf_db
    p = dict(p)
    if dphi is not None:
        p['dphi'] = dphi
    pd = dict(p, dc=0.0)
    d = m.delay('B', FS, rate, pd, DEV)
    nrms = m.noise_rms('B', FS, pd, nf0)          # model units of 1 noise rms at the comparator (nominal NF)
    k = nrms / ncmp                                # model units per mV at the comparator
    hm = (hyst_mv if hyst_mv is not None else (h0, h0))
    h = (hm[0] * k, hm[1] * k) if not np.isscalar(hm) else (hm * k, hm * k)
    vi, vq = vos[0] * k, vos[1] * k
    sps = int(round(FS / rate))
    rng = np.random.default_rng(seed)
    err = tot = 0
    per = max(50, m.MAX_SAMPLES // sps - m.NPRE - m.NPOST)
    while tot < nbits:
        nb = min(per, nbits - tot)
        bits = rng.integers(0, 2, nb + m.NPRE + m.NPOST)
        x, _ = m.rx_input(bits, rate, FS, level, nf, rng, dev=DEV)
        i, q = m.chain_b(x, FS, **p)
        st = m.steps_b(m.schmitt(i - vi, h[0]), m.schmitt(q * gq - vq, h[1]))
        c = m.counts(st, sps, nb, m.NPRE * sps + d).astype(float)
        err += int(np.sum((c > c.mean()) != (bits[m.NPRE:m.NPRE + nb] > 0)))
        tot += nb
    return err / tot


def sens(target=1e-2, lo=-118.0, hi=-95.0, tol=0.25, **kw):
    """Level (dBm) where the BER crosses target (bisection, common random numbers)."""
    while hi - lo > tol:
        mid = 0.5 * (lo + hi)
        if ber(mid, **kw) > target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def binom_p(k, n, p):
    """(P[X >= k], P[X <= k]) for X ~ Binomial(n, p)."""
    from scipy.stats import binom
    return float(binom.sf(k - 1, n, p)), float(binom.cdf(k, n, p))


if __name__ == '__main__':
    print(meas())
    for lv in (-100, -103, -105, -108, -110, -112):
        print(lv, ber(lv, nbits=4000))


def sig_cmp_mv(level, rate=RATE):
    """Amplitude (mV, per arm) of a noiseless FSK signal at `level` dBm at the comparator input, through the measured
    filter, in the units where the noise at the comparator is noise_cmp_mV rms (budget.json)."""
    p, nf0, hr, ncmp, h0 = meas()
    pd = dict(p, dc=0.0)
    rng = np.random.default_rng(3)
    bits = rng.integers(0, 2, 40)
    x, _ = m.rx_input(bits, rate, FS, level, None, rng, dev=DEV, pn=False)
    i, q = m.chain_b(x, FS, **pd)
    i = i[len(i) // 4:]
    return float(np.sqrt(2) * np.std(i) / m.noise_rms('B', FS, pd, nf0) * ncmp)
