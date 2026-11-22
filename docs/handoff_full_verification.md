# Handoff: the full verification run (existing checks + receiver / system gaps 1-6)

> Running: step 2/4 jobs since 2026-11-21 09:41: ok 513, run 23, wait 437

[![Made with Claude](https://img.shields.io/badge/Made%20with-Claude-D97757?logo=anthropic&logoColor=white)](https://claude.com/claude-code)

Written by Claude (Claude Code) on 2026-11-20, branch `verify-gaps`. This is the server agent's whole brief. Read
`CLAUDE.md`, `STATUS.md`, [`plan_verify_gaps.md`](plan_verify_gaps.md) (what each new test checks, its pass
criterion and its planted error), [`verification.md`](verification.md) (the existing checks) and
[`handoff_autonomy.md`](handoff_autonomy.md) (the rules below come from it).

**Goal: one unattended run of every verification check of the tile, existing and new, ending in a single verdict
(`build/verify/verdict.md`) that lists every check PASS / FAIL / pending and every planted error caught / missed /
pending; then the write-up.** Nothing in the design changes. A FAIL in the verdict is a result to report, not a
reason to stop or to fix anything.

## What runs

One scheduler (`sim/sched.py`) over one job file, `sim/verify/jobs_full.py`, which joins:

**Table I.** The job groups of the full run. CPU-hours are the job files' estimates (smoke-run times + 10 %, else the
first guesses), `python3 sim/verify/jobs_full.py` prints them.

| Group | Jobs | What | Output | Judged by |
|---|---|---|---|---|
| `ex_*` | 13 | existing digital and layout checks: pinout, `test/mutations.sh`, cocotb macro / TT on RTL and GL, formal `prove`, `gates_bmc`, `formal/mutate.sh`, eqy, floorplan, `xschem/gen/check.py`, `layout/gen/tile_driver.sh` | `build/verify/existing/<check>.log` (last line `RESULT`) | `sim/verify/existing.sh` parses each tool's own output |
| `mx_*` | 27 | mixed-signal co-simulation (`sim/mixed/jobs.py`) | `build/mixed/` | `sim/mixed/verdict.py --mutants` |
| `te_*` | 97 | the existing extracted-tile set (`sim/top/jobs_tile.py`: every case and the block references) | `build/verify/tile_existing/` | `sim/top/tb_tile_verdict.py` (+ `--mutants`) |
| `pw_*` | 14 | power grid IR drop / EM (`sim/power/jobs.py`) | `build/power/` | criterion added in `verdict.py`: worst EM below the 85 °C limit, mutated grids worse |
| `mc_*`, `mc_report` | 525 | gap 1: receiver mismatch Monte Carlo (MC) on the extracted blocks, N = 200 tt / 100 ss / 100 ff, plus the mutations and a schematic set (an extra) | `build/verify/chain/` | `sim/verify/mc_report.py` |
| `fsk_pex_*` | 48 | gap 2: bit errors with noise through the extracted chain, 5 levels × 8 runs of 8 bits, plus the mutations (NF 0 dB, noise × 10); gap 6 extra: 16 bits noiseless at -70 / -95 dBm | `build/verify/chain/` | `verdict.py` (binomial test against `sim/verify/rxm.py`) |
| `fskn_*`, `fsk_c_*`, `rxset_c_tt` | 5 | gaps 6 and 2 on the tile: one whole packet (4-bit preamble + 16 bits) at -95 dBm, 4 bits at -70 dBm, 2 × 6 bits at -105 dBm with noise; the settled RX pre-run | `build/verify/tile/` | `verdict.py` |
| `pvt_*`, `mut_pvt_*` | 218 | gap 3 on the tile: tt / ss / ff (and sf / fs for the frequency range) × 0 / 27 / 70 °C × 3.15 / 3.3 / 3.45 V | `build/verify/tile/` | `verdict.py` |
| `ovl1_*`, `rate_*`, `bbrec_*`, `txrx_c_tt` | 16 | gap 4: overload and recovery, +6 dBm rating, TX -> RX turnaround | `build/verify/chain/`, `build/verify/tile/` | `verdict.py` |
| `coupling_*`, `rx0_c_tt`, `mut_rx0_ccoup` | 4 | gap 5: the q_i / q_q coupling budget, the no-input tile run and its mutation | `build/verify/coupling/`, `build/verify/tile/` | `verdict.py` |

967 jobs, about 1860 CPU-hours: about 66 h on the sim server (28 of its 30 CPUs, CPU-bound). The longest single job is the tile's
16-bit packet (about 43 h on 8 threads). Trims are listed in `plan_verify_gaps.md`, "Decisions for Matt".

## Config (edit here; the driver reads environment variables of the same names)

```
BUDGET=28        # CPUs for the scheduler (the sim server has 30: keep 2 free)
LOAD=30          # the scheduler starts no job while the 1-minute load is above this
TOUT_H=96        # the scheduler's give-up time (h)
```
Corners per job are in the job files and in [`plan_verify_gaps.md`](plan_verify_gaps.md) Table I: 27 °C, 3.3 V and
tt / ss / ff unless the job is a gap-3 PVT job (corner policy: `handoff_autonomy.md`; 0 / 70 °C and ±4.5 % only for
this sign-off-style run). To trim the run, edit the job files (`plan_verify_gaps.md`, "Decisions for Matt").

## Steps

1. `git pull --rebase` on `verify-gaps`. Check the tools: `magic` 8.3.642 is only needed if you re-extract (the run
   uses the committed `layout/pex/tile_c.spice` and `layout/pex/rx_*_c.spice`; don't re-extract with 8.3.684, it drops
   substrate C).
2. Test the driver first (seconds, nothing moved): `DRY=1 POLL=2 bash sim/verify/full_run.sh` must end in
   `build/verify/full_dry/DONE`, and `DRY=fail bash sim/verify/full_run.sh` in `build/verify/full_dry/FAILED` at step 1
   (a planted missing netlist). Both were run on 2026-11-20 by the phase-1 agent.
3. Start the driver, **once, with the Bash tool's `run_in_background: true`** (not `nohup ... &`):
   `bash sim/verify/full_run.sh`
   It moves earlier outputs to `build/old/<time>/`, runs the scheduler, runs the verdict and writes
   `build/verify/full/DONE` or `FAILED`. Its steps (`build/verify/full/status.txt`):
   1. setup: tool versions, git revision, the job plan (`build/verify/full/plan.txt`);
   2. jobs: `sim/sched.py sim/verify/jobs_full.py --budget $BUDGET --out build/verify/full`, with an hourly progress
      line in `status.txt`;
   3. verdict: `python3 sim/verify/verdict.py` -> `build/verify/verdict.md`, `verdict.json`;
   4. done.
   With `GITHUB_TOKEN` set, the driver itself commits and pushes the `>` line at the top of this file at each step
   change and hourly in step 2. Without it, do that yourself at each step change.
4. While it runs: `python3 sim/sched.py --status --out build/verify/full`. A failed job is retried by bumping its
   entry in the `RERUN` dict of its job file (the scheduler re-runs a failed job whose command changed); at most
   twice, then leave it failed: the verdict reports it.
5. When `DONE` appears, write up (below) straight away.

## Running unattended (from `handoff_autonomy.md`)
1. **Never end a turn with untracked work running.** The driver is the one background command; if you also need
   a long wait, start a **Monitor** on `build/verify/full/DONE` / `FAILED`.
2. **One driver, every job chained in it** (`sim/verify/full_run.sh`); the job lists come from the job files, the
   budget from the config above.
3. **Fail loudly and early.** Each driver step checks its own output; on failure it writes `FAILED` with the log
   tail and stops. Judge every run by its `result.json` and the log tails (`singular`, `timestep too small`,
   `Transient op started`; the driver lists flagged logs in `build/verify/full/flagged_logs.txt`), not exit codes.
4. **Heartbeat.** After starting the driver, schedule a wakeup (ScheduleWakeup or `/loop`) every 60 minutes (the
   cap) and re-arm it each time; it only matters if the completion notification is missed.
5. **Progress where the laptop sees it:** the `>` line at the top of this file, pushed at each step change
   (`> Running: step 2/4 jobs since ..., ETA ...`), and `Done` at the end. Send a PushNotification to Matt when the run
   finishes or fails, if that tool is available.
6. **Finish in one go:** when the driver ends, go straight on to the write-up, commit and push, without waiting.
7. **CPU budget via the queue:** everything goes through `sim/sched.py` inside the driver.

## Write-up (straight after DONE)
- `docs/verification.md`: update the result column of every row from `build/verify/verdict.md` (existing checks and
  the new gap rows, which say "smoke run only" until now), and the date.
- `docs/plan_verify_gaps.md`: a "Results of the full run" section: per gap the measured numbers against the pass
  criteria, every mutation caught or missed, the run times (`build/verify/full/status.json`), and findings.
- Copy `build/verify/verdict.md` to `docs/verify_results/verdict_<date>.md` (the build directory is not committed).
- `STATUS.md`: one paragraph at the top of "Next steps".
- Write in Matt's technical style: plain, every acronym expanded at first use, problem -> fix -> evidence, honest
  limits, British spelling, a spaced hyphen instead of an em dash, and say the runs and write-up were done by Claude.
- Commit named files only (never `git add -A`, never `sim.yaml`, never `build/`), `git pull --rebase`, push.

## Run-time estimate

See [`plan_verify_gaps.md`](plan_verify_gaps.md), "Run-time estimates (from the smoke runs)".
