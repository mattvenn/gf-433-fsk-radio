# Plan: close the receiver and system verification gaps

[![Made with Claude](https://img.shields.io/badge/Made%20with-Claude-D97757?logo=anthropic&logoColor=white)](https://claude.com/claude-code)

Written by Claude (Claude Code) on 2026-11-20, from a comparison of [`verification.md`](verification.md) with the
OOK radio's verification (`github.com/mattvenn/ook-asic-radio`: `docs/verification.md`, `docs/plan_verify_gaps.md`,
`docs/review_harald_2026-11-13.md`). Matt chose gaps 1-6 below. Gap 7 (power-up with one supply missing) and gap 8 (an
external design review) are not in this plan.

The digital and layout checks already match or exceed the OOK radio's. The gaps are on the receiver (RX) and
system side. Every new test follows this project's rules: it is judged by its output files and log tails, it has at
least one planted error (mutation) that it must catch, and it reports pass / fail against a criterion written down
before the run. Long runs go through `sim/sched.py` job files so that a single full verification run can include them.

## What exists already

- **Block level, schematic** (`sim/rx/rx_chain.py`, [`rx_design.md`](rx_design.md)):
  - 2-frequency-shift keying (FSK) with an ideal local oscillator (LO), 6 data bits at -95 / -70 dBm: 0 bit errors.
  - The same through the real ring LO at -70 dBm (`realfsk`): 0 errors.
  - Noise: the model's noise figure (NF) 7.3 dB injected as one white `trnoise` source at the antenna, -105 dBm,
    2 data bits: 0 errors, no comparator chatter.
  - 1 dB compression at -23.5 dBm; blocker ratio at the baseband output at +1 / +2 MHz.
- **Extracted tile** (`sim/top/tb_tile.py`, [`tile_results.md`](../sim/top/tile_results.md)):
  - a continuous-wave (CW) tone at -70 to -100 dBm, high-pass preset settled, noiseless;
  - TX output, power-up, debug multiplexer, supply ±4.5 % for the voltage-controlled oscillator (VCO), I/Q LO phase;
  - all at 27 °C, mostly tt.
- **Monte Carlo (MC):** the ring's coarse digital-to-analog converter (DAC) (N = 900), start-up (36 runs) and the
  medium DAC (N = 200). There is no MC on the receiver. `sim/mc/mm_proof.sh` shows the GF180 trap: the models
  give one mismatch draw per instance and ignore `m`, so matched devices must be split into unit instances.

## Gaps and tests

**Table I.** The six gaps, the test for each, and its pass criterion. "Level" is where it runs: block schematic
(sch), block extraction (pex) or the extracted tile (tile, C-only `tile_c.spice`).

| # | Gap | Test | Level | Pass criterion | Planted error |
|---|---|---|---|---|---|
| 1 | No mismatch MC on the receiver | MC of the receiver with unit-instance mismatch: limiter / comparator offset against its ±36 mV hysteresis, the mixer's DC offset at LO start (self-mixing plus mismatch), I/Q gain and phase imbalance, LNA and baseband offsets. N = 200 at tt, 100 at ss and ff. Feed the I/Q imbalance and offset spread into `rx_model.py` for the sensitivity spread | sch (blocks), pex where an extraction exists | ≥ 99 % of samples: limiter toggles at -105 dBm (offset referred to the limiter input well inside the signal swing), baseband not driven to a rail by the start-up offset after the 8.5 kHz high-pass settles, model sensitivity within 3 dB of the nominal -110 dBm | mismatch turned off (all samples identical: the spread check must fail); one device's unit instances merged back into `m` (the spread must shrink) |
| 2 | No noise in any tile receiver run | Noise injected on the extracted tile: the receiver's antenna-referred noise (NF from the corner's AC noise run) as a `trnoise` source, or one noise waveform shared between runs through a file source, as the OOK radio did. CPFSK data at -100 / -105 / -108 dBm, high-pass preset settled, real ring LO. Also check whether ngspice can do device noise in transient now; if it can, run one comparison | tile (and sch for the longer bit counts) | bit errors against the model's BER at the same level and NF, within the statistics of the bit count (state the confidence); no limiter chatter (glitches < 1 µs) | noise source scaled ×10 (errors must rise); NF set to 0 dB (errors must fall to 0) |
| 3 | Supply and temperature not varied at system level | VAPWR and VDPWR 3.15 / 3.3 / 3.45 V × 0 / 27 / 70 °C × tt / ss / ff (plus sf / fs where the block set showed spread): the 433.92 MHz code still in reach, TX power, RX settled -95 dBm CW, I/Q LO phase, power-up | tile (C-only); sch for the long receiver runs | 433.92 MHz in reach at every point; TX ≥ +3 dBm; RX toggles at -95 dBm; I/Q phase within 72 ± 3° at tt (decoder limit 50-110° elsewhere); ring starts at every point | the 3.45 V case run at 3.0 V (out of range: must flag); temperature not passed to the deck (the check that the deck's `.temp` / `option temp` matches the case must fail) |
| 4 | No strong-signal or recovery test | (a) Overload: a -10 dBm and a 0 dBm burst of 1 ms, then -95 dBm FSK: time until bits decode again. (b) +6 dBm at the RX pins: the pad clamps and the LNA survive and recover. (c) TX-to-RX: TX on at +6 dBm (RX off, as the firmware rules require), then TX off and RX on: time until the RX decodes -95 dBm. Also the TX output's coupling into the LNA input and the RX supply in the tile extraction | sch for (a) / (b); tile for (c) | recovery ≤ 2 ms (the firmware rule waits 1-2 ms after RX_EN / TX off: tighten or relax that rule from the result); no node outside its device's voltage rating at +6 dBm | burst left on (recovery must not be found); the firmware delay check run with 0 ms |
| 5 | No coupling budget from the limiter outputs back to the baseband | From the AC gain of each baseband node to the limiter input, the coupling capacitance from a 3.3 V `q_i` / `q_q` square at the baseband frequency that would put 1/10 of the -105 dBm signal there. Compare it with every `q_i` / `q_q` (and `uo_out4` / `uo_out5`) coupling in `tile_c.spice`. Then a tile run with no RF input, settled: the limiters must not toggle | analysis + tile | every extracted coupling ≤ the budget (report the margin per node); no toggles with no input over the run | a coupling cap at 10× the budget added from `q_i` to the most sensitive node: the no-input run must toggle (or the budget check must fail) |
| 6 | No FSK data through the whole tile | CPFSK at 50 kbit/s (±100 kHz), 16 bits after a preamble, through the extracted tile with the real ring LO and the high-pass preset settled, decoded by `rx_model.steps_b` as the firmware would. Noiseless at -70 and -95 dBm; with noise at -105 dBm as gap 2. A long run on the sim server: a whole packet | tile | 0 bit errors noiseless at -70 / -95 dBm; with noise, as gap 2 | the bits inverted in the decoder's reference (errors must be 16 / 16, unless the decoder learns the sign from the preamble: then corrupt the preamble) |

## Phases

1. **Analysis and short benches** (this machine, hours): gap 5's budget and extraction check; the MC benches (gap 1)
   with a 20-sample smoke run per block; the noise and FSK decks for the tile (gaps 2 and 6) with a 2-bit smoke run;
   the supply / temperature cases added to `tb_tile.py` (gap 3) with one smoke run; the overload decks (gap 4).
   Every new checker gets its mutation, and every check gets its row in a verdict script (extend
   `sim/top/tb_tile_verdict.py`, or one new `sim/verify/verdict.py` that calls it).
2. **Job files for the full run:** one job file per gap, plus `sim/verify/jobs_full.py` that includes every existing
   check (digital, layout, mixed-signal, tile) and the new ones, with time estimates from the smoke runs.
3. **The full verification run** (sim server, Matt starts it): through `docs/handoff_full_verification.md`, following
   `docs/handoff_autonomy.md` (status and DONE / FAILED files, `Running: step N/M`, heartbeat).

## Run-time estimates

The C-only tile runs at about 470 s per simulated µs on 3 threads (`rxh_c_tt_-70_p`: 14 µs in 6627 s). One bit at
50 kbit/s is 20 µs, about 2.6 h; 16 bits plus a preamble about 2 days per run. So:
- gaps 2 and 6 on the tile: a few runs of 16 bits (about 2 days each, in parallel), and the longer bit counts at
  schematic level (`rx_chain.py` runs about 15 times faster);
- gap 1: about 400 block-level samples × a few minutes;
- gap 3: 3 × 3 × 3 (+ sf / fs) points × the tile's short VCO / TX / CW runs (about 1 h each);
- gap 4: schematic runs of a few ms (hours each), one tile run for (c).

The phase-1 agent refines these from its smoke runs and writes them into the job files.

## Limits at the time of writing

- Transient noise injected at the antenna lumps all device noise at the input. It misses noise that drives a later
  stage non-linear (Harald's point in the OOK review); VACASK or ngspice device noise would close that.
- The pad and antenna model is the same rough one as in [`pad_model.md`](pad_model.md), so the absolute NF and the
  out-of-band behaviour are estimates.
- The tile runs drive the macro's outputs from ideal sources, as before.
