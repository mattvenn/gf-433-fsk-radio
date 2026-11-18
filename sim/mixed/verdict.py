#!/usr/bin/env python3
"""PASS / FAIL per check of the mixed-signal co-simulation, from the run outputs (build/mixed/<run>/result.json,
written by sim/mixed/analyse.py). Prints one line per check and corner and writes build/mixed/verdict.json.

    python3 sim/mixed/verdict.py [--corners tt,ss,ff]
    python3 sim/mixed/verdict.py --mutants     # also: the checks on the mutant runs must FAIL (exit 1 if one passes)
    python3 sim/mixed/verdict.py --step step_tt_bswap --sd sd_tt_sdinv --corners tt   # any run set by hand

Checks (per corner; "ref" = the same analog with ideal control lines, sim/mixed/gen_mixed.py ref_*, i.e. the
sim/tune/mdac_sim.py / phase_c.py bench; frequencies from a0's mid-swing crossings):
  runs        every run finished (t_end = tstop), log free of singular / timestep too small / Transient op started
  spi_decode  the SPI writes reach the DAC lines: words 512 -> 513 -> 700 (step run), 512 (SD run), thermometer
              contiguous, dbg_sel = 8 after the third write
  f_word      f at each word within TOL_F of the ref (512, 513, 700)
  step        f(700) - f(512) > 0 and within TOL_STEP (relative) of the ref's
  lsb         f(513) - f(512) within TOL_LSB (relative) of the ref's
  sd_bits     the RTL's SD cell line, sampled every clk, is sd_model.sd1(64) bit for bit (mean exactly 1/4)
  sd_base     SD run, before SD_EN: f(512) within TOL_F of the step run's (the SD cell is off)
  sd_mean     SD running: mean f strictly between f(512) and f(513) of the mixed runs, and within TOL_F of the ref
              driven by the sd1(64) bitstream
  vctrl       DBG_SEL = 8 closes the vctrl debug switch: vctrl within TOL_V of the ref, f up and within TOL_FV of the ref
  rx_en       CTRL[4] reaches rx_en (0 / 3.3 V at the boundary) and rx_bias: nb > 0.5 V and enb < 0.1 V when on,
              nb < 0.05 V and enb > 3.2 V when off; also set in the SD run by CTRL = 0x11
  dbg_sel     each DBG_SEL bit closes its own switch only: ua[0] within TOL_UA of that switch's input, nothing
              else on; with none on ua[0] is not driven (< 0.1 V at the start, decaying at the end)
  miso        reading ID (address 7) returns 0x433
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "sim/tune"))
import sd_model  # noqa: E402

OUT = REPO / "build/mixed"
TOL_F = 3e3          # Hz: same word, mixed against ref (about 0.1 LSB)
TOL_STEP = 0.01      # relative, a 188-LSB step
TOL_LSB = 0.10       # relative, a 1-LSB step (about 3 kHz)
TOL_V = 0.010        # V, vctrl through the debug switch
TOL_FV = 1e-3        # relative, f with the vctrl override
TOL_UA = 0.03        # relative, ua[0] against the selected input
VDD = 3.3


def load(name):
    p = OUT / name / "result.json"
    return json.loads(p.read_text()) if p.exists() else None


def fseg(r, word, dbg=(0, 0, 0, 0), sd=False):
    """The mixed run's segment with this word / dbg_sel / SD state that has a frequency."""
    for s in r["segments"]:
        if s["word"] == word and tuple(s["dbg_sel"]) == tuple(dbg) and bool(s["sd_edges"]) == sd and s.get("fm"):
            return s
    return None


class V:
    def __init__(self):
        self.rows = []

    def add(self, check, corner, ok, msg):
        self.rows.append(dict(check=check, corner=corner, ok=bool(ok), msg=msg))
        print(f"{'PASS' if ok else 'FAIL'}  {check:11s} {corner:3s} {msg}")
        return ok


