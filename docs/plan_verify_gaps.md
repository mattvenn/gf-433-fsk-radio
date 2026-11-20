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

**Table I.** The six gaps, the test for each, and its pass criterion. "Level" is where it runs: the extracted tile
(tile, C-only `tile_c.spice`) or the receiver's block extractions joined as the chain (pex, `layout/pex/rx_*_c.spice`,
C only). Matt's rule (2026-11-20): every gap runs on the extracted design; a schematic run (sch) is only an extra,
for statistics, and is labelled so. Updated by the phase-1 agent: see "Changes from the first plan" below.

| # | Gap | Test | Level | Pass criterion | Planted error |
|---|---|---|---|---|---|
| 1 | No mismatch MC on the receiver | MC of the receiver with unit-instance mismatch: limiter / comparator offset against its ±36 mV hysteresis, the mixer's DC offset at LO start (self-mixing plus mismatch), I/Q gain and phase imbalance, LNA and baseband offsets. N = 200 at tt, 100 at ss and ff. Feed the I/Q imbalance and offset spread into `rx_model.py` for the sensitivity spread | pex (blocks; sch extra) | ≥ 99 % of samples: limiter toggles at -105 dBm (offset referred to the limiter input well inside the signal swing), baseband not driven to a rail by the start-up offset after the 8.5 kHz high-pass settles, model sensitivity within 3 dB of the nominal -110 dBm | mismatch turned off (all samples identical: the spread check must fail); one device's unit instances merged back into `m` (the spread must shrink) |
| 2 | No noise in any tile receiver run | Noise injected on the extracted tile: the receiver's antenna-referred noise (NF from the corner's AC noise run) as a `trnoise` source, or one noise waveform shared between runs through a file source, as the OOK radio did. CPFSK data at -100 / -105 / -108 dBm, high-pass preset settled, real ring LO. Also check whether ngspice can do device noise in transient now; if it can, run one comparison | tile; pex for the longer bit counts (sch extra) | bit errors against the model's BER at the same level and NF, within the statistics of the bit count (state the confidence); no limiter chatter (glitches < 1 µs) | noise source scaled ×10 (errors must rise); NF set to 0 dB (errors must fall to 0) |
| 3 | Supply and temperature not varied at system level | VAPWR and VDPWR 3.15 / 3.3 / 3.45 V × 0 / 27 / 70 °C × tt / ss / ff (plus sf / fs where the block set showed spread): the 433.92 MHz code still in reach, TX power, RX settled -95 dBm CW, I/Q LO phase, power-up | tile (C-only) | 433.92 MHz in reach at every point; TX ≥ +3 dBm; RX toggles at -95 dBm; I/Q phase within 72 ± 3° at tt (decoder limit 50-110° elsewhere); ring starts at every point | the 3.45 V case run at 3.0 V (out of range: must flag); temperature not passed to the deck (the check that the deck's `.temp` / `option temp` matches the case must fail) |
| 4 | No strong-signal or recovery test | (a) Overload: a -10 dBm and a 0 dBm burst of 1 ms, then -95 dBm FSK: time until bits decode again. (b) +6 dBm at the RX pins: the pad clamps and the LNA survive and recover. (c) TX-to-RX: TX on at +6 dBm (RX off, as the firmware rules require), then TX off and RX on: time until the RX decodes -95 dBm. Also the TX output's coupling into the LNA input and the RX supply in the tile extraction | pex for (a) / (b); tile + pex baseband for (c) | recovery ≤ 2 ms (the firmware rule waits 1-2 ms after RX_EN / TX off: tighten or relax that rule from the result); no node outside its device's voltage rating at +6 dBm | burst left on (recovery must not be found); the firmware delay check run with 0 ms |
| 5 | No coupling budget from the limiter outputs back to the baseband | From the AC gain of each baseband node to the limiter input, the coupling capacitance from a 3.3 V `q_i` / `q_q` square at the baseband frequency that would put 1/10 of the -105 dBm signal there. Compare it with every `q_i` / `q_q` (and `uo_out4` / `uo_out5`) coupling in `tile_c.spice`. Then a tile run with no RF input, settled: the limiters must not toggle | analysis (pex blocks + tile capacitors) + tile | every extracted coupling ≤ the budget (report the margin per node); no toggles with no input over the run | a coupling cap at 10× the budget added from `q_i` to the most sensitive node: the no-input run must toggle (or the budget check must fail) |
| 6 | No FSK data through the whole tile | CPFSK at 50 kbit/s (±100 kHz), 16 bits after a preamble, through the extracted tile with the real ring LO and the high-pass preset settled, decoded by `rx_model.steps_b` as the firmware would. Noiseless at -70 and -95 dBm; with noise at -105 dBm as gap 2. A long run on the sim server: a whole packet | tile | 0 bit errors noiseless at -70 / -95 dBm; with noise, as gap 2 | the bits inverted in the decoder's reference (errors must be 16 / 16, unless the decoder learns the sign from the preamble: then corrupt the preamble) |

## Changes from the first plan (phase 1, 2026-11-20)

The phase-1 agent (Claude) built the tests against the code and changed the plan where it did not fit:

1. **Extracted design everywhere (Matt, 2026-11-20).** The schematic-level parts (gap 1, gap 2's longer bit counts,
   gap 4 (a) / (b)) now run on the receiver's block extractions (`layout/pex/rx_{bias,lna,mix,bb,lim}_c.spice`,
   C only, swapped into the `sim/rx` decks by `sim/verify/chain_x.py`), with an ideal LO; everything else is on the
   C-only tile. Schematic Monte Carlo stays as a labelled extra.
