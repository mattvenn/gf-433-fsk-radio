"""What the fine word's falling boundaries and gaps mean for tuning (docs/tx_fine_tune.md, note after Table III).

Reads the per-seed Monte Carlo logs of `mdac_sim.py mc` (build/tx_fine/mdac/mc_<corner>/s*.log), like
mdac_fineword.py, and reports per corner:
  - falling boundaries by size: samples with a drop > 0.1 / 0.25 / 0.5 LSB, and the largest drop below a major carry;
  - coverage: each word w reaches [I(w), I(w) + 255/256 I_cell] through the ΣΔ fraction. The union of those intervals
    over all 1024 words is what the fine word can reach. The rest of the range is gaps. For random targets, the tuning
    error is the distance to the nearest reachable current, in kHz. The coarse code is held, so a gap that a
    neighbouring coarse code would cover still counts (pessimistic).

    python3 sim/tune/mdac_coverage.py [--corners typical,ss,ff] [--dir build/tx_fine/mdac]
"""
import argparse, glob, random, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mdac_fineword import parse, LSB_KHZ, REPO  # noqa: E402


def sample(iw, isd):
    lsb = (iw[1023] - iw[0]) / 1023
    drops = []                                              # (size in LSB, carry level)
    for w in range(1023):
        d = -((iw[w + 1] - iw[w]) - 255 / 256 * isd) / lsb
        if d > 0:
            drops.append((d, (w ^ (w + 1)).bit_length() - 1))
    merged = []
    for a, b in sorted((iw[w], iw[w] + 255 / 256 * isd) for w in range(1024)):
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    gaps = [(merged[i][1] / lsb, merged[i + 1][0] / lsb) for i in range(len(merged) - 1)]
    return lsb, drops, gaps, merged[0][0] / lsb, merged[-1][1] / lsb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--corners", default="typical,ss,ff")
    ap.add_argument("--dir", default=str(REPO / "build/tx_fine/mdac"))
    ap.add_argument("--targets", type=int, default=2000, help="random targets per sample")
    a = ap.parse_args()
    rng = random.Random(1)
    for c in a.corners.split(","):
        khz = LSB_KHZ[c]
        rows = [p for p in (parse(open(f).read()) for f in sorted(glob.glob(f"{a.dir}/mc_{c}/s*.log"))) if p]
        n = len(rows)
        big = {t: 0 for t in (0.1, 0.25, 0.5)}
        minor_worst = 0.0
        gap_frac, chip_worst, errs = [], [], []
        for iw, isd in rows:
            lsb, drops, gaps, lo, hi = sample(iw, isd)
            for t in big:
                big[t] += any(d > t for d, _ in drops)
            minor_worst = max([minor_worst] + [d for d, lvl in drops if lvl < 5])
            gap_frac.append(sum(b - x for x, b in gaps) / (hi - lo))
            chip_worst.append(max(((b - x) / 2 for x, b in gaps), default=0.0) * khz)
            for _ in range(a.targets):
                t = rng.uniform(lo, hi)
                errs.append(next((min(t - x, b - t) for x, b in gaps if x < t < b), 0.0) * khz)
        errs.sort(); chip_worst.sort()
        q = lambda p: errs[int(p * len(errs)) - 1]
        print(f"{c}: N={n}; samples with a falling boundary > 0.1 / 0.25 / 0.5 LSB: "
              f"{big[0.1]} / {big[0.25]} / {big[0.5]}; largest drop below a major carry {minor_worst:.3f} LSB")
        print(f"{c}: gaps {100 * sum(gap_frac) / n:.1f} % of the range; targets in a gap "
              f"{100 * sum(e > 0 for e in errs) / len(errs):.1f} %; tuning error p99 {q(0.99):.2f} kHz, "
              f"max {errs[-1]:.1f} kHz; worst error per chip median {chip_worst[n // 2]:.1f}, max {chip_worst[-1]:.1f} kHz")


if __name__ == "__main__":
    main()
