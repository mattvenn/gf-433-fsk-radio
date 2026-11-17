#!/usr/bin/env python3
"""Figure for sim/mixed/results.md: docs/img/mixed/mixed_<corner>.png from build/mixed (run analyse.py first).

    python3 sim/mixed/plot_mixed.py [tt]

(a) step run: the ring frequency against time (mean over 100 periods) as the SPI writes MED_INT 512 -> 513 -> 700
    and then DBG_SEL = 8 (vctrl override); dashed: the reference runs (ideal control lines).
(b) SD run: f - f(512) in kHz, mean over each SD period (4 clocks = 160 ns) once SD_EN is set, with the levels of
    words 512 and 513 and the mean.
(c) io run: ua[0] and the receiver bias nb as RX_EN and the DBG_SEL bits are written.
"""
import json
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
B = REPO / "build/mixed"
IMG = REPO / "docs/img/mixed"
C1, C2, GREY, INK, INK2 = "#2a78d6", "#eb6834", "#8a8984", "#0b0b0b", "#52514e"


def res(n):
    return json.loads((B / n / "result.json").read_text())


def frames(ax, meta, lab=True):
    for fr in meta["frames"]:
        ax.axvspan(fr["t"] * 1e6, (fr["t"] + 17 * meta["tsck"]) * 1e6, color="#e8e7e3", lw=0, zorder=0)


def main(cn="tt"):
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": GREY, "axes.labelcolor": INK2, "xtick.color": INK2,
                         "ytick.color": INK2, "axes.spines.top": False, "axes.spines.right": False})
    fig, ax = plt.subplots(1, 3, figsize=(14, 4.2), gridspec_kw=dict(width_ratios=[1.25, 1, 1.25]))
    # (a)
    st = res(f"step_{cn}")
    tc = np.load(B / f"step_{cn}" / "trace.npz")["tc"]
    k = 100
    n = (len(tc) - 1) // k
    tm = 0.5 * (tc[0:n * k:k] + tc[k:n * k + 1:k])
    fm = k / (tc[k:n * k + 1:k] - tc[0:n * k:k])
    frames(ax[0], st["meta"])
    ax[0].plot(tm * 1e6, fm / 1e6, color=C1, lw=1.5, label="mixed (RTL + transistors)")
    for r, w in (("w512", "512"), ("w513", "513"), ("w700", "700"), ("vctrl", "700 + vctrl")):
        f = res(f"ref_{cn}_{r}")["fm"]["f"] / 1e6
        ax[0].axhline(f, color=GREY, ls="--", lw=1, zorder=1)
        ax[0].text(0.3, f, f" {w}", color=INK2, va="bottom", fontsize=8)
    ax[0].set_ylim(fm[tm > 1.5e-6].min() / 1e6 - 1.5, fm.max() / 1e6 + 1.5)
    ax[0].set_xlabel("time (µs); grey bands: SPI frames")
    ax[0].set_ylabel("ring frequency (MHz)")
    ax[0].set_title("(a) SPI writes MED_INT, then DBG_SEL = 8", fontsize=9, color=INK, loc="left")
    ax[0].legend(frameon=False, loc="center right", fontsize=8)
    # (b)
    sd = res(f"sd_{cn}")
    seg = [s for s in sd["segments"] if s["sd_edges"]][0]
    f512 = [s for s in st["segments"] if s["word"] == 512 and s.get("fm")][0]["fm"]["f"]
    f513 = [s for s in st["segments"] if s["word"] == 513 and s.get("fm")][0]["fm"]["f"]
    tcs = np.load(B / f"sd_{cn}" / "trace.npz")["tc"]
    tp = 40e-9                                 # one clk: the per-clock dither is visible
    t0 = seg["t_start"] + 0.2e-6
    edges = np.arange(t0, tcs[-1], tp)
    cnt = np.interp(edges, tcs, np.arange(len(tcs)))      # fractional cycle count at each edge
    fp = np.diff(cnt) / tp
    tq = edges[:-1] + tp / 2
    pre = (tcs > 2e-6) & (tcs < seg["t_start"] - 0.1e-6)
    e2 = np.arange(tcs[pre][0], tcs[pre][-1], tp)
    c2 = np.interp(e2, tcs, np.arange(len(tcs)))
    ax[1].plot((e2[:-1] + tp / 2) * 1e6, (np.diff(c2) / tp - f512) / 1e3, color=C1, lw=1, alpha=0.5)
    ax[1].plot(tq * 1e6, (fp - f512) / 1e3, color=C1, lw=1)
    fs = seg["fm"]["f"]
    ref = res(f"ref_{cn}_sd64")["fm"]["f"] - res(f"ref_{cn}_w512")["fm"]["f"]
    for y, lab, c in ((0, "word 512", GREY), ((f513 - f512) / 1e3, "word 513", GREY),
                      ((fs - f512) / 1e3, f"SD mean +{(fs - f512) / 1e3:.1f} kHz", C1),
                      (ref / 1e3, f"ref, sd1 bitstream +{ref / 1e3:.1f}", C2)):
        ax[1].axhline(y, color=c, ls="--", lw=1)
        below = c == C2
        ax[1].text(2.2, y + (-1.0 if below else 0.5), lab, color=INK2, va="top" if below else "bottom", fontsize=8)
    ax[1].axvline(seg["t_start"] * 1e6, color=GREY, lw=0.8)
    ax[1].set_ylim(-15, 50)
    ax[1].set_xlim(2, sd["t_end"] * 1e6)
    ax[1].set_xlabel("time (µs); SD_EN set at the line")
    ax[1].set_ylabel("f - f(512) (kHz), mean per 40 ns clock")
    ax[1].set_title("(b) MED_FRAC = 64: the SD dithers word 512 / 513", fontsize=9, color=INK, loc="left")
    # (c)
    io = res(f"io_{cn}")
    z = np.load(B / f"io_{cn}" / "trace.npz")
    frames(ax[2], io["meta"])
    ax[2].plot(z["t"] * 1e6, z["ua0"], color=C1, lw=1.5, label="ua[0]")
    ax[2].plot(z["t"] * 1e6, z["nb"], color=C2, lw=1.5, label="nb (receiver bias)")
    for s in io["segments"]:
        x = 0.5 * (s["t_start"] + s["t_end"]) * 1e6
        ax[2].text(x, 3.75, "on" if s["rx_en"] else "off", ha="center", fontsize=7, color=INK2)
        ax[2].text(x, 3.45, "".join(map(str, s["dbg_sel"][::-1])), ha="center", fontsize=7, color=INK2)
    ax[2].text(-1, 3.75, "RX_EN", ha="right", fontsize=7, color=INK2)
    ax[2].text(-1, 3.45, "DBG_SEL", ha="right", fontsize=7, color=INK2)
    ax[2].set_ylim(-0.1, 4.0)
    ax[2].set_yticks([0, 1, 2, 3])
    ax[2].set_xlabel("time (µs)")
    ax[2].set_ylabel("V")
    ax[2].set_title("(c) RX_EN and DBG_SEL[3:0] on the analog side", fontsize=9, color=INK, loc="left", pad=16)
    ax[2].legend(frameon=False, loc="center right", fontsize=8)
    fig.tight_layout()
    IMG.mkdir(parents=True, exist_ok=True)
    out = IMG / f"mixed_{cn}.png"
    fig.savefig(out, dpi=130)
    print("wrote", out)


if __name__ == "__main__":
    main(*(sys.argv[1:] or ["tt"]))