2. **Gap 1, the "merge" mutation goes the other way.** The GF180 models give one mismatch draw per instance and
   ignore `m`, so a device written as one `m = 16` instance gets the spread of a single finger, 4 times too large, not
   smaller. The extraction writes every finger as its own instance (or as one wide device, whose Pelgrom spread
   is right), so no extracted fet has `m > 1`; the check is now static (no fet with `m > 1` in any MC deck) plus the
   F-test of the stage-1 offset spread, and the mutation (the 16 stage-1 fingers of one side written back as one
   `m = 16` instance) must be flagged by the static check. The resistor models have no mismatch (`mis_r = 0`):
   a limit.
3. **Gap 1, mismatch off.** With mismatch off the comparator still reads a 0.06 mV offset (the measurement
   resolution and the layout's asymmetry), so the mutation is judged on two seeds giving the same numbers (no
   spread), not on a zero offset.
4. **Gap 1, the sensitivity spread** uses the model at BER 1e-3 and 10 kbit/s (the definition of the nominal
   -110 dBm in `rx_design.md` Table VII) with each sample's comparator offsets and hysteresis, I/Q gain ratio and
   phase; the mismatch-off run is the nominal reference. The model has a fixed noise figure (NF), so the NF spread
   from the bias-current spread is not in it (the sample's supply current is reported instead).
5. **Gaps 2 and 6, the decoder.** `rx_chain.fsk_analyse` took the sign and the bit timing from the data bits
   themselves (fine noiseless, biased for an error count). `sim/verify/decode.py` learns both from a known preamble
   (4 bits, 2 in the smoke runs), as the firmware would. The gap-6 mutation is then the reference data inverted
   (errors must be all bits), plus a second one, the preamble inverted (the decoder learns the wrong sign).
6. **Gap 2, statistics.** The tile's 16-bit runs can only show that the BER is not grossly off (the model's BER is
   1.8e-3 at -105 dBm and 2.6e-2 at -108 dBm at 50 kbit/s). The statistical test (two-sided binomial at 1 %) runs on
   the extracted chain: 5 levels (-105 ... -114 dBm) × 8 runs of 8 bits. The NF-0 mutation runs at -114 dBm, where
   the nominal BER is 0.25 and the NF-0 BER is 0.014, so 24 bits separate them; at -105 dBm (the first plan) both
   would give 0 errors and the mutation could not be caught. ngspice 47 has no device noise in transient (checked:
   `trnoise` sources only), so the noise stays lumped at the antenna.
