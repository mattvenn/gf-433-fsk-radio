#!/usr/bin/env python3
"""Analyse one sim/mixed run directory (build/mixed/<name>/) -> result.json (+ trace.npz for the plots).

Ring runs (mixed and reference): f(a0) from mid-swing rising crossings (the ring swings vg..VDD, so the level is
(min + max) / 2 of a0 in each window, never VDD / 2). Mixed runs: the digital outputs come from out.vcd (eprvcd of
the d_cosim nodes); the run is cut into segments at every change of the 36 array lines (dac_tn / dac_bn), dbg_sel
or rx_en; within a segment the word is decoded from the lines (active low) and f is the mean over
[segment start + SETTLE, segment end - 0.1 us]. The SD segment is the one where dac_sdn toggles.
Log check: the run is bad if the log has 'singular', 'timestep too small' or 'Transient op started'
(sim policy), or the raw is missing / short.

    python3 sim/mixed/analyse.py build/mixed/<name>
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools"))
from rawread import read_raw  # noqa: E402

SETTLE = 1.0e-6        # after a DAC word change (the extracted mo node settles with tau about 0.4 us)
REF_T0 = 1.5e-6        # reference runs: measure from here to tstop
START = 4.0e-6         # mixed runs, first segment: the ring and mo settle by about 3 us (the DAC lines start from
                       # the d_cosim reset state; the reference runs, with ideal lines, are settled by 1.5 us)
BAD = ("singular", "timestep too small", "transient op started")


def read_vcd(path):
    """{name: [(t_s, value)]} for scalar wires."""
    ids, ev, t, unit = {}, {}, 0.0, 1e-12
    scale = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9, "ps": 1e-12, "fs": 1e-15}
    for ln in Path(path).read_text().splitlines():
        if ln.startswith("$timescale"):          # ngspice picks 1 ps or 1 fs depending on the run
            p = ln.split()
            unit = int(p[1]) * scale[p[2]]
        elif ln.startswith("$var"):
            p = ln.split()
            ids[p[3]] = p[4]
            ev[p[4]] = []
        elif ln.startswith("#"):
            t = int(ln[1:]) * unit
        elif ln and ln[0] in "01xXzZ" and ln[1:] in ids:
            ev[ids[ln[1:]]].append((t, ln[0]))
    return ev


def value_at(evs, t):
    v = None
    for te, x in evs:
        if te <= t:
            v = x
        else:
            break
    return v


def crossings(t, v, lvl):
    i = np.where((v[:-1] < lvl) & (v[1:] >= lvl))[0]
    return t[i] + (lvl - v[i]) / (v[i + 1] - v[i]) * (t[i + 1] - t[i])


def fmean(t, a0, t0, t1):
    s = (t >= t0) & (t <= t1)
    lvl = 0.5 * (a0[s].min() + a0[s].max())
    tc = crossings(t[s], a0[s], lvl)
    if len(tc) < 10:
        return None
    return dict(f=(len(tc) - 1) / (tc[-1] - tc[0]), n=len(tc) - 1, t0=t0, t1=t1, lvl=lvl,
                amin=float(a0[s].min()), amax=float(a0[s].max()))


def log_check(d):
    lg = (d / "deck.log").read_text(errors="replace") if (d / "deck.log").exists() else ""
    bad = [w for w in BAD if w in lg.lower()]
    return dict(log_bad=bad, log_tail=lg.strip().splitlines()[-3:] if lg else ["missing"],
                done="ngspice-47 done" in lg or "binary raw file" in lg)


def main(d):
    d = Path(d)
    meta = json.loads((d / "meta.json").read_text())
    res = dict(name=meta["name"], meta=meta, **log_check(d))
    if not (d / "out.raw").exists():
        res["ok"] = False
        res["error"] = "no out.raw"
        (d / "result.json").write_text(json.dumps(res, indent=1))
        return 1
    p = read_raw(d / "out.raw")[0]
    V = p["vars"]
    t = np.real(V[p["scale"]])
    V = {k.lower(): np.real(x) for k, x in V.items()}
    res["t_end"] = float(t[-1])
    res["ok"] = (not res["log_bad"]) and t[-1] >= 0.999 * meta["tstop"]
    tr = {}
    if meta["kind"] == "ref":
        res["fm"] = fmean(t, V["v(a0)"], REF_T0, t[-1])
        s = t >= REF_T0
        res["vg"] = float(V["v(vg)"][s].mean())
        res["vctrl"] = float(V["v(vctrl)"][s].mean())
        if meta["ref"] == "sd64":
            res["sd_bits"] = None
    else:
        ev = read_vcd(d / "out.vcd")
        res["vcd_names"] = len(ev)
        lines = [f"dac_tn_{i}" for i in range(31)] + [f"dac_bn_{i}" for i in range(5)] + \
                [f"dbg_sel_{i}" for i in range(4)] + ["rx_en"]
        cuts = sorted({round(te, 12) for n in lines for te, _ in ev[n] if te > 0})
        edges = [0.0] + cuts + [float(t[-1])]
        segs = []
        for a, b in zip(edges[:-1], edges[1:]):
            if b - a < 0.2e-6:
                continue
            tm = 0.5 * (a + b)
            tn = [value_at(ev[f"dac_tn_{i}"], tm) for i in range(31)]
            bn = [value_at(ev[f"dac_bn_{i}"], tm) for i in range(5)]
            seg = dict(t_start=a, t_end=b,
                       tn_on=[i for i in range(31) if tn[i] == "0"],
                       bn_on=[i for i in range(5) if bn[i] == "0"],
                       dbg_sel=[int(value_at(ev[f"dbg_sel_{i}"], tm) == "1") for i in range(4)],
                       rx_en=int(value_at(ev["rx_en"], tm) == "1"))
            hi = len(seg["tn_on"])
            seg["thermo_ok"] = seg["tn_on"] == list(range(hi))
            seg["word"] = (hi << 5) | sum(1 << b for b in seg["bn_on"])
            sd_ev = [(te, x) for te, x in ev["dac_sdn"] if a <= te < b]
            seg["sd_edges"] = len(sd_ev)
            seg["sd_on_static"] = int(value_at(ev["dac_sdn"], tm) == "0") if not sd_ev else None
            m0 = max(a + SETTLE, START)
            if meta["kind"] != "io" and b - 0.1e-6 - m0 > 0.5e-6:
                s = (t >= m0) & (t <= b - 0.1e-6)
                if seg["sd_edges"]:      # SD running: from its first edge + SETTLE
                    m0 = max(m0, sd_ev[0][0] + SETTLE)
                seg["fm"] = fmean(t, V["v(a0)"], m0, b - 0.1e-6)
                for k in ("vg", "mo", "vctrl", "ua0"):
                    seg[k] = float(V[f"v({k})"][s].mean())
                # levels at the digital / analog boundary (the d2a outputs into the mdac / dbg_tg)
                seg["lv_nsd"] = [float(V["v(nsd)"][s].min()), float(V["v(nsd)"][s].max())]
                seg["lv_dbg3"] = float(V["v(dbg_sel_3_a)"][s].mean())
                if seg["sd_edges"]:
                    seg["sd_bits"] = sd_bits(ev, sd_ev[0][0], b, meta["fclk"])
            if meta["kind"] == "io":
                m0 = a + 0.5 * (b - a)
                s = (t >= m0) & (t <= b - 0.05e-6)
                for k in ("ua0", "nb", "enb", "rx_en_a") + tuple(f"dbg_sel_{i}_a" for i in range(4)):
                    seg[k] = float(V[f"v({k})"][s].mean())
                seg["ua0_end"] = float(V["v(ua0)"][s][-1])
            segs.append(seg)
        res["segments"] = segs
        if meta["kind"] == "io":
            res["miso_words"] = miso_words(ev, meta)
        # traces for the plot: per-period f (decimated), vg, mo
        if meta["kind"] != "io":
            a0 = V["v(a0)"]
            s = t > 1.0e-6
            lvl = 0.5 * (a0[s].min() + a0[s].max())
            tc = crossings(t[s], a0[s], lvl)
            tr = dict(tc=tc)
            k = max(1, len(t) // 20000)
            tr.update(t=t[::k], vg=V["v(vg)"][::k], mo=V["v(mo)"][::k], vctrl=V["v(vctrl)"][::k])
        else:
            k = max(1, len(t) // 20000)
            tr = dict(t=t[::k], ua0=V["v(ua0)"][::k], nb=V["v(nb)"][::k], enb=V["v(enb)"][::k])
    if meta["kind"] == "ref":
        a0 = V["v(a0)"]
        s = t > 1.0e-6
        lvl = 0.5 * (a0[s].min() + a0[s].max())
        tr = dict(tc=crossings(t[s], a0[s], lvl))
    np.savez_compressed(d / "trace.npz", **tr)
    (d / "result.json").write_text(json.dumps(res, indent=1, default=float))
    print(d.name, "ok" if res["ok"] else "BAD", res.get("log_bad"), f"t_end {t[-1]:.3e}")
    return 0 if res["ok"] else 1


def sd_bits(ev, t0, t1, fclk):
    """dac_sdn sampled half a clock after each clk rising edge from t0 (1 = cell on, active low)."""
    clk = [te for te, x in ev["clk"] if x == "1" and t0 - 1 / fclk <= te < t1 - 1 / fclk]
    return [int(value_at(ev["dac_sdn"], te + 0.5 / fclk) == "0") for te in clk]


def miso_words(ev, meta):
    """For each read frame: the 12 data bits of MISO sampled at SCLK rising edges 5..16."""
    out = []
    rises = [te for te, x in ev["sclk"] if x == "1"]
    for fr in meta["frames"]:
        if not fr["read"]:
            continue
        r = [te for te in rises if fr["t"] <= te < fr["t"] + 17 * meta["tsck"]]
        b = [int(value_at(ev["miso"], te) == "1") for te in r[4:16]]
        out.append(dict(addr=fr["addr"], bits=len(b), value=int("".join(map(str, b)), 2) if b else None))
    return out


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
