#!/usr/bin/env python3
"""Mixed-signal co-simulation of the fine-tuning loop: the tx_fine RTL (src/tx_fine.v, verilated into
build/mixed/tx_fine.so by sim/mixed/build_so.sh) runs as an XSPICE d_cosim instance inside ngspice, next to the
transistor-level analog, so the loop is closed for real:

    SPI frames (PWL) -> adc_bridge -> tx_fine RTL -> dac_tn[30:0] / dac_bn[4:0] / dac_sdn -> dac_bridge (0 / 3.3 V)
      -> mdac (extracted layout, layout/pex/mdac_cm.spice) -> vg -> current-fed ring (schematic, sim/vco/vco_bias.py
         with the reference and RC filter, vbnf held at its DC value as in sim/tune/phase_c.py) -> f(a0)
    rx_en, dbg_sel[3:0] -> dac_bridge -> rx_bias / dbg_tg (the LVS source's transistor subcircuits)

The DAC lines are wired port by port as the tile's LVS source wires them (lvs/tt_um_mattvenn_gf433_vco.spice,
instance xxmdac), so a crossed line in the tile shows up here. The d_cosim port list is generated from the
inputs.h / outputs.h of the same build (as ook-asic-radio's sim/mixed/gen_mixed.py), so it can't drift from the .so.

Runs (one directory each under build/mixed/<name>/: deck.cir, deck.log, out.raw, out.vcd):
  step_<c>   SPI: MED_INT 512 (reset) -> 513 -> 700, then DBG_SEL = 8 with a 1.65 V bench source on ua[0]
             (vctrl override through the real dbg_tg switch)                      ring + DAC, 26 us
  sd_<c>     SPI: MED_FRAC = 64, then CTRL = SD_EN | RX_EN: the SD dithers the SD cell at fraction 1/4  19 us
  io_<c>     no ring: CTRL = RX_EN, DBG_SEL = 1 / 2 / 4 / 8, read ID, CTRL = 0, DBG_SEL = 0, with rx_bias and
             the four dbg_tg switches on ua[0]                                       62 us
  ref_<c>_<w512|w513|w700|sd64|vctrl>   the same analog with ideal control sources (the mdac_sim / phase_c bench):
             the prediction the mixed runs are checked against; sd64 drives the SD cell with sim/tune/sd_model.py's
             sd1(64) bitstream
  mutants (tt only): step_tt_bswap (dac_bn[0] / dac_bn[1] crossed at the mdac), sd_tt_sdinv (the SD cell's line
             inverted: the fine word's sign flipped). The verdict must FAIL on them.
Corners: tt / ss / ff at 27 C, VDD 3.3 V, coarse code (ui_in[4:0]) 9 / 11 / 7 (each corner's 433.92 MHz code on the
schematic ring, sim/tune/mdac_sim.py CODE433). Clock 25 MHz (d_osc), SCLK 2.5 MHz (clk / 10, as test/test_tx_fine.py).

    python3 sim/mixed/gen_mixed.py list
    python3 sim/mixed/gen_mixed.py run <name>      # write the deck, run ngspice, then sim/mixed/analyse.py
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "sim/tune"))
sys.path.insert(0, str(REPO / "sim/vco"))
sys.path.insert(0, str(REPO / "xschem/gen"))
import mdac_sim as ms  # noqa: E402
import sd_model  # noqa: E402
import vco_bias as vb  # noqa: E402

OUT = REPO / "build/mixed"
OBJ = OUT / "tx_fine_obj_dir"
LVS = REPO / "lvs/tt_um_mattvenn_gf433_vco.spice"
VDD = 3.3
FCLK = 25e6
TSCK = 400e-9                 # SPI clock period (clk / 10)
TFRAME = 7.8e-6               # one frame (19 SCLK periods) plus a gap
T0 = 0.507e-6                 # first frame starts (off the 20 ns clk-edge grid: an SPI edge on a clk edge stopped sd_ff on "timestep too small")
CORNERS = {"tt": ("typical", 9), "ss": ("ss", 11), "ff": ("ff", 7)}
TRISE = 100e-12               # d2a edges, as phase_c.py's PWL control lines
UA0_BENCH = 1.65              # bench source on ua[0] for the vctrl override (V, through 1 kOhm)
IO_MODS = dict(oi_p=0.3, oq_p=3.0, vctrl=1.65)   # io run: stand-in sources on the dbg_tg inputs (nb is rx_bias's)

# SPI programmes: (address, data, read)
PROG = {
    "step": [(0, 513, 0), (0, 700, 0), (5, 8, 0)],
    "sd":   [(1, 64, 0), (3, 0x11, 0)],
    "io":   [(3, 0x10, 0), (5, 1, 0), (5, 2, 0), (5, 4, 0), (5, 8, 0), (7, 0, 1), (3, 0, 0), (5, 0, 0)],
}
TSTOP = {"step": 26e-6, "sd": 19e-6, "io": 72e-6}
REF_TSTOP = {"w512": 3.5e-6, "w513": 3.5e-6, "w700": 3.5e-6, "sd64": 4.5e-6, "vctrl": 3.5e-6}
SD_FRAC = 64
MUTANTS = {"step_tt_bswap": "bswap", "sd_tt_sdinv": "sdinv"}


def names():
    n = [f"{k}_{c}" for c in CORNERS for k in ("step", "sd", "io")]
    n += [f"ref_{c}_{r}" for c in CORNERS for r in REF_TSTOP]
    return n + list(MUTANTS)


# ---------------------------------------------------------------- d_cosim ports (from the build's headers)
def ports(header):
    rx = re.compile(r"VL_DATA\(\d*,(\w+),(\d+),(\d+)\)")
    return [(m[1], int(m[2]), int(m[3])) for m in rx.finditer((OBJ / header).read_text())]


def bits(plist):
    """Node names, MSB first per bus (verilator_shim.cpp's order): dac_tn_30 ... dac_tn_0; scalars as is."""
    out = []
    for name, msb, lsb in plist:
        out += [name] if msb == lsb == 0 else [f"{name}_{i}" for i in range(msb, lsb - 1, -1)]
    return out


# ---------------------------------------------------------------- the tile's wiring (LVS source)
def subckt_text(name):
    txt = LVS.read_text().split("\n")
    out, on = [], False
    for ln in txt:
        t = ln.split()
        if t and t[0].lower() == ".subckt" and t[1] == name:
            on = True
        if on:
            out.append(ln)
            if t and t[0].lower() == ".ends":
                break
    assert out, name
    return "\n".join(out) + "\n"


def mdac_wiring():
    """{mdac port: d_cosim node}: the mdac instance's connections in the tile (xxmdac), its control ports only."""
    txt = LVS.read_text()
    hdr = re.search(r"^\.subckt mdac (.*)$", txt, re.M).group(1).split()
    inst = re.search(r"^xxmdac (.*) mdac$", txt, re.M).group(1).split()
    assert len(hdr) == len(inst), (hdr, inst)
    w = {}
    for p, n in zip(hdr, inst):
        m = re.fullmatch(r"(dac_tn|dac_bn)\[(\d+)\]", n)
        if m:
            w[p] = f"{m[1]}_{m[2]}"
        elif n == "dac_sdn":
            w[p] = "dac_sdn"
    assert len(w) == 37, w
    return w


def word_ports(word, sd=0):
    """{mdac port: 1 = cell on} for a 10-bit word, from mdac_sim.word_bits (s<i> -> ns<i>, b<i> -> nb<i>, sd -> nsd)."""
    st = ms.word_bits(word, sd)
    return {("n" + k): v for k, v in st.items() if k != "off"}


# ---------------------------------------------------------------- SPI stimulus
def spi_src(prog, path, t0=T0):
    """The digital stimulus as a d_source file (rst_n cs_n sclk mosi fsk ck): SPI mode 0, MSB first, 16 bits,
    as test/test_tx_fine.py xfer(). Digital events, not analog PWL + adc_bridge: PWL breakpoints next to the
    d_cosim events stopped two runs on "timestep too small" (2026-11-17). Returns the frame list."""
    # rst_n: 1 -> 0 at 10 ns -> 1 at 0.1 us. Starting at 0 gives the shim no negedge, so the RTL's asynchronous
    # reset only ran at clock edges (and the gated-clock flops depend on the clock gates' start state)
    st = dict(rst_n=1, cs_n=1, sclk=0, mosi=0)
    ev = [(0.0, dict(st)), (10e-9, dict(st, rst_n=0)), (0.1e-6, dict(st, rst_n=1))]
    st["rst_n"] = 1

    def put(t, **kw):
        st.update(kw)
        ev.append((t, dict(st)))
    frames = []
    for k, (addr, data, rd) in enumerate(prog):
        word = (0x8000 if rd else 0) | (addr << 12) | (data & 0xfff)
        t = t0 + k * TFRAME
        frames.append((t, addr, data, rd))
        put(t, cs_n=0)
        t += TSCK
        for i in range(15, -1, -1):
            put(t, mosi=(word >> i) & 1)
            put(t + TSCK / 2, sclk=1)
            put(t + TSCK, sclk=0)
            t += TSCK
        put(t + TSCK, cs_n=1)
    order = ("rst_n", "cs_n", "sclk", "mosi")
    lines = ["* t rst_n cs_n sclk mosi fsk ck (sim/mixed/gen_mixed.py)"]
    last = -1.0
    for t, v in ev:
        if t <= last:                      # same time: the later state wins
            lines.pop()
        lines.append(f"{t:.6e} " + " ".join(f"{v[n]}s" for n in order) + " 0s 0s")
        last = t
    Path(path).write_text("\n".join(lines) + "\n")
    return frames


# ---------------------------------------------------------------- analog
def hdr(corner):
    return ms.HDR.format(corner=corner)


def ring(corner, code):
    """Schematic ring + reference + RC filter (vco_bias), coarse code sources, vctrl pull-down, vbnf held, the
    extracted mdac (ports pb / mo / md brought out) on vg through the ammeter vam."""
    p = ms.base_p()
    body, ics = vb.netlist(p)
    src = "".join(f"vbit{b} bit{b} 0 {VDD if (code >> b) & 1 else 0}\nvbitb{b} bitb{b} 0 {0 if (code >> b) & 1 else VDD}\n"
                  for b in range(p["bits"]))
    rv = f"XRV vctrl 0 0 ppolyf_u_1k r_width=1e-6 r_length={ms.rv_length(ms.M['rv']):.2f}e-6\n"
    md = ms.mdac_netlist(p, ms.M, g=vb.gnet(p))
    hold = f"vhold vbnf 0 {ms.VBNF[corner]}\n"
    return f"vdd vdd 0 {VDD}\n{rv}{src}{body}{hold}vam vg vgo 0\n{md}", ics


RUN_DIR = OUT / "net"


def setup_pex():
    ms.PEX = "cm"
    ms.OUT = RUN_DIR                # pex_ports() writes its ported copy into the run's own directory (no race)


def tg_sub():
    return subckt_text("dbg_tg") + subckt_text("rx_bias")


# ---------------------------------------------------------------- decks
def mixed_deck(kind, cn, mut=None):
    corner, code = CORNERS[cn]
    ins, outs = bits(ports("inputs.h")), bits(ports("outputs.h"))
    assert set(ins) == {"clk", "rst_n", "ck", "sclk", "mosi", "cs_n", "fsk"}, ins
    frames = spi_src(PROG[kind], RUN_DIR / "stim.txt")
    L = [f"* mixed-signal tx_fine + analog, {kind} {cn}{' mutant ' + mut if mut else ''} (sim/mixed/gen_mixed.py)",
         hdr(corner).rstrip(), tg_sub()]
    L += ["* ---- digital: the RTL; port list from inputs.h / outputs.h (MSB first per bus)",
          f"adut [ {' '.join(ins)} ] [ {' '.join(outs)} ] null dut",
          f'.model dut d_cosim simulation="{OUT / "tx_fine.so"}"',
          "aclk 0 clk clock",
          f".model clock d_osc cntl_array=[-1 1] freq_array=[{FCLK:g} {FCLK:g}]",
          f".model d2a dac_bridge(out_low=0 out_high={VDD} t_rise={TRISE:g} t_fall={TRISE:g})",
          ".model dinv d_inverter(rise_delay=1p fall_delay=1p)",
          "astim [rst_n cs_n sclk mosi fsk ck] stim",
          f'.model stim d_source(input_file="{RUN_DIR / "stim.txt"}")',
          "amiso [miso] [miso_a] d2a",
          "arxen [rx_en] [rx_en_a] d2a"]
    L += [f"adbg{i} [dbg_sel_{i}] [dbg_sel_{i}_a] d2a" for i in range(4)]
    vcd = ["clk", "rst_n", "sclk", "mosi", "cs_n", "miso", "rx_en", "dac_sdn"] + [f"dbg_sel_{i}" for i in range(4)] + \
          [f"dac_tn_{i}" for i in range(31)] + [f"dac_bn_{i}" for i in range(5)]
    if kind == "io":
        save = "v(ua0) v(nb) v(enb) v(rx_en_a) v(miso_a) " + " ".join(f"v(dbg_sel_{i}_a)" for i in range(4))
        L += ["* ---- analog: rx_bias on rx_en, the four debug switches onto ua[0] (stand-in sources on their inputs)",
              f"vdd vdd 0 {VDD}",
              "xrxb vdd 0 rx_en_a enb nb rx_bias"]
        L += [f"V{k} {k} 0 {v}" for k, v in IO_MODS.items()]
        L += [f"xdbg{i} vdd 0 dbg_sel_{i}_a {m} ua0 dbg_tg" for i, m in enumerate(("oi_p", "oq_p", "nb", "vctrl"))]
        L += ["Rua ua0 0 1Meg", "Cua ua0 0 2p",
              ".option temp=27", ".control", f"save {save}",
              f"tran 1n {TSTOP[kind]:g} 0 2n"]
    else:
        setup_pex()
        an, ics = ring(corner, code)
        w = mdac_wiring()
        if mut == "bswap":
            w["nb0"], w["nb1"] = w["nb1"], w["nb0"]
        L += ["* ---- digital -> analog: the 37 DAC lines, wired as the tile's xxmdac instance"]
        for port, node in sorted(w.items()):
            if mut == "sdinv" and port == "nsd":
                L += [f"ainvsd {node} {node}_inv dinv", f"a_{port} [{node}_inv] [{port}] d2a"]
            else:
                L += [f"a_{port} [{node}] [{port}] d2a"]
        L += ["* ---- analog: ring + reference + filter (schematic), mdac (extracted, C only)", an.rstrip(),
              "* debug switch dbg_sel[3]: vctrl onto ua[0], with a bench source on ua[0]",
              f"xdbgv vdd 0 dbg_sel_3_a vctrl ua0 dbg_tg", f"Vua ua0s 0 {UA0_BENCH}", "Rua ua0s ua0 1k", "Cua ua0 0 2p",
              f".ic {ics}", ".option temp=27", ".control",
              "save v(a0) v(vg) v(mo) v(vctrl) v(ua0) v(nsd) v(nb0) v(nb1) v(ns16) v(ns17) v(rx_en_a) v(dbg_sel_3_a)",
              f"tran 5p {TSTOP[kind]:g} 0 5p"]
    L += ["set filetype=binary", "write out.raw", f"eprvcd {' '.join(vcd)} > out.vcd", "quit", ".endc", ".end"]
    return "\n".join(L) + "\n", frames


def ref_deck(cn, r):
    corner, code = CORNERS[cn]
    setup_pex()
    an, ics = ring(corner, code)
    word = {"w512": 512, "w513": 513, "w700": 700, "sd64": 512, "vctrl": 700}[r]
    ctl = word_ports(word)
    L = [f"* reference (ideal control lines) {r} {cn} (sim/mixed/gen_mixed.py)", hdr(corner).rstrip(), tg_sub(), an.rstrip()]
    for port, on in sorted(ctl.items()):
        if port == "nsd" and r == "sd64":
            bitsq = sd_model.sd1(SD_FRAC, 8, int(REF_TSTOP[r] * FCLK) + 2)
            L.append(f"vc_{port} {port} 0 " + pwl_bits(list(bitsq), 0.5e-6))
        else:
            L.append(f"vc_{port} {port} 0 {0 if on else VDD}")
    L += [f"Vsel3 sel3 0 {VDD if r == 'vctrl' else 0}", "xdbgv vdd 0 sel3 vctrl ua0 dbg_tg",
          f"Vua ua0s 0 {UA0_BENCH}", "Rua ua0s ua0 1k", "Cua ua0 0 2p",
          f".ic {ics}", ".option temp=27", ".control", "save v(a0) v(vg) v(mo) v(vctrl) v(nsd)",
          f"tran 5p {REF_TSTOP[r]:g} 0 5p", "set filetype=binary", "write out.raw", "quit", ".endc", ".end"]
    return "\n".join(L) + "\n"


def pwl_bits(bitsq, t0, tclk=1 / FCLK):
    """Active-low PWL of a bitstream from t0, one bit per clock (phase_c.pwl_bits)."""
    lv = lambda b: 0.0 if b else VDD
    pts, prev = [(0.0, lv(0))], 0
    for k, b in enumerate(bitsq):
        t = t0 + k * tclk
        if b != prev:
            pts += [(t, lv(prev)), (t + TRISE, lv(b))]
            prev = b
    return "PWL(" + " ".join(f"{t:.4e} {v:g}" for t, v in pts) + ")"


def write(name):
    global RUN_DIR
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    RUN_DIR = d
    (d / ".spiceinit").write_text("set ng_nomodcheck\nset num_threads=1\noption noinit\n")
    meta = {"name": name}
    if name.startswith("ref_"):
        _, cn, r = name.split("_")
        txt = ref_deck(cn, r)
        meta.update(kind="ref", corner=cn, ref=r, tstop=REF_TSTOP[r])
    else:
        base = name if name not in MUTANTS else name.rsplit("_", 1)[0]
        kind, cn = base.split("_")
        txt, frames = mixed_deck(kind, cn, MUTANTS.get(name))
        meta.update(kind=kind, corner=cn, mut=MUTANTS.get(name), tstop=TSTOP[kind],
                    frames=[dict(t=t, addr=a, data=dt, read=rd) for t, a, dt, rd in frames])
    meta.update(fclk=FCLK, tsck=TSCK, sd_frac=SD_FRAC, ua0_bench=UA0_BENCH, io_mods=IO_MODS)
    (d / "deck.cir").write_text(txt)
    import json
    (d / "meta.json").write_text(json.dumps(meta, indent=1))
    return d


def run(name):
    d = write(name)
    for f in ("out.raw", "out.vcd", "result.json"):
        (d / f).unlink(missing_ok=True)
    t = time.time()
    subprocess.run(["bash", "-c", f"cd {d} && ngspice -b deck.cir > deck.log 2>&1"], check=False)
    (d / "runtime.txt").write_text(f"{time.time() - t:.0f}\n")
    # ngspice can exit 1 at the d_cosim teardown after a complete run: judge by the files (analyse.py)
    r = subprocess.run([sys.executable, str(REPO / "sim/mixed/analyse.py"), str(d)])
    sys.exit(r.returncode)


if __name__ == "__main__":
    if sys.argv[1] == "list":
        print("\n".join(names()))
    elif sys.argv[1] == "write":
        for n in sys.argv[2:] or names():
            print("wrote", write(n) / "deck.cir")
    elif sys.argv[1] == "run":
        run(sys.argv[2])