def corner_checks(v, cn, step="step_{c}", sd="sd_{c}", io="io_{c}"):
    names = dict(step=step.format(c=cn), sd=sd.format(c=cn), io=io.format(c=cn),
                 **{f"ref_{k}": f"ref_{cn}_{k}" for k in ("w512", "w513", "w700", "sd64", "vctrl")})
    R = {k: load(n) for k, n in names.items()}
    miss = [names[k] for k, r in R.items() if r is None]
    bad = [names[k] for k, r in R.items() if r is not None and not r["ok"]]
    v.add("runs", cn, not miss and not bad, f"{len(R)} runs; missing {miss or '-'}; bad {bad or '-'}")
    if R["io"] and R["io"]["ok"]:
        io_checks(v, cn, R["io"], R["sd"])
    if miss:
        return
    st, sdr, io = R["step"], R["sd"], R["io"]
    fr = {k: R[f"ref_{k}"]["fm"]["f"] for k in ("w512", "w513", "w700", "sd64", "vctrl")}

    # spi_decode
    words = [s["word"] for s in st["segments"]]
    dbg_last = st["segments"][-1]["dbg_sel"]
    thermo = all(s["thermo_ok"] for r in (st, sdr, io) for s in r["segments"])
    seq = [w for i, w in enumerate(words) if i == 0 or w != words[i - 1]]
    v.add("spi_decode", cn, seq == [512, 513, 700] and dbg_last == [0, 0, 0, 1] and thermo
          and {s["word"] for s in sdr["segments"]} == {512},
          f"step-run words {seq}, dbg_sel at the end {dbg_last}, SD-run words {sorted({s['word'] for s in sdr['segments']})}, "
          f"thermometer contiguous {thermo}")

    s512, s513, s700 = fseg(st, 512), fseg(st, 513), fseg(st, 700)
    if not (s512 and s513 and s700):
        v.add("f_word", cn, False, "a word segment has no frequency")
        return
    f = {512: s512["fm"]["f"], 513: s513["fm"]["f"], 700: s700["fm"]["f"]}
    d = {w: f[w] - fr[f"w{w}"] for w in f}
    v.add("f_word", cn, all(abs(x) <= TOL_F for x in d.values()),
          "mixed - ref: " + ", ".join(f"{w}: {f[w] / 1e6:.4f} MHz ({x / 1e3:+.2f} kHz)" for w, x in d.items())
          + f"  (tol {TOL_F / 1e3:g} kHz)")
    dm, dr = f[700] - f[512], fr["w700"] - fr["w512"]
    v.add("step", cn, dm > 0 and abs(dm / dr - 1) <= TOL_STEP,
          f"512 -> 700: {dm / 1e6:+.4f} MHz, ref {dr / 1e6:+.4f} MHz ({(dm / dr - 1) * 100:+.2f} %, tol {TOL_STEP * 100:g} %); "
          f"{dm / 188 / 1e3:.2f} kHz/LSB")
    lm, lr = f[513] - f[512], fr["w513"] - fr["w512"]
    v.add("lsb", cn, lm > 0 and abs(lm / lr - 1) <= TOL_LSB,
          f"512 -> 513: {lm / 1e3:+.2f} kHz, ref {lr / 1e3:+.2f} kHz ({(lm / lr - 1) * 100:+.1f} %, tol {TOL_LSB * 100:g} %)")

    # SD
    ssd = fseg(sdr, 512, sd=True)
    b0 = fseg(sdr, 512, sd=False)
    bits = ssd.get("sd_bits") if ssd else None
    if bits:
        ref = list(sd_model.sd1(64, 8, len(bits) + 8))
        k0, r0 = bits.index(1), ref.index(1)
        n = min(len(bits) - k0, len(ref) - r0)
        same = bits[k0:k0 + n] == ref[r0:r0 + n]
        mean = float(np.mean(bits[k0:k0 + (n // 4) * 4]))
    v.add("sd_bits", cn, bool(bits) and same and mean == 0.25,
          f"{len(bits or [])} clocks sampled, match sd1(64) {bits and same}, mean {bits and mean}")
    v.add("sd_base", cn, b0 is not None and abs(b0["fm"]["f"] - f[512]) <= TOL_F,
          f"SD run before SD_EN: {b0['fm']['f'] / 1e6:.4f} MHz, step run {f[512] / 1e6:.4f} MHz "
          f"({(b0['fm']['f'] - f[512]) / 1e3:+.2f} kHz)" if b0 else "no segment")
    if ssd:
        fs = ssd["fm"]["f"]
        frac = (fs - f[512]) / (f[513] - f[512])
        fracr = (fr["sd64"] - fr["w512"]) / (fr["w513"] - fr["w512"])
        v.add("sd_mean", cn, f[512] < fs < f[513] and abs(fs - fr["sd64"]) <= TOL_F,
              f"mean {fs / 1e6:.4f} MHz = 512 + {frac:.3f} LSB (ref bitstream run 512 + {fracr:.3f}, "
              f"{(fs - fr['sd64']) / 1e3:+.2f} kHz; ideal 0.25 + the SD cell's charge injection)")
    else:
        v.add("sd_mean", cn, False, "no SD segment")

    # vctrl override through dbg_sel[3]
    sv = fseg(st, 700, dbg=(0, 0, 0, 1))
    rv = R["ref_vctrl"]
    if sv:
        ok = (abs(sv["vctrl"] - rv["vctrl"]) <= TOL_V and sv["fm"]["f"] > f[700]
              and abs(sv["fm"]["f"] / fr["vctrl"] - 1) <= TOL_FV and sv["lv_dbg3"] > 0.99 * VDD)
        v.add("vctrl", cn, ok, f"dbg_sel[3] at {sv['lv_dbg3']:.3f} V: vctrl {sv['vctrl']:.4f} V (ref {rv['vctrl']:.4f}), "
              f"f {f[700] / 1e6:.3f} -> {sv['fm']['f'] / 1e6:.3f} MHz (ref {fr['vctrl'] / 1e6:.3f}, "
              f"{(sv['fm']['f'] / fr['vctrl'] - 1) * 1e6:+.0f} ppm)")
    else:
        v.add("vctrl", cn, False, "no segment with dbg_sel = 8")



def io_checks(v, cn, io, sdr):
    # rx_en
    ok, notes = True, []
    for s in io["segments"]:
        on = s["rx_en"]
        good = (abs(s["rx_en_a"] - (VDD if on else 0)) < 0.01 and
                ((s["nb"] > 0.5 and s["enb"] < 0.1) if on else (s["nb"] < 0.05 and s["enb"] > VDD - 0.1)))
        ok &= good
        notes.append(f"{'on' if on else 'off'}: nb {s['nb']:.3f} enb {s['enb']:.2f}")
    sd_rx = [s["rx_en"] for s in sdr["segments"]] if sdr and sdr["ok"] else [None, None]
    ok &= sd_rx[0] == 0 and sd_rx[-1] == 1
    on_states = [s["rx_en"] for s in io["segments"]]
    ok &= 1 in on_states and on_states[0] == 0 and on_states[-1] == 0
    uniq = sorted({n for n in notes})
    v.add("rx_en", cn, ok, "; ".join(uniq[:4]) + f"; SD run rx_en {sd_rx[0]} -> {sd_rx[-1]}")

    # dbg_sel
    mods = dict(io["meta"]["io_mods"])
    ok, notes = True, []
    for i, s in enumerate(io["segments"]):
        sel = s["dbg_sel"]
        lv_ok = all(abs(s[f"dbg_sel_{k}_a"] - (VDD if sel[k] else 0)) < 0.01 for k in range(4))
        if sum(sel) == 1:
            k = sel.index(1)
            src = ("oi_p", "oq_p", "nb", "vctrl")[k]
            want = s["nb"] if src == "nb" else mods[src]
            good = abs(s["ua0"] - want) <= TOL_UA * max(want, 0.1) and lv_ok
            notes.append(f"[{k}] {src}: ua0 {s['ua0']:.3f} V / {want:.3f}")
        elif sum(sel) == 0:
            good = lv_ok and ((s["ua0"] < 0.1) if i == 0 else (s["ua0_end"] < 0.5 * s["ua0"] or s["ua0"] < 0.1))
            notes.append(f"none: ua0 {s['ua0']:.3f} -> {s['ua0_end']:.3f} V")
        else:
            good = False
            notes.append(f"two on: {sel}")
        ok &= good
    seen = sorted({tuple(s["dbg_sel"]) for s in io["segments"]})
    ok &= all(tuple(int(j == k) for j in range(4)) in seen for k in range(4))
    v.add("dbg_sel", cn, ok, "; ".join(notes))
    mw = io.get("miso_words") or []
    v.add("miso", cn, len(mw) == 1 and mw[0]["value"] == 0x433,
          ", ".join(f"addr {m['addr']}: 0x{m['value']:03x}" for m in mw if m["value"] is not None))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corners", default="tt,ss,ff")
    ap.add_argument("--step", default="step_{c}")
    ap.add_argument("--sd", default="sd_{c}")
    ap.add_argument("--mutants", action="store_true")
    a = ap.parse_args()
    v = V()
    for cn in a.corners.split(","):
        corner_checks(v, cn, a.step, a.sd)
    nfail = sum(not r["ok"] for r in v.rows)
    print(f"== {'PASS' if not nfail else 'FAIL'}: {len(v.rows) - nfail} / {len(v.rows)} checks pass")
    out = dict(rows=v.rows, ok=not nfail)
    rc = 0 if not nfail else 1
    if a.mutants:
        out["mutants"] = []
        for name, (step, sd) in {"bswap (dac_bn[0] / dac_bn[1] crossed at the mdac)": ("step_tt_bswap", "sd_tt"),
                                 "sdinv (SD cell line inverted: fine-word sign flipped)": ("step_tt", "sd_tt_sdinv")}.items():
            print(f"-- mutant {name}: must FAIL")
            m = V()
            corner_checks(m, "tt", step, sd)
            failed = [r["check"] for r in m.rows if not r["ok"]]
            caught = bool(failed) and "runs" not in failed
            print(f"== mutant {name}: {'CAUGHT' if caught else 'MISSED'} (failing checks: {failed})")
            out["mutants"].append(dict(name=name, caught=caught, failed=failed))
            rc |= 0 if caught else 2
    (OUT / "verdict.json").write_text(json.dumps(out, indent=1))
    return rc


if __name__ == "__main__":
    sys.exit(main())
