# Verification strategy

## Architecture
```
model (Python, bit-exact) ──vectors──► RTL ──► GL ──► mixed signal (Verilated RTL via d_cosim + transistor analog)
schematic blocks ──► tb_<block> (schematic vs PEX) ──► system (analog paths joined, extracted tile)
```
- One reference: the bit-exact model exports stimulus plus every expected output, and RTL and GL
  match it sample for sample.
- A behavioural e2e model sets block budgets up front (e.g. comparator noise ≤ 0.5 mV rms per
  decision, filter cutoff ±30 % tolerable) and converts the worst corner, supply and MC numbers into
  system pass rates at the end.
- Every check has a documented run command in `docs/verification.md`, so a rerun is mechanical. Keep
  scripts in the repo, never in `build/` (a pod loss deleted them).
- Rerun everything after any design change *or* tool-image upgrade (magic, ngspice and KLayout each
  moved results) and compare every number with the previous run.

## When the full system sim is impossible
An extracted high-gain path with transient noise ran ~250× slower than the schematic, so the full
system transient would have taken years.
- **Split fast from slow.** Model the fast front end's output statistically, calibrate that model
  against a short transistor-level noise run, and drive the slow back end with it. Confirm the split
  once with one long joined run (here 14 h, within ~5 %).
- Run a noise-free level/gain table on the extracted path first (minutes). It gives the
  extracted-vs-model offset exactly, before any long noisy run.
- Use short paired runs (stimulus on/off) with **shared** noise (numpy + filesource) to measure small
  differences. State the remaining coverage gap explicitly.

- **Compare a transistor-level result with a transistor-level bench, not the behavioural model.** A joined
  run's −90 dBm swing looked +70 % off against the model; the model reads ~1.3× low near the noise floor, and
  the transistor-level noise bench agreed with the run.
- **Near the noise floor one noise realisation proves nothing.** Four realisations of one joined run spread
  ±0.55 mV (±23 %) at −90 dBm, and one of them was flagged as a change. Run three or more, compare means,
  and split each run by window (chip by chip) to see its own spread first.
- **When an extracted block brings its own copy of a modelled stage** (a detector), don't map its level
  through the schematic stage's curve: that read as +6.6 dB of gain. Calibrate on the *change* instead, e.g.
  the ratio of its signal-induced drops to the schematic's, folded in as a higher NF.

## What to sweep (and what each one caught)
| Check | Caught |
|---|---|
| MC mismatch (`tt_mm`, seeded per process) | trim range too narrow: ~30 % of chips missed spec |
| supply sweep (each rail ±, separately) | an enable level shifter failing at one rail −5 % / the other +10 % |
| pairs of blocks extracted together | −1.5 dB from a shifter + driver pair that passed alone |
| real source impedance on block benches | a block's input C loading the stage that drives it (−2.4 dB) |
| real bias generator instead of ideal sources | −0.6–0.9 dB at hot corners |
| a point outside the spec range (e.g. 85 °C) | where the cliff is |
| stability kick at the highest-gain corner (ss, cold, high VDD) | coupling budget half the tt one |
| stability (and every margin check) also at the corner where *that* margin is smallest | a gain-step condition whose worst corner (sf) wasn't in the stability list |
| the merged block extracted, not just its parts | a detector's inputs and tap wiring (9.7 fF against 1.4 fF in the schematic) taking 4.7 dB off the chain |
| both possible supply-strap orientations of the platform, every rerun | a re-route checked in one only (TT: tile N or FS, pin order) |
| power-up: 10 µs and 10 ms ramps × 3 corners | bias start-up, no output glitch |
| each one-supply-missing state | outputs floating to the other rail |
| overload: large input then small at several gaps, large signals at the pads | recovery time getting worse after an unrelated fix |
| formal with all inputs free, reset at any time | a 1-clock reset shortening a non-overlap dead time |
| structural bus check + mutation | a reversed trim bus that still "worked" |
| TT-wrapper-level cocotb through the real pins | `project.v` had been a stub; `uio_oe` (0 in reset, then exactly the outputs) |

## Mixed-signal detection near threshold
- A mixed run starts its burst at a fixed instant against the RTL's sample clock, so every seed at one level
  shares the same timing luck: counts can be non-monotonic in level (7/20 at −88 dBm, 16/20 at −90). Replay the
  digital decision at every sample alignment from the finished runs (a Python replay of the slicer and
  correlator, checked against the event pin) and quote detection averaged over burst timing.

## Monte Carlo practice
- One sample per ngspice process with its own `.options seed`. Check for duplicate rows.
- Compute per-chip metrics at each chip's own operating point. An average over a range overstated
  the trim step at the real operating point, and the assumed operating code was wrong.
