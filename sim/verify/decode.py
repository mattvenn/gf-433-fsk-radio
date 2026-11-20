#!/usr/bin/env python3
"""Firmware-like decoding of the receiver's two comparator bits (q_i, q_q) for the verification checks.

The RP2350 PIO turns q_i / q_q into signed quadrant steps (rx_model.steps_b) and sums them per bit. Unlike
sim/rx/rx_chain.py fsk_analyse (which takes the sign and the bit timing from the data bits themselves: fine for a
noiseless check, biased for a bit-error count), the decoder here learns the bit timing and the sign from a known
preamble only, then decides the data bits with that timing and sign, as the firmware would.

    decode(t, qi, qq, bits, npre, t0, rate)       -> per-bit counts, errors on the data bits, sign, timing, glitches
    recovery(t, qi, qq, bits, t0, rate, t_ref)    -> the first bit start after which every bit decodes (and stays so)
"""
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'sim' / 'rx'))
import rx_model  # noqa: E402

FS = 8e6
VTH = 1.65


def xings(t, v, th, rising=True):
    a, b = v[:-1] - th, v[1:] - th
    i = np.where((a < 0) & (b >= 0))[0] if rising else np.where((a > 0) & (b <= 0))[0]
    return t[i] + (th - v[i]) * (t[i + 1] - t[i]) / (v[i + 1] - v[i])


def steps(t, qi, qq, t0=0.0, fs=FS):
    tu = np.arange(t0, t[-1], 1 / fs)
    return tu, rx_model.steps_b(np.interp(tu, t, qi) > VTH, np.interp(tu, t, qq) > VTH)


def glitches(t, v, t0, tmin=1e-6):
    """Comparator pulses shorter than tmin after t0 (a 100 kHz rotation gives 2.5 us between edges of one arm)."""
    m = t >= t0
    e = np.sort(np.concatenate([xings(t[m], v[m], VTH), xings(t[m], v[m], VTH, False)]))
    return int(np.sum(np.diff(e) < tmin))


def decode(t, qi, qq, bits, npre, t0, rate=50e3, fs=FS, dmax=0.5):
    """bits: every bit sent from t0 (preamble first); the first npre are the known preamble. The bit timing (a
    delay 0 ... dmax bits after the nominal edge) and the sign maximise the preamble's sign-weighted step sum.
    Bits whose window runs past the end of the run are not decided."""
    bits = np.asarray(bits)
    tu, st = steps(t, qi, qq, t0, fs)
    sps = int(round(fs / rate))
    nfit = int((len(st) - int(dmax * sps)) // sps)          # bits that fit for every delay tried
    nb = min(len(bits), nfit)
    if nb <= npre:
        return dict(error=f'run too short: {nb} whole bits, preamble {npre}')
    sp = np.where(bits[:npre] > 0, 1, -1)
    best = None
    for d in range(0, int(dmax * sps) + 1, max(1, sps // 40)):
        c = rx_model.counts(st, sps, nb, d)
        sc = float(np.sum(sp * c[:npre]))
        if best is None or abs(sc) > abs(best[0]):
            best = (sc, d, c)
    sc, d, c = best
    sign = 1 if sc >= 0 else -1
    dec = (sign * c[npre:]) > 0
    ref = bits[npre:nb] > 0
    errs = int(np.sum(dec != ref))
    return dict(counts=[int(x) for x in c], sign=sign, delay_us=d / fs * 1e6, preamble_score=sc,
                n_data=int(nb - npre), bit_errors=errs, errors_at=[int(k) for k in np.where(dec != ref)[0]],
                glitches=glitches(t, qi, t0) + glitches(t, qq, t0),
                min_abs_count=int(np.min(np.abs(c[npre:]))) if nb > npre else None)


def recovery(t, qi, qq, bits, t0, rate=50e3, fs=FS, t_ref=None, nlast=10, dmax=0.5):
    """Bits sent from t0 without a preamble: the timing and sign come from the last nlast bits (the receiver has
    recovered by then, or the result says it never did). Returns the start time of the first bit after which every
    bit decodes correctly (None: the last bits are not all correct, so there is no recovery in the run), and that time
    minus t_ref (the event: the end of a burst, rx_en rising)."""
    bits = np.asarray(bits)
    tu, st = steps(t, qi, qq, t0, fs)
    sps = int(round(fs / rate))
    nb = min(len(bits), int((len(st) - int(dmax * sps)) // sps))
    sp = np.where(bits[nb - nlast:nb] > 0, 1, -1)
    best = None
    for d in range(0, int(dmax * sps) + 1, max(1, sps // 40)):
        c = rx_model.counts(st, sps, nb, d)
        sc = float(np.sum(sp * c[nb - nlast:]))
        if best is None or abs(sc) > abs(best[0]):
            best = (sc, d, c)
    sc, d, c = best
    sign = 1 if sc >= 0 else -1
    ok = ((sign * c) > 0) == (bits[:nb] > 0)
    # the decoder also needs a clear count: |count| >= 3 of the nominal 8 steps per bit
    ok &= np.abs(c) >= 3
    r = dict(n_bits=int(nb), sign=sign, delay_us=d / fs * 1e6, counts=[int(x) for x in c], ok=[bool(x) for x in ok])
    if not ok[-nlast:].all():
        r.update(t_rec=None, rec_after_ref_ms=None, why='the last bits do not decode: no recovery in the run')
        return r
    bad = np.where(~ok)[0]
    k = int(bad[-1]) + 1 if len(bad) else 0
    r['t_rec'] = t0 + k / rate + d / fs
    r['first_good_bit'] = k
    if t_ref is not None:
        r['rec_after_ref_ms'] = (r['t_rec'] - t_ref) * 1e3
    return r
