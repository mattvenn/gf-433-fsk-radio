# Digital verification: the pinout, the tile on its pins, formal and equivalence

[![Made with Claude](https://img.shields.io/badge/Made%20with-Claude-D97757?logo=anthropic&logoColor=white)](https://claude.com/claude-code)

This page covers the checks on the digital side of the 433 MHz radio tile (`tt_um_mattvenn_gf433_vco`, a Tiny
Tapeout (TT) 2x2 analog tile on GF180MCU): the one digital macro `tx_fine` (`src/tx_fine.v`, the serial peripheral
interface (SPI) register file, the frequency-shift keying (FSK) offset, the sigma-delta (SD) modulator, the medium
digital-to-analog converter (DAC) lines, the clock dividers and the debug-switch enables) and the wiring between the
TT pins, the macro and the analog blocks. The approach is copied from the ook-asic-radio project. The checks and this
page were written by Claude (Claude Code). Each check was mutation-tested: a bug is planted in a temporary copy of
the design, and the check must fail on it.

**Table I.** The checks.

| Check | What it covers | Command | Result (2026-11-17) | Mutants caught |
|---|---|---|---|---|
| Pinout | `info.yaml` labels, the layout versus schematic (LVS) source's TT-pin nets, the macro ↔ analog nets, uio_oe ties, the macro's pins in RTL / LEF / gate-level (GL) netlist / LVS source | `python3 tools/check_pinout.py` | OK, 0 errors | 8 / 8 |
| Macro cocotb (existing) | `tx_fine` on its own: SPI, reset values, FSK, saturation, SD against `sim/tune/sd_model.py`, dividers, clock gating, RX_EN / DBG_SEL | `cd test && make TB=macro` (`GL=1`) | 7 / 7 pass, RTL and GL | (6 / 6 in `docs/tile_layout.md`) |
| TT-level cocotb | the whole tile through its TT pins, wired from the LVS source, analog blocks as stubs | `cd test && make TB=tt` (`GL=1`) | 6 / 6 pass, RTL and GL | 7 / 7 |
| Formal (`prove`) | six safety properties of the RTL for all time | `cd formal && sby -f tx_fine.sby prove` | PASS (PDR, about 1.5 min) | 6 / 6 |
| Formal (`gates`) | the clock-gated RTL equals the RTL with every gate replaced by a wire | `sby -f tx_fine.sby gates` (`gates_bmc`) | not proven for all time: PDR still open after 25 min; bounded check PASS to 60 steps (30 clk cycles) | 2 / 2 |
| Formal (`dbg`, `long`) | two expected failures, kept as records (below) | `sby -f tx_fine.sby dbg` / `long` | FAIL as expected | - |
| Equivalence (eqy) | RTL vs the shipped netlist `macro/tx_fine/nl/tx_fine.nl.v`, every input, plus a clock / reset source check | `bash formal/eqy/run.sh` | equivalent: 71 / 71 partitions, clocks 170 / 170 | 5 / 5 |

`cd test && make` runs both cocotb benches (RTL), `make GL=1` both on the GL netlist. Each run takes a few seconds.
`bash test/mutations.sh` and `bash formal/mutate.sh` repeat the mutation tests.

## Pinout check

`tools/check_pinout.py` holds one table, `PINOUT`, that says what each TT pin is: its `info.yaml` label and the block
ports its net must reach. The script checks it against:
- **`info.yaml`:** every pinout label equals the table's; `analog_pins` (6) covers the highest `ua` pin used;
  `top_module` and `uses_vapwr`.
- **The LVS source** (`lvs/tt_um_mattvenn_gf433_vco.spice`, generated from `layout/gen/tile_nets.py` and LVS-matched
  to the GDS, so it is the truth for what the pins connect to): each TT pin's net has exactly the listed block ports,
  no more and no fewer. Unused inputs (`uio_in[3..7]`) and `ena` are unconnected, unused outputs are tied low, and
  `uio_oe[i]` is tied high exactly on the uio pins the table marks as outputs (only uio[3], MISO: `uio_oe` = 0x08).
  `ua[1]` must be shorted to VGND (the on-chip ground sense, `Rshort_ua1` in the source).
- **The macro ↔ analog nets:** `ck` (the VCO's f / 4 into the macro), `rx_en` to the RX bias and both local
  oscillator (LO) buffers, `dbg_sel[k]` to debug switch k and its antenna diode, the four sources the switches put on
  `ua[0]`, the 37 DAC lines (`dac_tn[i]` to `ns(i+1)`, `dac_bn[b]` to `nb(b)`, `dac_sdn` to `nsd`), the code
  inverters, and the macro's supplies on VDPWR / VGND. Every macro port must be in one of the two tables.
- **The macro's pins:** the 54 signal pins are the same in the RTL, the LEF, the GL netlist and the LVS source's
  `tx_fine` subcircuit, and the LEF directions match the RTL's.

`--verilog OUT` also writes the TT-level wrapper the cocotb tests use (below).

**Table II.** Pinout mutants (`test/mutations.sh`, a sed edit on a copy of the LVS source or `info.yaml`).

| Mutant | Edit | Result |
|---|---|---|
| swap_ua23 | the TX driver's out_p / out_n onto ua[2] / ua[3] swapped | caught: ua[2] has out_p |
| swap_dbg01 | debug switches 0 and 1 on each other's `dbg_sel` | caught: net dbg_sel[0] |
| oe3_low | uio_oe[3] tie cell `tieh` → `tiel` | caught: uio_oe[3] expected tied 1 |
| dac_rev | mdac's ns30 / ns28 lines swapped | caught: net dac_tn[27] |
| ua1_open | the ua[1] to VGND short removed | caught: ua[1] unconnected |
| rx_en_open | the Q LO buffer's enable off `rx_en` | caught: net rx_en |
| label | uo[1]'s `info.yaml` label changed | caught |
| analog_pins | `analog_pins: 6` → 4 | caught |

## TT-level cocotb

`test/test.py` drives the whole tile only through its TT pins, as the bench will. The Verilog top
`tt_um_mattvenn_gf433_vco` is generated from the LVS source by `check_pinout.py --verilog` (into the simulation
build directory), so the wiring under test is the wiring that is LVS-matched to the GDS. The macro is the RTL, or the
GL netlist with `GL=1`. The analog blocks are behavioural stubs (`test/stubs.v`): logic models only, enough to show
that each control line reaches the right block. The debug switches are `tranif1` transmission gates, the vctrl
pull-down is a weak 0, and the medium DAC stub turns its 37 active-low lines back into a word and checks that the
thermometer has no gaps. `test/tb.v` is the usual TT test bench, plus a driver on ua[0] for the vctrl override.

**Table III.** TT-level tests (6 / 6 pass, RTL and GL).

| Test | Checks |
|---|---|
| `test_reset_and_oe` | `uio_oe` = 0x08 in reset and after; MISO low in reset; unused outputs low; ck output gated off; RX off, no debug switch on, ua[0] floating, DAC word 512, SD cell off; the SPI works with `ena` low (the design ignores `ena`); `rst_n` returns every register to its reset value |
| `test_spi_to_mdac` | SPI write and read-back of every register on the uio pins; MED_INT reaches the DAC word at every thermometer level (32 words plus the end points) and reads back as EFF_INT; FSK on ui_in[7] moves the word by ± FSK_DEV; the SD cell's mean over 256 clocks equals the fraction (77) |
| `test_rx_en` | CTRL[4] turns on the RX bias and both LO buffers, and nothing else does; the I and Q limiter outputs reach uo_out[4] / uo_out[5] unswapped; the LO buffers stop with RX_EN off |
| `test_dbg_sel` | DBG_SEL bit k closes switch k only, and ua[0] carries that switch's source (baseband I, Q, bias nb, vctrl), with the sources set to two different patterns; ua[0] floats with DBG_SEL = 0; with switch 3 on, ua[0] driven from the bench sets vctrl at the core; two bits on short two sources (ua[0] = x) |
| `test_tx_and_code` | ui_in[5] keys ua[3] and only ua[3], ui_in[6] keys ua[2]; ui_in[4:0] reach the ring's coarse DAC with their inverses |
| `test_dividers` | uo_out[1..3] are ck / 4, / 16, / 256; uo_out[0] follows ck only with CTRL.CK_EN |

**Table IV.** TT-level mutants (`test/mutations.sh`: a copy of the LVS source, so a new wrapper, or of the RTL).

| Mutant | Edit | Failing tests |
|---|---|---|
| swap_dbg01 | debug switches 0 / 1 swapped (LVS source) | `test_dbg_sel` |
| oe3_low | uio_oe[3] tied low (LVS source) | `test_reset_and_oe` |
| dac_rev | mdac ns30 / ns28 swapped (LVS source) | `test_spi_to_mdac` |
| swap_tx_en | ui_in[5] / ui_in[6] swapped at the TX driver (LVS source) | `test_tx_and_code` |
| rx_en_open | Q LO buffer enable not on `rx_en` (LVS source) | `test_reset_and_oe`, `test_rx_en` |
| rtl_rx_en | `rx_en = ctrl[3]` (RTL) | `test_rx_en`, `test_dbg_sel` |
| rtl_dbg_addr | DBG_SEL at address 6 (RTL) | `test_reset_and_oe`, `test_spi_to_mdac`, `test_dbg_sel` |

The first version of `test_spi_to_mdac` wrote only 10 words and missed `dac_rev` (the swapped lines only differ with
28 or 29 segments on). It now writes one word at every thermometer level.

## Formal

`formal/tx_fine.sby` (SymbiYosys) proves properties of the RTL for all time. The harness `formal/fv_tx_fine.sv`
leaves every input free at every step: `rst_n` (at any time), the SPI pins, `fsk`, and `ck` with any waveform. `clk`
toggles every step, and reset is assumed only in the first step. The RTL is not edited: the clock gates and their
latches are modelled as written (`multiclock on`), and internal registers reach the harness through `connect -set`
after `flatten`.

**Table V.** Properties of the `prove` task (all PASS).

| | Property | Why it matters |
|---|---|---|
| R | while `rst_n` is low, every output is at its reset value: DAC word 512, SD cell off, MISO low, RX_EN and DBG_SEL 0, ck output and dividers 0 | the chip powers up with the RX off and no debug switch on |
| S | the registers (and the `rx_en` / `dbg_sel` outputs) always equal a reference model of the documented frame format: 16 bits while CS_n is low, [15] read, [14:12] address, a write at the 16th rising edge, addresses 4, 6 and 7 not writable | reads never write, a write changes only the register it addresses, read-only addresses change nothing; frames of up to 47 bits (below) |
| F | the effective word is {MED_INT, MED_FRAC} ± FSK_DEV, clamped to 0 … 2^18 − 1 | FSK never wraps the word round (a jump of the whole tuning range) |
| D | the thermometer lines have no gaps, and the DAC lines always encode EFF_INT | the medium DAC stays monotonic |
| Q | one clock edge after SD_EN is seen low, the SD cell is off and its accumulator clear | the SD switch-off leaves no stray LSB |
| G | outside reset, `ck_o` is high only while `ck` is, and rises and falls only with `ck` | the ck output gate never makes a runt pulse |

The `gates` task is a miter: two copies of the RTL with the same inputs, one as written and one with each `tx_cg`
replaced by a wire (`formal/cg_nogate.v`, swapped in by `copy` and `chtype` in the .sby). Every output must be equal
at every step after the first reset. This proves the RTL comment that the four clock gates leave the outputs "cycle for
cycle the same as without the gates", for any input sequence. Result, at the time of writing: **not proven for all time.** PDR had not converged
after 25 minutes (the run has a 60-minute limit), while the `prove` task closes in about 1.5 minutes. The bounded
task `gates_bmc` passes to 60 steps (30 clk cycles, about 14 minutes), which is short of one 16-bit SPI frame, so it
is a weak bound; the two `gates` mutants were found by PDR at steps 24 and 70. The test bench `clock_gating` test in
`test_tx_fine.py` and the eqy check (which treats the gates as black boxes with proven enables) cover the same
ground by other means. Next step: help PDR with invariants (for example the D property and `en_l` = the enable while
clk is low) or run it longer on the sim server.

**Table VI.** Formal mutants (`formal/mutate.sh`, one edit on a copy of `src/tx_fine.v`).

| Mutant | Task | Edit | Result |
|---|---|---|---|
| rst_dbg | prove | DBG_SEL resets to 1 | caught (S), step 1, 1 s |
| addr4 | prove | DBG_SEL written at address 4 (read only) | caught (S), step 84, 7 s |
| thermo | prove | thermometer line i decoded as line i ^ 1 | caught (D, gap), step 72, 8 s |
| no_sat | prove | no saturation below 0 (the word wraps) | caught (F), step 208, 51 s |
| sd_hold | prove | SD_EN off no longer clears the accumulator | caught (Q), step 198, 125 s (a first run with three other proofs on the machine timed out at 900 s) |
| ck_glitch | prove | `ck_o = ck & ck_en` (CK_EN straight from the clk domain) | caught (G), step 66, 24 s |
| dec_gate | gates | the decode gate's enable compares only bits [17:9] | caught, step 70, 35 s |
| spi_gate | gates | the SPI gate's enable without the two clocks after CS_n rises | caught, step 24, 2 s |

A first `ck_glitch` mutant, `g_en` clocked on the rising instead of the falling edge of `ck`, was **not** caught: in
the zero-delay model `g_en` and `ck` change in the same step, so no runt pulse appears. In silicon that is a race.
Property G only catches enables that change while `ck` is high from another clock domain.

**Two expected failures**, kept as tasks so the traces can be looked at again:
- **`dbg`: at most one DBG_SEL bit.** The RTL stores any 4-bit value, as `src/tx_fine.v` says ("at most one should be
  on, firmware's job"). BMC finds a write of two bits at step 66. Two switches on short two sources together on ua[0]
  (the TT-level test shows ua[0] = x). Not a bug, but the firmware must never write more than one bit.
- **`long`: frames of 48 bits or more.** The bit counter is 5 bits and wraps, and a write happens whenever it reaches
  15. A frame held for 48 bits (CS_n low for three 16-bit words) therefore writes twice: the first word at bit 16 and
  the third word at bit 48; the second word is ignored. PDR finds this in 30 s (a counterexample at step 194, 97 clocks). The documented frame is 16
  bits with CS_n high between frames, so the `prove` task assumes at most 47 bits per frame. The firmware must raise
  CS_n after every 16-bit word.

## Equivalence (eqy)

Gate-level simulation only shows that the netlist matches the RTL for the stimulus the tests give it. A logic
equivalence check (LEC) proves it for every input. `formal/eqy/run.sh` uses eqy (Yosys' equivalence checker) to
prove that `src/tx_fine.v` and the shipped netlist `macro/tx_fine/nl/tx_fine.nl.v` (LibreLane run r250c) do the same
thing. The scripts are adapted from the ook-asic-radio project's.
- **Gold** is the RTL read as LibreLane synthesis reads it (Yosys defines `SYNTHESIS`, so `tx_cg` instantiates the
  library's `icgtp_1`). **Gate** is `nl.v` with the cells' functions from the PDK's liberty file
  (`gf180mcu_fd_sc_mcu7t5v0__tt_025C_3v30.lib`: combinational functions, flops with their asynchronous set / reset);
  fill, endcap and antenna cells are dropped.
- **Clock gates:** the `icgtp_1` cell is a black box on both sides (`formal/eqy/icg_bb.v`), paired by instance name,
  so eqy proves its inputs (CLK, E, TE) equivalent.
- **Matching:** only ports, flop outputs and the clock gates are matched by name (`match.py`). 170 of the RTL's 171
  flop bits have their name in the netlist; the 171st, `sr[15]`, is never read and synthesis removed it.
- **Clocks:** eqy treats every flop as clocked by one global clock. `clocks.py` checks separately that each flop has
  the same clock source and edge, and the same asynchronous reset source and polarity, in the RTL and the netlist,
  walking back through clock-tree buffers and inverters. Sources: `clk` (11 synchroniser flops), the four clock gates
  (73 + 18 + 46 + 9), `ck` (5 rising, 1 falling) and the ripple divider's own stages (falling edges).
- **`pnl.v`** (with power pins, the netlist the LVS source is made from): with the power pins stripped it is the same
  2617 statements as `nl.v`.

Result: **equivalent, 71 / 71 partitions proven, clocks 170 / 170 the same, about 1 s** (the whole script with the
self-test about 11 s).

**Table VII.** Planted bugs (`formal/eqy/plant.py`, one text edit each on a copy of `nl.v`, run by `run.sh`).

| Bug | Edit | Result |
|---|---|---|
| sd_gate_en | the SD clock gate's enable: its `oai21` driver becomes an `aoi21` | caught: `g_sd.en` not proven |
| eff_bit | `eff_int[3]` loads `eff_q[10]` instead of `eff_q[11]` | caught: `eff_int` not proven |
| rst_val | `eff_q[17]`'s set flop (reset word 512) becomes a reset flop | caught: `eff_q` not proven |
| clk_swap | a `dac_tn` flop on the eff_q gated clock instead of the decode's | eqy passes it (71 / 71); the clock check catches it |
| ripple_edge | divider stage 6 on the rising edge of stage 5 | eqy passes it; the clock check catches it (edge) |

**CI:** `.github/workflows/eqy.yaml` runs `run.sh` on every push, with YosysHQ's oss-cad-suite (build 2026-09-30) and
the gf180mcuD PDK from the same ciel version as the `lvs` action. After a re-harden, the edits in `plant.py` need
updating: they name instances in the r250c netlist, and `plant.py` stops with an error if an edit doesn't match.

**Not covered:** the cell functions come from the liberty file, so a wrong liberty function would go unseen. LVS
ties the layout to `pnl.v`, and this ties `pnl.v` to the RTL. The clock gates' latch timing and the clock tree are
static timing analysis' (STA's) and GL simulation's job.

## Findings

1. **No TX / RX interlock.** The TX enables come straight from ui_in[5] / ui_in[6] to the TX driver; RX_EN is CTRL[4].
   Nothing in the tile stops the TX and RX being on together. It may be wanted (a loopback test), but it is the
   firmware's job.
2. **DBG_SEL is not one-hot** (formal task `dbg`): two bits on short two sources on ua[0].
3. **Frames of 48 bits or more write twice** (formal task `long`): the firmware must raise CS_n after each 16-bit
   frame. The register map comment in `info.yaml` could say so.
4. **The tie cells on the TT outputs are powered from VAPWR** (`lvs/make_source.py` and `layout/gen/tile.py`), so
   `uio_oe[3]` = 1 and the tied-low outputs come from the analog supply. `layout/gen/tile_nets.py` lists
   `'xties': VD` (VDPWR) in `SUPPLY`, which is not used. Both supplies are 3.3 V, so this works, but the two files
   disagree.
5. **uio_oe[3] is always 1:** MISO drives the bus even with CS_n high and in reset (low). Fine with one device on
   the bus.
6. `sr[15]` in the SPI shifter is never read (synthesis removed it); harmless.

At the time of writing the TT-level tests use logic stubs for every analog block, so they check wiring and control,
not analog behaviour. The real TT precheck (and any TT test action) has not run on these files yet.