7. **Gap 3, the bias of each PVT point.** The RX runs hold vbnf; its 27 °C value is wrong at 0 / 70 °C and at other
   supplies (ss 70 °C 3.15 V: 1.414 V against 1.384 V at 27 °C), so every point starts with an operating point that
   sets vbnf (5 s). The I/Q LO phase comes from the settled RX pre-run (the same run gives the ring's frequency),
   72 ± 3° at tt 27 °C 3.3 V and 50-110° (the decoder's range) elsewhere. "433.92 MHz in reach" is checked at code 31
   at every point and at code 0 at ff / fs. Power-up runs 16 µs (oscillating by 15 µs).
8. **Gap 4 runs in two parts.** A 1 ms burst and 2 ms of recovery are 3 ms of RF simulation, about 50 h per run on
   the extracted chain. Phase 1 runs the RF chain for 12 µs of the burst (a CW tone 100 kHz above the LO) and saves
   every baseband and limiter node; phase 2 runs the extracted baseband and limiters alone, the mixer outputs as
   sources (the burst's measured mixer-output tone, DC and common mode, then the -95 dBm FSK signal's), from that
   state: the rest of the 1 ms burst, then 2.5 ms of FSK, decoded bit by bit. A run with no burst checks the split
   (the receiver settles from its LO start-up within 1 ms). The TX -> RX turnaround (c) is the same: the tile run
   (TX on, RX off for 1.5 µs, then TX off and rx_en on) gives the mixer's offset and common mode before and after,
   and the extracted baseband bench takes it from there, against the firmware's 1 ms wait (`bringup.md` rule 2).
   (b) +6 dBm checks every LNA and mixer device's |Vgs|, |Vgd|, |Vds|, |Vgb| against 3.63 V (3.3 V + 10 %);
   its mutation is the LNA and mixers at 4.5 V. The "1 ms burst" is simulated as 12 µs of RF + 988 µs of baseband.
9. **Gap 5, the budget** is computed at the FSK deviation (100 kHz) as a transimpedance (`.ac` with the LO held
   static, one switch pair on, so the mixer output sees the LNA's output resistance as it does in both LO phases)
   from a current injected at each baseband node to each comparator input. The tile's unnamed nets are matched to
   the block nets by their device connections (an LVS-like signature: model, W, L, terminal). The tile mutation
   (a 10 × budget cap from q_i to the most sensitive node, `mut_rx0_ccoup`) is in the full run; the budget-check
   mutation runs on every analysis.
10. **Gap 6, packet length.** One tile bit costs 4.5-9 h on 6 threads with the machine loaded (smoke runs), so a
    16-bit packet with a 4-bit preamble is about 2-3 days. The full run keeps the whole-packet runs (-70 / -95 dBm);
    see "Decisions for Matt".

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

## What was built (phases 1 and 2, 2026-11-20)

**Table II.** The new benches and checks (all under `sim/verify/`, run outputs under `build/verify/`, not committed).

| File | What |
|---|---|
| `tile_verify.py`, `jobs_tile_verify.py` | the tile cases of gaps 2-6 (`tb_tile.py`'s deck with new options: a CPFSK source, `trnoise` at the antenna, stepped logic lines, a coupling cap, the temperature mutation) and their analyses |
| `chain_x.py`, `jobs_chain.py` | the extracted receiver blocks as a chain: MC samples, FSK with noise, overload phase 1, the +6 dBm rating, the baseband recovery bench (phase 2) |
| `mc_report.py` | gap 1's yields, spreads, model sensitivities and mutation checks |
| `coupling.py` | gap 5's transimpedances, budgets, tile capacitor matching and its mutation |
| `rxm.py`, `decode.py` | the measured receiver model at 50 kbit/s with offsets / imbalance; the preamble-learning decoder and the recovery-time finder |
| `existing.sh` | one existing digital or layout check, judged from the tool's own output (`RESULT` line) |
| `verdict.py` | the single verdict: every existing and new check PASS / FAIL / pending, every mutation caught / missed / pending |
| `jobs_full.py`, `full_run.sh` | the full run's job file (967 jobs) and its driver; brief in [`handoff_full_verification.md`](handoff_full_verification.md) |

## Run-time estimates (from the smoke runs)

The smoke runs ran with the machine full (about 30 threads busy on 30 cores), as the full run will be, so the
times below are loaded times:
- **Tile (C-only):** about 440 s per simulated µs on 6 threads, 610 s on 4 threads, 3500 s on 1 thread (the ring
  alone); the operating point 5 s. One FSK bit (20 µs) is about 2.5 h on 6 threads, so the 16-bit packet with a 4-bit
  preamble (412 µs) is about 1.8 days on 8 threads: the critical path of the full run.
- **Extracted receiver chain (ideal LO):** about 60 s per simulated µs on 1 thread (an 8-bit FSK run with a 4-bit
  preamble, 270 µs, is about 4.5 h); one MC sample (comparators, 4 µs front end, .ac) 4.7 min; overload phase 1
  (12 µs) 13 min; the baseband recovery bench (3.5 ms of baseband) 3.5 min.
- **Existing checks:** digital checks 1-30 s each, formal `prove` 72 s, `gates_bmc` 12 min, `formal/mutate.sh`
  20 min, `tile_driver.sh` 20 min; the existing tile set about 200 CPU-hours (its job file's estimates).

**Table III.** The full run (`python3 sim/verify/jobs_full.py`): 967 jobs, about 1860 CPU-hours.

| Group | CPU-hours | Note |
|---|---|---|
| gap 3 PVT on the tile (216 jobs) | 640 | the settled -95 dBm RX run at 27 points is 405 of it |
| gap 6 / 2 FSK on the tile (4 runs) + gap 2 on the chain (48 runs) | 660 + 250 | the whole packet alone is about 350 |
| existing tile set (97 jobs) | 200 | |
| gap 1 MC (525 jobs) | 47 | |
| everything else (gaps 4 and 5, existing digital / layout / mixed / power) | about 60 | |

**Wall time:** about 66 h on 28 CPUs (the sim server) and 62 h on 30 (this machine), CPU-bound; the 16-bit tile
packet alone takes about 43 h, so trimming CPU below about 1200 CPU-hours does not shorten the run further.

## Decisions for Matt (before the full run)

1. **Run length, about 2.5-3 days.** Trims, if wanted (each is one edit in the job files):
   - the gap-3 RX run only at the supply extremes (3.15 / 3.45 V) at 0 / 70 °C: -90 CPU-hours;
   - gap 2 on the chain at 3 levels (-108 / -112 / -114 dBm) instead of 5: -85 CPU-hours;
   - the 16-bit tile packet split into 4 runs of 4 bits (same bits, each from the settled state): the critical path
     drops from about 43 h to about 16 h, but it is then not one whole packet.
2. **Where it runs:** the sim server (28 CPUs) or this machine (30): about the same time. The sim server needs
   `GITHUB_TOKEN` for the driver's own status pushes, or the agent pushes them.
3. **Two findings from the smoke runs that bear on the firmware rules** (below, "Smoke-run results"): the receiver
   needs about 1.5 ms after rx_en (from off) and about 1.9 ms after a strong in-band burst before -95 dBm decodes,
   against the 1 ms wait in `bringup.md`. The full run repeats both; the rule could be changed to 2 ms now.

## Where the phase-1 agent got to (2026-11-20, 15:20) and next steps

Written so the work can resume from git alone (the smoke outputs are in `build/verify/`, not committed).

**Done and committed:** every gap's bench, checker and mutation (Table II); the full-run job file
(`sim/verify/jobs_full.py`, 967 jobs), driver (`sim/verify/full_run.sh`, dry-run tested: `DRY=1` -> DONE,
`DRY=fail` -> FAILED at setup) and brief ([`handoff_full_verification.md`](handoff_full_verification.md)).

**Smoke results so far** (`python3 sim/verify/verdict.py --smoke` -> `build/verify/verdict_smoke.md`):
- existing digital / layout: all PASS (pinout, cocotb macro / TT on RTL and GL, formal prove and gates_bmc, eqy,
  floorplan, xschem, `tile_driver.sh`); planted errors caught: `test/mutations.sh` 15 / 15, `formal/mutate.sh` 8 / 8,
  eqy 5 / 5, tile LVS 14 / 14, antenna 1 / 1.
- gap 4: +6 dBm at the RX pins, worst device 3.35 V (LNA input-pair Vgs) against 3.63 V: PASS (4.5 V mutation: 55
  devices flagged). A 1 ms burst at -10 / 0 / +6 dBm: -95 dBm decodes again 1.90 ms after the burst (a 0.1 ms burst
  gives the same 1.90 ms: the baseband saturates within 0.1 ms); no-burst reference 0.28 ms. TX -> RX: 1.47 ms after
  rx_en. On the tile the TX puts under 1 µV p-p on the LNA pins with the RX off. Burst-left-on mutation: pending.
- gap 5: every one of 50 extracted q_i / q_q couplings into baseband nets within its budget (tightest
  uo_out[5] -> bi_p 315 aF against 2744 aF, 8.7x; smallest budget 48 aF at the stage-2 inputs); the 10x mutation is
  caught. Not in the baseband but worth noting: uo_out[4] - ua[0] is 24 fF, 0.6 of oi_p's budget when DBG_SEL[0] puts
  oi_p on ua[0] (debug mode only).
- gap 3, ss / 70 °C / 3.15 V (the smoke point): TX +3.24 dBm against the +3 dBm limit (PASS, 0.24 dB margin: the
  tightest point is likely here), divide-by-4 exact at the operating code (409.2 MHz), I/Q LO phase 73.9°; the
  settled -95 dBm RX run and power-up still running.
- power grid: re-solved on the current mesh, worst EM 2.74-2.80x the LEF figure (0.88-0.90x the 85 °C limit) at
  tt / ss / ff and the finer mesh: PASS.
- gap 3 mutations (3.0 V for 3.45 V; 70 °C not in the deck) caught. ss / 70 °C / 3.15 V: 433.92 MHz in reach
  (687 MHz at code 31), but the divide-by-4 reads f / f(ck) = 10.85 at 687 MHz there (information: the check is at the
  operating code, still running).

**Smoke-verdict FAILs and what they are:**
1. *mixed rx_en ss* (nb 0.000 V with rx_en on): the known open item of `verification.md` ("io_ss: the first SPI write
   (CTRL = RX_EN) did not reach rx_en ... believed to be a d_cosim artefact"); the result is from the stale
   `build/mixed` of 2026-11-17, not a new run. The full run reruns it.
2. *gap 1 MC tt, 7 of 16 runs bad*: a bench artefact, fixed. The comparator bench's triangle ran 2 periods; with an
   offset the second rising switching point fell outside the run, ngspice logged "Error: measure ... out of
   interval" and the log flag marked the run bad (and the fallback to the first switching point gave a wrong
   offset). The bench now runs 3 periods and reads only the second switching points; `chain_x.py mc --only cmp`
   redoes the comparator part of an existing sample. Done for every sample: the MC smoke now passes at tt / ss / ff
   (N = 20 / 10 / 10, extracted blocks): comparator offset sigma 6.3-7.5 mV, |offset| + hysteresis at most 61 mV
   against the 124 mV limit; stage-1 offset at most 130 mV against 0.5 V; mixer offset -4.0 ... -4.5 mV (sigma
   0.05 mV: mostly LO self-mixing); I/Q conversion phase sigma 0.3-0.4°; model sensitivity -110.5 dBm nominal, worst
   +0.28 dB. Supply current 5.7 ± 0.7-0.9 mA (the bias reference's spread; the model's NF does not follow it).
   Mutations caught: mismatch off gives identical numbers for two seeds; the merged stage-1 fingers are flagged
   by the static check, and their stage-1 offset sigma is 26.6 mV against 10.2 mV (F 6.8, p 5e-4).
3. *TX -> RX 1.47 ms against the 1 ms firmware wait*: a real result, not a design error: the baseband's AC couplings
   recover slowly after rx_en (0.5-0.9 ms after a 10 mV step in `rx_design.md`; from the fully-off state here 1.47 ms;
   after an in-band overload 1.90 ms). Proposed (not applied): change `bringup.md` firmware rule 2 to "wait 2 ms after
   rx_en rises or after TX ends" and keep the check's limit as the firmware wait, so the check tracks the rule. A
   faster coupling (more replica current) is the design-side option already listed as open in `rx_design.md`.
4. *power EM p0.5_ss / ff 26.7x*: stale results: `build/power/res_p0.5_ss` / `_ff` were solved at 21:48 on 2026-11-17
   on the mesh from before the strap fix (re-meshed and `res_p0.5` re-solved at 22:38; `p0.25` at 22:25 is also
   older than the mesh). The full run moves `build/power` away and solves everything fresh. Confirmed: re-solved
   locally on the current mesh, ss and ff give 2.74x (0.88x the 85 °C limit), the same as tt; the mutation results
   in that directory are stale in the same way.

**Still running at hand-back (2026-11-20 15:30, smoke, this machine; the schedulers run detached and keep going):**
tile `fsk_c_tt_-95_n2` (gap 6, ETA about 01:00), `fskn_c_tt_-105_n2_s1` (gap 2, about 03:00), `rx0_c_tt` (gap 5,
about 17:30), `pvt_ss_70_3.15_rxs` and `_pu` (gap 3, about 19:30); extracted chain: the 8 gap-2 FSK runs
(`fsk_pex_tt_*`: -114 dBm NF 7.3 / NF 0 × 3 seeds, -105 dBm NF 7.3 / noise × 10, about 20:00) and the 10
schematic MC samples (an extra). Done since: the burst-left-on mutation (caught: no recovery) and the budget
mutation (caught). To collect: `python3 sim/verify/verdict.py --smoke`. The two schedulers exit only once
`sim/verify/jobs_tile_verify.py.final` / `jobs_chain.py.final` exist (touch them when nothing more is to be added;
don't commit them). Restart: `VERIFY_SET=smoke` with `sim/sched.py sim/verify/jobs_tile_verify.py --out
build/verify/tile` and `sim/verify/jobs_chain.py --out build/verify/chain` (a restarted scheduler skips jobs already
OK); the tile FSK smoke runs need `build/verify/tile/rxset_c_tt` (a link to `build/tile_sims_nb/rxset_c_tt`).

**Next steps:** finish the smoke runs; fill the `SMOKE_G*` placeholders in `verification.md` and a "Smoke-run results"
table here; Matt decides the run length (above) and starts the full run.

## Limits at the time of writing

- Transient noise injected at the antenna lumps all device noise at the input. It misses noise that drives a later
  stage non-linear (Harald's point in the OOK review); VACASK or ngspice device noise would close that.
- The pad and antenna model is the same rough one as in [`pad_model.md`](pad_model.md), so the absolute NF and the
  out-of-band behaviour are estimates.
- The tile runs drive the macro's outputs from ideal sources, as before.
