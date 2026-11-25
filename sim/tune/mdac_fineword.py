#!/usr/bin/env python3
"""Fine-word monotonicity of the medium DAC with the sigma-delta (ΣΔ) cell, from the Monte Carlo logs.

The fine word is F = 256·w + f (w the 10-bit DAC word, f the 8-bit ΣΔ fraction). Its mean output is
I(w) + (f/256)·I_sd. Inside a word every step adds I_sd/256 > 0, so the only places it can fall are the word
boundaries: going from (w, 255) to (w+1, 0) changes the mean by step(w) − (255/256)·I_sd, which is negative whenever
a DAC step is smaller than 255/256 of the ΣΔ cell. A Lean proof (circuit-design-learnings/lean/MediumDac.lean,
fine_boundary) shows the worst case allows this unless every unit is within ±U/16383; this script measures how often
it happens in the Monte Carlo samples.

Input: the per-seed ngspice logs of `mdac_sim.py mc` (build/tx_fine/mdac/mc_<corner>/s<seed>.log: lines
"IW <w> <I>" for w = 0..1023, and "SD0 <I>" / "SD1 <I>", the output with the ΣΔ cell off / on at word 512).

    python3 sim/tune/mdac_fineword.py [--corners typical,ss,ff] [--dir build/tx_fine/mdac]
    python3 sim/tune/mdac_fineword.py --selftest      # synthetic data: must report 0, then the injected violations

Output: a summary per corner on stdout and build/tx_fine/mdac/fineword_<corner>.json.
"""
import argparse, json, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
# fine-DAC LSB in kHz of ring frequency, extracted ring + extracted DAC (STATUS.md / docs/tx_fine_tune.md)
LSB_KHZ = {"typical": 31.1, "ss": 27.4, "ff": 35.6}


def parse(log):
    iw = [float(i) for i in re.findall(r"^IW \S+ (\S+)$", log, re.M)]     # in word order, as mdac_sim.py reads them
    sd0 = re.search(r"^SD0 (\S+)$", log, re.M)
    sd1 = re.search(r"^SD1 (\S+)$", log, re.M)
    if len(iw) != 1024 or not sd0 or not sd1:
        return None
    return iw, float(sd1.group(1)) - float(sd0.group(1))


def analyse(iw, isd):
    """Per sample: the word boundaries where the fine word falls, and by how much (in LSB)."""
    lsb = (iw[1023] - iw[0]) / 1023
    drops = []
    for w in range(1023):
        d = (iw[w + 1] - iw[w]) - (255 / 256) * isd        # change of the mean from (w, 255) to (w+1, 0)
        if d < 0:
            drops.append((w, -d / lsb))
    worst = max((x for _, x in drops), default=0.0)
    return dict(lsb=lsb, sd_lsb=isd / lsb, n_drops=len(drops), worst_drop_lsb=worst,
                drop_words=[w for w, _ in drops], major_carry_drops=sum(1 for w, _ in drops if w % 32 == 31))


def summarise(corner, rows):
    n = len(rows)
    hit = [r for r in rows if r["n_drops"] > 0]
    counts = sorted(r["n_drops"] for r in rows)
    worst = max((r["worst_drop_lsb"] for r in rows), default=0.0)
    khz = LSB_KHZ.get(corner)
    s = dict(corner=corner, n=n, samples_with_drop=len(hit), frac_with_drop=len(hit) / n if n else None,
             median_drops=counts[n // 2] if n else None, max_drops=counts[-1] if n else None,
             worst_drop_lsb=worst, worst_drop_khz=worst * khz if khz else None,
             drops_at_major_carries=sum(r["major_carry_drops"] for r in rows), total_drops=sum(counts),
             sd_lsb_range=(min(r["sd_lsb"] for r in rows), max(r["sd_lsb"] for r in rows)) if n else None)
    print(f"{corner}: N={n}; samples with a falling word boundary {len(hit)}/{n}"
          + (f" ({100 * len(hit) / n:.1f} %)" if n else "")
          + f"; drops per sample median {s['median_drops']}, max {s['max_drops']}; worst drop {worst:.3f} LSB"
          + (f" ({worst * khz:.1f} kHz)" if khz else "")
          + f"; {s['drops_at_major_carries']} of {s['total_drops']} drops at a major carry (w % 32 == 31)")
    return s


def selftest():
    """Ideal DAC (steps exactly 1 LSB, cell exactly 1 LSB): no drops. Then shrink three steps: they must be found."""
    iw = [1e-9 * w for w in range(1024)]
    r = analyse(iw, 1e-9)
    assert r["n_drops"] == 0, r
    bad = list(iw)
    for w, step in ((31, 0.24), (511, 0.5), (700, 0.999)):       # 0.999 > 255/256: must NOT count
        delta = (1 - step) * 1e-9
        bad = [x - delta if i > w else x for i, x in enumerate(bad)]
    r = analyse(bad, 1e-9)
    assert r["drop_words"] == [31, 511], r
    assert abs(r["worst_drop_lsb"] - (255 / 256 - 0.24) * 1e-9 / r["lsb"]) < 1e-6, r
    print("selftest OK: ideal DAC has no drops; injected steps of 0.24 and 0.5 LSB found at words 31 and 511; "
          "a 0.999 LSB step (above 255/256) correctly not counted")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corners", default="typical,ss,ff")
    ap.add_argument("--dir", default=str(REPO / "build/tx_fine/mdac"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        return
    for corner in a.corners.split(","):
        d = Path(a.dir) / f"mc_{corner}"
        rows, bad = [], []
        for lg in sorted(d.glob("s*.log")):
            p = parse(lg.read_text(errors="replace"))
            if p is None:
                bad.append(lg.name)
                continue
            rows.append(dict(seed=lg.stem, **analyse(*p)))
        if bad:
            print(f"{corner}: {len(bad)} incomplete logs skipped: {', '.join(bad[:5])}", file=sys.stderr)
        if not rows:
            print(f"{corner}: no complete logs in {d}", file=sys.stderr)
            continue
        s = summarise(corner, rows)
        (Path(a.dir) / f"fineword_{corner}.json").write_text(json.dumps(dict(summary=s, rows=rows), indent=1))


if __name__ == "__main__":
    main()
