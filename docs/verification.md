# Verification: every test on the 433 MHz radio tile

[![Made with Claude](https://img.shields.io/badge/Made%20with-Claude-D97757?logo=anthropic&logoColor=white)](https://claude.com/claude-code)

This page lists every verification test of the 433 MHz radio tile `tt_um_mattvenn_gf433_vco`, a Tiny Tapeout (TT)
2x2 analog tile on GF180MCU (ttgf26c, branch `floorplan`). For each test it gives what is checked, the command, the
result, and whether the test was itself mutation-tested: a bug is planted in a copy of the design, and the test must
fail on it. The tests, their mutants and this page were written by Claude agents (Claude Code), working from Matt's
briefs; the numbers are copied from the result pages linked in the "Where" column, and no simulation was rerun for
this page. Results are as of 2026-11-17.

The digital checks are described in detail in [`verification_digital.md`](verification_digital.md), the layout checks
in [`tile_layout.md`](tile_layout.md), the mixed-signal co-simulation in
[`sim/mixed/results.md`](../sim/mixed/results.md) and the extracted-tile simulations in
[`sim/top/tile_results.md`](../sim/top/tile_results.md).

Abbreviations used below: register-transfer level (RTL), gate-level netlist (GL), serial peripheral interface (SPI),
digital-to-analog converter (DAC), design rule check (DRC), layout versus schematic (LVS), continuous integration
(CI, the GitHub Actions in `.github/workflows/`), property-directed reachability (PDR, an unbounded proof engine),
bounded model checking (BMC), voltage-controlled oscillator (VCO), transmit / receive (TX / RX), local oscillator
(LO), noise figure (NF), bit-error rate (BER), sigma-delta (ΣΔ), GDSII layout file (GDS), library exchange format (LEF), frequency-shift keying (FSK), process, voltage and temperature (PVT), Monte Carlo (MC). The process corners are tt, ss, ff
and the skewed sf / fs (slow NMOS / fast PMOS and the reverse).

## Summary

**Table I.** Every verification test, at 27 °C and 3.3 V unless stated. "Mutants" counts planted bugs caught / planted.

| Level | Test | Command | Result | Mutants / planted bugs | Where | CI? |
|---|---|---|---|---|---|---|
| **Digital** | Pinout: `info.yaml`, LVS source TT-pin nets, macro ↔ analog nets, `uio_oe` ties, macro pins in RTL / LEF / GL / LVS source | `python3 tools/check_pinout.py` | OK, 0 errors | 8 / 8 (`test/mutations.sh`) | [digital](verification_digital.md#pinout-check) | test |
| | Macro cocotb: `tx_fine` alone (SPI, reset, FSK, saturation, ΣΔ against `sd_model.py`, dividers, clock gating, RX_EN / DBG_SEL) | `cd test && make TB=macro` (`GL=1`) | 7 / 7 pass, RTL and GL | 6 / 6 broken RTL copies for the RX_EN / DBG_SEL test | [digital](verification_digital.md), [layout step 1](tile_layout.md#step-1-the-digital-macro) | test |
| | TT-level cocotb: the whole tile through its TT pins, wiring generated from the LVS source, analog blocks as logic stubs | `cd test && make TB=tt` (`GL=1`) | 6 / 6 pass, RTL and GL | 7 / 7 | [digital](verification_digital.md#tt-level-cocotb) | test |
| | Formal `prove`: six safety properties of the RTL for all time | `cd formal && sby -f tx_fine.sby prove` | PASS (PDR, about 1.5 min) | 6 / 6 (`formal/mutate.sh`) | [digital](verification_digital.md#formal) | no |
| | Formal `gates`: clock-gated RTL equals the RTL with the gates replaced by wires | `sby -f tx_fine.sby gates` / `gates_bmc` | **not proven for all time** (PDR open after 25 min); BMC PASS to 60 steps (30 clk cycles) | 2 / 2 (found by PDR at steps 24 and 70) | [digital](verification_digital.md#formal) | no |
| | Formal `dbg`, `long`: DBG_SEL one-hot, frames of 48 bits or more | `sby -f tx_fine.sby dbg` / `long` | FAIL as expected (kept as records: firmware rules) | - | [digital](verification_digital.md#formal) | no |
| | Equivalence (eqy): RTL against the shipped netlist, every input, plus a clock / reset source check | `bash formal/eqy/run.sh` | equivalent: 71 / 71 partitions, clocks 170 / 170 | 5 / 5 (3 by eqy, 2 by the clock check) | [digital](verification_digital.md#equivalence-eqy) | eqy |
| **Mixed-signal** | Co-simulation: Verilator `tx_fine` RTL inside ngspice, driving the extracted medium DAC and the schematic ring, against an ideal-source reference (tt / ss / ff) | see [Reproduce](#reproduce) (`sim/mixed/`) | 35 / 36 checks pass; io_ss RX_EN FAIL (open, below) | 2 / 2 (DAC bits crossed, ΣΔ line inverted) | [sim/mixed](../sim/mixed/results.md) | no |
| **Layout / physical** | Macro harden (LibreLane): DRC, LVS, antenna, setup timing | `HARDEN=1 bash layout/gen/tile_driver.sh` (step 1) | DRC 0 / 0 (magic / KLayout), LVS 0, antenna 0, setup +1.70 ns at 50 MHz | - (LibreLane's own checks) | [layout step 1](tile_layout.md#step-1-the-digital-macro) | no |
| | Block checks: 13 cells (14 since iq-symmetry: `rx_lsq` split into `rx_lsq_ls` and `rx_lsq_hdr`), each DRC, LVS against its schematic, antenna | `bash layout/gen/tile_driver.sh` (step 2; `check_*.sh` per block) | 14 / 14 CHECK OK (2026-11-19) | per block, e.g. `check_core.sh` 6, `check_rx_block.sh` 2 per cell | [layout step 2](tile_layout.md#step-2-the-block-re-layouts) | no |
| | Floorplan rules on the real blocks | `node layout/floorplan/page/check.js layout/floorplan/floorplan.json` | no rule fails; 3 warnings (a2, ls length, supply crossings) | 14 / 14 | [layout step 3](tile_layout.md#step-3-the-floorplan-on-the-real-blocks) | no |
| | Tile DRC: magic `drc(full)` and KLayout (`feol=true beol=true`, rule count must be > 0) | `tile_driver.sh` (step 4) | magic 0, KLayout 0 (768 rules), rerun 2026-11-20 | planted Metal2 spacing and Metal3 width errors caught | [layout step 5](tile_layout.md#step-5-the-checks) | no |
| | Tile LVS (netgen) and resistor totals | `bash layout/gen/check_tt.sh` | match uniquely: 10 537 devices, 5712 nets (2026-11-20); resistor totals match | 14 / 14 | [layout step 5](tile_layout.md#step-5-the-checks) | lvs |
| | Supply landing: every block supply on a strap with Via3 cuts for its current (LVS can't see resistance) | `python3 layout/gen/supply_check.py` (`tile_driver.sh` step 3) | OK: tx_drv 417 / 206 cuts, LNA 524 / 503 | 1 / 1: the TX driver's VSS unlanded | [sim/power/results.md](../sim/power/results.md) | no |
| | Power grid IR drop / EM (conductance mesh from the GDS, block currents) | `sim/sched.py sim/power/jobs.py` | after the strap fix: TX ground 259 → 12.3 mV, TX supply 36-52 mV (20 mV TT switch); worst EM 0.86× the 85 °C limit | 3 / 3 | [sim/power/results.md](../sim/power/results.md) | no |
| | Tile antenna (KLayout deck, rule count must be > 0) | `tile_driver.sh` (step 6) | 0 violations (24 rules) | 1 / 1: a planted 300 × 300 µm Metal1 plate on a 0.3 µm² gate gives 2 ANT.16 violations | [layout step 5](tile_layout.md#step-5-the-checks) | no |
| | Local precheck: TT structural rules, including the analog pin check | `python3 layout/gen/tile_precheck.py` | pass | Metal5 square caught; fails on the GDS CI rejected (ua[1] open) | [layout step 5](tile_layout.md#step-5-the-checks) | no |
| | The real TT precheck (tt-support-tools) and GDS viewer | CI only (`gds.yaml`) | first run failed the analog pin check (ua[1]); fixed in 27ca4ab, passing since (run 44089936326 on 93b3ddf) | - | [layout step 5](tile_layout.md#step-5-the-checks) | gds |
| | TT documentation build | CI only (`docs.yaml`) | pass (run 44089936433 on 93b3ddf) | - | - | docs |
| | Schematics: xschem netlists against the simulated circuits and the layout's LVS source (netgen plus a device-size diff) | `python3 xschem/gen/check.py` | match uniquely, no size differences | broken copies caught (cfed_dac leg m, lsdiv R1 +10 %, 2 in tx_drv, 4 in the receiver) | [schematics](schematics.md#checks-python3-xschemgencheckpy-results-in-buildxschchecktxt) | no |
| **Extracted tile analog** (C-only extraction, `tb_tile_verdict.py`) | VCO frequency against the block-level extraction, 5 corners | see [Reproduce](#reproduce) (`sim/top/`) | consistent shift PASS; **12.2-12.8 % below the block** at fca76de (tt code 9: 368.05 against 420.50 MHz; a2 19.88 fF): FAIL against the 5 % estimate, open | code bits swapped: caught | [tile §1](../sim/top/tile_results.md#1-vco-on-the-tile) | no |
| | Tuning range and medium DAC range | as above | tt 190.8-691.3 MHz; DAC 1.59 coarse steps; 433.92 MHz at code 12-13 (tt), about 20 (sf) | (as above) | [tile §1](../sim/top/tile_results.md#1-vco-on-the-tile) | no |
| | TX into the 73 Ω dipole through the pad models | as above | +4.73 (ss) to +7.58 (ff) dBm at fca76de, +6.16 dBm at code 13; R+C extraction (supply grid in the loop) +5.97 dBm, -0.19 dB; off -91 dBm: PASS | 2 / 2 (enables low, 10 Ω supply switches) | [tile §2](../sim/top/tile_results.md#2-tx-into-the-dipole) | no |
| | RX, -70 dBm tone 200 kHz from the LO | as above | q_i / q_q toggle at tt, ss, ff; I/Q phase +70 to +76°, sign follows the offset: PASS | 3 / 3 (RX off, q_i / q_q swapped twice) | [tile §3](../sim/top/tile_results.md#3-rx-a-tone-through-the-pads-to-q_i--q_q) | no |
| | RX, -70 / -90 / -95 / -100 dBm, high-pass preset settled | as above | q_i / q_q toggle at 198-201 kHz, duty 47-49 %, I/Q +77 to +79°: PASS (no noise in transient: a working chain, not a sensitivity figure) | (as above) | [tile §3](../sim/top/tile_results.md#3-rx-a-tone-through-the-pads-to-q_i--q_q) | no |
| | Power-up, ramped supplies | as above | ring runs from 15 µs, no TX output (0.03 mV p-p): PASS | 1 / 1 (TX on during power-up) | [tile §4](../sim/top/tile_results.md#4-power-up) | no |
| | Debug mux on ua[0] | as above | each select within 0.4 mV, 0.86-1.63 kΩ; ua[1] = VGND: PASS | 2 / 2 | [tile §5](../sim/top/tile_results.md#5-debug-mux-on-ua0) | no |
| | Supplies: ±4.5 %, impedance, ripple during TX | as above | f +0.32 / -0.30 %; VAPWR ripple 1.0 mV p-p with TX on: PASS | 1 / 1 | [tile §6](../sim/top/tile_results.md#6-supplies) | no |
| | **I/Q LO phase** (2026-11-19, iq-symmetry: the Q level shifter in `vco_core`; 2026-11-20: nb kept away from the LO wires), receiver on, tt / ss / ff | `TILE_SIMS_OUT=build/tile_sims_nb python3 sim/top/tb_tile_verdict.py` (check 7) | Q lags I 72.9° (tt), 74.1° (ss), 72.8° (ff) against 72 ± 3°: PASS (2026-11-19: 74.7 / 76.1 / 74.3°, ss 0.13° outside, accepted by Matt) | 1 / 1 (+16.6 fF on a2: 80.5°) | [tile update 2026-11-20](../sim/top/tile_results.md#update-2026-11-20-nb-kept-away-from-the-lo-wires-branch-iq-symmetry) | no |
| | VCO, RX, TX, debug after iq-symmetry and the nb fix (re-extracted 2026-11-20) | as above | shift -3.55 ... -3.90 % (was -12.2 ... -12.8 %); 433.92 MHz at tt code 10; TX +6.28 dBm (code 9), +5.99 dBm (code 13, now 478.8 MHz); RX settled -95 dBm PASS (I/Q +77.0°); unsettled 14 µs -70 dBm: both arms' mixer offset now equal (-3.4 ... -3.9 mV), limiter I/Q +64.6° / -81.5° and sign flip PASS, -offset and +offset runs PASS (the unsettled runs check phase and sign only since 2026-11-20: +offset read 233 / 240 kHz vs 202 from 4 edges; frequency is checked on the settled run, 198 / 200 kHz) | 12 / 12 | [tile update 2026-11-20](../sim/top/tile_results.md#update-2026-11-20-nb-kept-away-from-the-lo-wires-branch-iq-symmetry) | no |
| | RC extraction (one run, tt code 9) | as above | -12.47 % against the block (-0.67 % against C-only) | - | [tile limits](../sim/top/tile_results.md#limits-at-the-time-of-writing) | no |
| **Receiver / system gaps** (branch `verify-gaps`, [plan](plan_verify_gaps.md); **smoke run only** until the full run, [handoff](handoff_full_verification.md)) | Gap 1: receiver mismatch MC on the extracted blocks (comparator offset + hysteresis against half the -105 dBm signal, stage-1 offset, I/Q gain and phase into the model's sensitivity) | `python3 sim/verify/chain_x.py mc`, `mc_report.py` | smoke (N = 20 / 10 / 10 at tt / ss / ff): PASS: offset sigma 6.3-7.5 mV, |offset| + hysteresis at most 61 mV vs 124 mV; stage-1 offset at most 130 mV vs 0.5 V; model sensitivity within +0.28 dB of -110.5 dBm | smoke (N = 20 / 10 / 10 at tt / ss / ff): PASS: offset sigma 6.3-7.5 mV, |offset| + hysteresis at most 61 mV vs 124 mV; stage-1 offset at most 130 mV vs 0.5 V; model sensitivity within +0.28 dB of -110.5 dBmM | [plan](plan_verify_gaps.md#where-the-phase-1-agent-got-to-2026-11-20-1520-and-next-steps) | no |
| | Gap 2: bit errors with the receiver's noise (`trnoise` at the antenna, NF 7.3 dB), extracted chain and tile, against the model's BER (two-sided binomial, 1 %) | `chain_x.py fsk --nf`, `tile_verify.py run fskn_*` | smoke: tile -105 dBm with noise 0 / 2 errors, 0 glitches: PASS; extracted chain (settled, known sign / timing) -114 dBm 8 / 24 (model 0.25), -105 dBm 0 / 8: PASS | noise × 10: caught; NF 0 at -114 dBm: missed (the circuit does not follow the model there; moved to -110 dBm for the full run) | [plan](plan_verify_gaps.md#where-the-phase-1-agent-got-to-2026-11-20-1520-and-next-steps) | no |
| | Gap 3: tile at corner × 0 / 27 / 70 °C × 3.15 / 3.3 / 3.45 V: 433.92 MHz in reach, TX power, RX settled -95 dBm, I/Q LO phase, power-up | `tile_verify.py run pvt_*` | smoke, ss / 70 °C / 3.15 V: TX +3.24 dBm, RX -95 dBm, I/Q LO 73.9°, ring starts at 16 µs, 687 MHz at code 31: PASS | 2 / 2 (3.0 V for 3.45 V; 70 °C not in the deck) | [plan](plan_verify_gaps.md#where-the-phase-1-agent-got-to-2026-11-20-1520-and-next-steps) | no |
| | Gap 4: overload (1 ms burst at -10 / 0 / +6 dBm, then -95 dBm FSK), +6 dBm device rating, TX -> RX turnaround | `chain_x.py ovl1 / rate / bbrec`, `tile_verify.py run txrx_c_tt` | smoke: +6 dBm worst device 3.35 V vs 3.63 V: PASS; 1 ms burst at -10 / 0 / +6 dBm: decodes 1.90 ms after it: PASS (limit 2 ms); TX -> RX: decodes 1.47 ms after rx_en: PASS against the firmware wait, now 2 ms (was 1 ms: FAIL; decision 2026-11-20) | 3 / 3 (LNA at 4.5 V, burst left on, firmware wait 0 ms) | [plan](plan_verify_gaps.md#where-the-phase-1-agent-got-to-2026-11-20-1520-and-next-steps) | no |
| | Gap 5: q_i / q_q coupling budget into the baseband (every extracted coupling against its budget), tile with no RF input | `python3 sim/verify/coupling.py`, `tile_verify.py run rx0_c_tt` | smoke: all 50 couplings into baseband nets within budget, tightest uo_out[5] -> bi_p 315 aF vs 2744 aF (8.7x): PASS; tile no-input run (settled, 16 µs): 0 edges on q_i / q_q, baseband 2 / 8 mV p-p: PASS | 1 / 1 (a cap of 10 × the budget: the budget check fails); the tile mutation run is in the full run | [plan](plan_verify_gaps.md#where-the-phase-1-agent-got-to-2026-11-20-1520-and-next-steps) | no |
| | Gap 6: CPFSK through the whole extracted tile (real ring LO, settled high-pass), decoded as the firmware would | `tile_verify.py run fsk_c_*` | smoke: -95 dBm, 2 + 2 bits, 0 errors, 7-8 steps per bit, no glitches: PASS | 2 / 2 (reference data inverted; preamble inverted) | [plan](plan_verify_gaps.md#where-the-phase-1-agent-got-to-2026-11-20-1520-and-next-steps) | no |
| **Block-level analog** (links only) | Ring topology, sizing, full-PVT range, monotonicity, FM noise, supply sensitivity | - | see doc | - | [cfed_results](cfed_results.md), [cfed_sizing_results](cfed_sizing_results.md) | no |
| | Coarse DAC mismatch MC (N = 900), start-up (36 runs) | - | see doc | - | [cfed_v3_check](cfed_v3_check.md), [cfed_startup_results](cfed_startup_results.md) | no |
| | 433.92 MHz code map on the extracted core | - | see doc | - | [remap_results](remap_results.md), [rc_extraction_fix](rc_extraction_fix.md) | no |
| | Medium DAC, ΣΔ, MC (N = 200), supply coupling, extracted DAC | - | see doc | - | [tx_fine_tune](tx_fine_tune.md) | no |
| | TX driver, receiver (schematic and extracted), pad model | - | see doc | - | [tx_driver](tx_driver.md), [rx_design](rx_design.md), [rx_layout](rx_layout.md), [pad_model](pad_model.md) | no |
| | Block layouts, phase noise, GF silicon factor | - | see doc | - | [ring_layout_v3](ring_layout_v3.md), [ref_layout](ref_layout.md), [lsdiv_layout](lsdiv_layout.md), [top_layout](top_layout.md), [pn_results](pn_results.md), [gf_silicon_factor](gf_silicon_factor.md) | no |

Every simulation run was judged by its output files and log tails ("singular", "timestep too small", "Transient op
started"), not by exit codes. The `test` workflow runs the pinout check and both cocotb benches on RTL and GL; `eqy`
runs the equivalence check with its planted-bug self-test; `lvs` runs `check_tt.sh` with its mutations; `gds` builds
the GDS and runs the real TT precheck; `docs` builds the TT documentation.

## Open items at the time of writing

- **The a2 shift: mostly fixed on branch `iq-symmetry` (2026-11-19).** The Q level shifter now sits on the ring; a2 7.91 fF, the shift -3.6 ... -3.9 %. With nb also kept away from the LO wires (2026-11-20, lsq - nb 10.55 -> 0.13 fF) the I/Q LO phase is 72.8-74.1°, inside 72 ± 3° at tt / ss / ff. The text below is the state before.
- **The a2 shift.** The ring on the extracted tile runs 12.2-12.8 % below the block-level extraction (fca76de; 11.6-12.3 % before the supply straps added 0.9 fF of coupling to a2) at every corner,
  code and word. The a2 net carries 19.0 fF against about 3.3 fF on the other ring nodes; `vco_top` with 15.7 fF added
  on one ring node reproduces the tile within 0.3 %. 433.92 MHz is still reached (tt code 12-13, sf about 20), but
  the frequency map no longer holds and a2 couples into the baseband. Matt is deciding whether to accept it or to
  re-lay out the a2 route; until then this result is open.
- **Formal `gates` is not proven for all time.** PDR had not converged after 25 minutes; the bounded check passes to
  60 steps only, which is shorter than one 16-bit SPI frame. The cocotb clock-gating test and eqy cover the same
  ground by other means.
- **io_ss: the first SPI write (CTRL = RX_EN) did not reach `rx_en`** in the mixed-signal run, on every rerun. The
  same deck with a build that exports more internal signals takes the write normally, so it is believed to be a
  `d_cosim` artefact, but it is not root-caused.
- **RX at -95 dBm: settled run passes (2026-11-18).** The LO start-up offset (-3 mV) needs 0.5-0.9 ms to clear the
  8.5 kHz high-pass, so the runs preset stage 1's coupling nodes with `.ic` from a 3 µs pre-run; q_i / q_q then toggle
  down to -100 dBm. Transient has no noise, so the noise-limited sensitivity is still not simulated.
- **No TX / RX interlock.** The TX enables come from ui_in[5] / ui_in[6] and RX_EN from CTRL[4]; nothing on chip
  stops both being on. Decided 2026-11-17: no hardware interlock; the firmware rules are in `bringup.md`. Firmware must also keep DBG_SEL one-hot and raise CS_n after each 16-bit frame (formal `dbg`
  and `long`).
- **sf / fs block-level spread.** With vctrl pulled down, the extracted block-level reference runs at 321.6 MHz (sf
  code 9) and 542.0 MHz (fs code 10), far from the schematic map; this is a block-level open item, and the tile adds
  the same -12 % on top.
- **No 0 / 70 °C or MC on the extracted tile.** The tile runs are at 27 °C, 3.3 V (plus ±4.5 % at tt), with power-up,
  debug mux and supply impedance at tt only. Sign-off (full PVT plus MC on the extracted layout) waits for the a2
  decision.
- **No power-grid IR-drop or electromigration (EM) analysis** of the tile's Metal4 stripes has been done.
- **Smaller gaps:** the macro is not in the extracted tile netlist (ideal sources drive its outputs). The tile has
  no antenna violation even with its three antenna-diode rows removed: they are spare protection, since the nets
  they guard stay off Metal4.

## Reproduce

Run from the repository root (in the IIC-OSIC-TOOLS image). The simulation lines take hours (each mixed-signal
step / ΣΔ run 32-51 minutes, the tile set about 7 hours on 14 CPUs) and belong on the sim server.

```bash
# everything below plus the gap 1-6 tests, one driver (about 2.5 days; docs/handoff_full_verification.md)
bash sim/verify/full_run.sh                    # -> build/verify/verdict.md

# digital
python3 tools/check_pinout.py
cd test && make && make GL=1 && cd ..          # macro and TT-level cocotb, RTL then GL
bash test/mutations.sh                         # pinout and TT-level mutants
cd formal && sby -f tx_fine.sby prove && sby -f tx_fine.sby gates_bmc && cd ..
bash formal/mutate.sh                          # formal mutants
bash formal/eqy/run.sh                         # equivalence, clock check and planted bugs

# layout / physical
node layout/floorplan/page/check.js layout/floorplan/floorplan.json
python3 xschem/gen/check.py
python3 lvs/make_source.py
bash layout/gen/tile_driver.sh                 # blocks, DRC, LVS (check_tt.sh), antenna, local precheck
                                               # (HARDEN=1 also re-hardens the macro); results in build/tile/run/

# mixed-signal co-simulation
bash sim/mixed/build_so.sh
nohup setsid python3 sim/sched.py sim/mixed/jobs.py --budget 8 --out build/mixed > build/mixed/sched.log 2>&1 &
python3 sim/mixed/verdict.py --mutants

# extracted tile
bash layout/gen/pex_tile.sh c && bash layout/gen/pex_tile.sh rc
mkdir -p build/tile_sims && nohup setsid python3 sim/sched.py sim/top/jobs_tile.py --budget 14 \
    --out build/tile_sims > build/tile_sims/sched.log 2>&1 &
python3 sim/top/tb_tile_verdict.py --mutants
```