- Pass for trim loops: mean ± 4σ inside the trim range with margin, on both sides. A chip past the end
  of the trim fails hard, which is worse than a soft loss.
- Design the nominal point in the middle of the linear region (a designed-in offset or reference),
  not at a knee. Check that candidate values are buildable in layout (e.g. resistor-string tap parity)
  *before* running MC.
- Compare supply-relative quantities in codes, not volts, across supply corners.
- Report yield against the spec (% of chips meeting each spec level), and pick the metric explicitly: a
  coarser trim step won yield at the spec but lost the best case.

## Stability of a high-gain amplifier
- A 1 µA / 1 ns kick, and the late/early output p-p ratio (< 1 decays). AC peaking within 1 dB of the
  no-coupling case.
- Sweep parasitic output→input coupling to get a budget (for 80 dB it decayed up to 0.1 fF and rang
  at 1 fF), and design the layout to half of it.
- Supply L with decap was not the problem for a differential amplifier; asymmetric coupling was. Use
  the real decap subcircuit, not an ideal C.
- Bias OTA loops: Middlebrook voltage injection, all corners × temperatures, real loads.

## Process
- Close gaps in phases (cheap fixes → block statistics and supply → system on the extracted chip →
  full rerun), with a human review gate after each. **A failing check opens a design change; don't
  patch it inside the verification plan.**
- Keep a findings table: the failure, its detail, its effect on the spec (dB, % of chips), and
  accepted items with owner and date.
- Quote performance per temperature range and as a yield, with the best case shown separately. Mark
  estimates "(est.)".
- Explicitly list what simulation doesn't cover: the pad/package/board model, the silicon speed
  factor, the real environment, latch-up and substrate injection.
- After any block fix, rerun the system-level checks too.
- Re-check claims in docs before trusting them (an "antenna fixed" note was stale).

## Run-time rules of thumb (sky130, 8 threads unless noted)
| Job | Time |
|---|---|
| block `check.sh` / tile `check_top.sh` (DRC×2, LVS, precheck) | ~10 s / ~6 min |
| per-block tb (schematic or PEX) | minutes |
| one block, 5 corners × 3 temps | ~8 min |
| stability: schematic / extracted 6-stage amp (8.7k R) | ~20 s / 15–30 min per case |
| extracted tile RC tb (18k C / 85k R) | ~1 h |
| mixed signal 15 ms: schematic analog / extracted | ~15 min / ~4 h (1 thread) |
| transistor-level high-frequency path with noise | ~38 s per simulated µs; 400 µs = 4 h on 28 CPUs |
| the same path extracted | ~10 000 s per µs |
| 200 MC comparator samples | ~40 s on 24 threads |
| RTL cocotb / GL / TT-level | ~12 min / ~35 min / 1–2 min (Mac 8 / 17) |
| LibreLane harden (~30k µm²) | 5–10 min |
| SymbiYosys PDR | 13–45 min, varies run to run |
| power-grid variant (DC R + IR + EM) | ~45–50 min |
| full re-verification (~270 jobs) | ~410 thread-hours, ~14 h on 28 CPUs |
| the next full rerun (~470 jobs, merged chain + detector extracted) | 1286 thread-hours, 41 h on 28 CPUs |
| extracted chain + detector, PWL noise, 3 µs (3 threads) | ~7 h on a quiet machine, 13–15 h at full load |
| the same with the chain-only extraction / schematic | ~2 h / 1.5 min |
| extracted stability, one case (chain + detector) | 35–55 min |
| extracted chain MC, one sample batch | 4–9 h (schematic 10–14 min) |
| joined schematic RX, 400 µs, trnoise (2 threads) | 3.5–4.3 h |

Extracted vs schematic slowdown: about 10× for a block, 250× for a long high-gain path with noise.
Plan short stand-ins early. Merging a block into the extraction (chain + detector) cost 3.6× over the chain
alone, and a full machine roughly doubles every long run: time probes on a quiet machine aren't the batch
estimate. Run noise levels on the smaller extraction and the merged one only where its own stage matters.

## Silicon vs sim
- Ring oscillators: silicon / extracted-tt = 0.843–0.866, the same at two ring lengths (it isn't
  temperature or VDD). Use the factor that matches the extraction flow (cell alone vs the whole tile).
- To fit the corner of a measured part you need *two* circuits: an inverter trip point (N/P ratio) and
  a ring (speed).
- Routed bus capacitance can dominate: real wiring took one ring from 93 to 38 MHz (it measured 30).
