> Stopped (2026-11-25): run complete, but the Table III sanity check is off (worst DNL 0.23-0.26 LSB deeper, ff 199/200), so docs/tx_fine_tune.md is not edited yet; results and draft text below for Matt.

# Handoff: does the fine word fall at word boundaries? (medium-DAC Monte Carlo, sim server)

**Goal: measure how often, and by how much, the fine tuning word (the 10-bit medium-DAC word plus the 8-bit ΣΔ
fraction) goes *down* when it crosses a word boundary, over the medium DAC's Monte Carlo samples, and correct
`docs/tx_fine_tune.md` with the numbers.** About 2–3 hours on the big machine; nothing in the design changes.

## Why (2026-11-25)
A Lean proof (`mattvenn/circuit-design-learnings`, `lean/MediumDac.lean`, theorem `fine_boundary`) showed that the
fine word's mean output, I(w) + (f/256)·I<sub>ΣΔ</sub>, can only stay monotonic across the boundary (w, 255) → (w+1, 0)
if every DAC step is larger than 255/256 of the ΣΔ cell. Table III of `docs/tx_fine_tune.md` has steps as small as
0.24 LSB (worst DNL −0.76 at ff) and a ΣΔ cell of 0.92–1.08 LSB, so at weak carries the frequency can step **down** by
up to about 0.7 LSB (about 20 kHz). The doc says "the curve stays monotonic and continuous across word boundaries",
from runs without mismatch (now corrected with an interim note pointing here). Table III only checked that the coarse steps stay positive (DNL > −1), which is a
different test. This run counts the falling boundaries per sample.

## Where things are
- **Branch: `main`.** Clone it: `cd /foss/designs && git clone https://github.com/mattvenn/gf-433-oscillator.git
  gf433-fineword` (the repo is now named `gf-433-fsk-radio`; GitHub redirects). `git pull --rebase` before every push.
- **Scripts (committed):**
  - `sim/tune/mdac_sim.py mc`: the existing Monte Carlo behind Table III (every PMOS / NMOS unit its own instance,
    DC output current for all 1024 words, `vg` held). Its per-seed logs in `build/tx_fine/mdac/mc_<corner>/` hold
    every word's current (`IW`) and the ΣΔ cell's (`SD0` / `SD1`).
  - `sim/tune/mdac_fineword.py`: reads those logs, finds every falling boundary per sample, and writes
    `build/tx_fine/mdac/fineword_<corner>.json`. `--selftest` checks it on synthetic data (must pass first).
  - `sim/tune/run_mdac_fineword.sh`: the driver (self-test → MC tt → MC ss → MC ff → analysis).
- **Ownership:** you own `build/tx_fine/mdac/`, this handoff, and the edits to `docs/tx_fine_tune.md` described below.
  Don't change any circuit, netlister or the scripts' logic (a fix to make them run is fine: say what and why).

## Config
- Corners **tt, ss, ff** (`typical ss ff`, as Table III), **N = 200** per corner, the default seeds (5000…), so the
  coarse results should reproduce Table III (exactly if Table III used the default seeds; otherwise statistically). 27 °C, 3.3 V. Jobs: `JOBS=<cpus>` in the environment (default 26).

## Run
1. Start the driver from the repo root with the Bash tool's `run_in_background: true`:
   `JOBS=<cpus> bash sim/tune/run_mdac_fineword.sh`. Status: `build/tx_fine/mdac/fineword_status.txt`; the end:
   `build/tx_fine/mdac/DONE` or `FAILED`.
2. **Sanity check before the write-up:** each corner's `mc_<corner>.out` summary line should match Table III (all
   samples DNL > −1; worst DNL close to −0.721 / −0.682 / −0.763; ΣΔ cell range as listed). If it is far off (for
   example the worst DNL differs by more than 0.1 LSB), stop and report: the models or tools on this machine differ.
3. **Mutation-test the analysis once:** copy one sample's log, shrink one step below the cell (subtract from every
   `IW` above that word), run `mdac_fineword.py --dir` on the copy, and confirm the boundary is reported.

## Write-up (in `docs/tx_fine_tune.md`)
- In the ΣΔ bullet of the extracted-results section, replace the interim sentence "How often it happens is being
  measured (`docs/handoff_mdac_fineword.md`)." with the measured result: the share of samples with at least
  one falling boundary, the median and maximum count per sample, the worst drop in LSB and kHz, and how many fall at
  major carries (w % 32 = 31). Keep the point about the ΣΔ charge-injection excess.
- Add a short note after Table III: what the fine-word check measures, its result per corner, and what it means for
  the firmware (the counting servo measures frequency, so it tolerates a falling boundary; a search or FSK step that
  assumes monotonicity across a word boundary does not). Cite the Lean proof as the reason the check was added.
- Update `STATUS.md`'s fine-tuning line if the result changes a conclusion.

## Running unattended
1. **Never end a turn with untracked work running:** start the driver with `run_in_background`, not `nohup … &`.
2. **One driver**, status file per step, `DONE` / `FAILED` at the end (the driver does this).
3. **Fail early:** the driver stops on missing logs, "singular" or "transient op started". Retry at most twice, then
   write up and stop.
4. **Heartbeat:** a wakeup at about 1.5× the step's estimated time, at least 20 and at most 60 minutes; re-arm it.
5. **Progress:** replace the first line of this file with `> Running: step N/5 since HH:MM, ETA HH:MM` at each step
   change, commit and push. PushNotification when done or failed, if available.
6. **Finish in one go:** write up, commit and push without waiting to be asked. Stage only your files, never
   `git add -A`, never `build/` or `sim.yaml`.


## Results (server run, 2026-11-25, written by the server agent)
Run on the sim server (30 CPUs, `JOBS=28`), 16:29-17:24, ngspice-47; `build/tx_fine/mdac/DONE`. Analysis self-test passed.
**The run is complete and the fine-word numbers are measured, but the server agent stopped before editing
`docs/tx_fine_tune.md`** because the sanity check against Table III missed the handoff's 0.1 LSB threshold.

### Sanity check against Table III (did not match)
| Corner | DNL > −1 | Worst DNL (Table III) | 1st percentile (Table III) | LSB | ΣΔ cell / LSB |
|---|---|---|---|---|---|
| tt | 200 / 200 | −0.965 (−0.721) | −0.797 (−0.700) | 6.49-6.85 nA (6.52-6.81) | 0.921-1.083 (0.928-1.071) |
| ss | 200 / 200 | −0.912 (−0.682) | −0.753 (−0.662) | 6.87-7.23 nA (6.90-7.19) | 0.925-1.078 (0.932-1.068) |
| ff | **199 / 200** | **−1.019** (−0.763) | −0.843 (−0.738) | 6.14-6.50 nA (6.17-6.46) | 0.917-1.089 (0.924-1.075) |

- The LSB and the ΣΔ-cell ranges match; the tails are 0.23-0.26 LSB deeper at every corner. The worst samples are
  the same seeds at all three corners (5102 at word 319, then 5093, 5064, 5050), so it is a property of seeds
  5000-5199, not of one corner.
- **The tools on this machine are not the cause.** The Table III numbers come from `sim/tune/mdac.py` at 0917332
  (2026-11-10). Re-running seeds 5102 and 5093 with that exact script here gives −0.965 and −0.797, identical to
  today's `mdac_sim.py`. So Table III was made with other seeds or settings than the defaults; the commit does not
  record which.
- ff 199/200 (99.5 %) still meets the ≥ 99 % spec, but Table III's and the summary row's "200 / 200 at tt, ss and
  ff (worst −0.76 LSB, ff)" would need correcting. That changes a published conclusion, so it is left for Matt.

### Mutation test (passed)
Copied seed 5000's tt log, shrank the step at word 100 to 0.3 × the ΣΔ cell (subtracting 5.01 nA from every `IW`
above it) and ran `mdac_fineword.py --dir` on the copy: the drop list gained word 100 (86 → 87 drops) and the worst
drop became 0.680 LSB, as the arithmetic predicts (255/256 − 0.3) × cell / LSB.

### Fine-word result (`mdac_fineword.py`, N = 200 per corner)
| Corner | Samples with a falling boundary | Drops per sample, median / max | Worst drop | At major carries (w % 32 = 31) |
|---|---|---|---|---|
| tt | 200 / 200 | 451 / 1020 | 0.930 LSB (28.9 kHz) | 3235 of 89 895 |
| ss | 200 / 200 | 461 / 1023 | 0.878 LSB (24.1 kHz) | 3258 of 90 570 |
| ff | 200 / 200 | 447 / 1019 | 0.981 LSB (34.9 kHz) | 3221 of 89 510 |

The raw count is dominated by tiny drops. The ΣΔ cell is one unit, the same as the LSB step, so in an ideal DAC the
margin of the theorem's condition (step > 255/256 cell) is only 1/256 LSB; with mismatch about half of all boundaries
fall, at every carry level. Breaking the drops down by size (a scratch script on the same logs, not committed):

| Corner | Samples with a drop > 0.1 LSB | > 0.25 LSB | > 0.5 LSB | Largest drop below a major carry |
|---|---|---|---|---|
| tt | 189 / 200 | 136 / 200 | 30 / 200 | 0.381 LSB (carry into bit 4) |
| ss | 188 / 200 | 125 / 200 | 26 / 200 | 0.359 LSB (carry into bit 4) |
| ff | 190 / 200 | 139 / 200 | 40 / 200 | 0.402 LSB (carry into bit 4) |

Every drop over 0.5 LSB is at a major carry (carry into bits 5-9). The worst at all three corners is seed 5102 at
word 319 (carry into bit 6).

### Draft text for `docs/tx_fine_tune.md` (not applied)
- Replace "How often it happens is being measured (`docs/handoff_mdac_fineword.md`)." with: "A Monte Carlo of the
  fine word (N = 200 per corner, `mdac_fineword.py`) finds a falling boundary in every sample: the ΣΔ cell and the
  LSB step are the same unit, so about half of all boundaries fall by a few hundredths of an LSB. Drops over 0.25 LSB
  occur in 63-70 % of samples and drops over 0.5 LSB in 13-20 %, all at major carries (w % 32 = 31); the worst is
  0.93 / 0.88 / 0.98 LSB (28.9 / 24.1 / 34.9 kHz) at tt / ss / ff."
- Note after Table III: "Table III checks that every coarse step stays positive (DNL > −1). The fine word needs
  more: across (w, 255) → (w + 1, 0) the mean output only rises if the step exceeds 255/256 of the ΣΔ cell (the Lean
  proof `fine_boundary`, `mattvenn/circuit-design-learnings`, which is why this check was added). It fails somewhere
  in every sample (results above). The counting servo measures frequency, so it tolerates this; a binary search or an
  FSK offset that assumes monotonicity across a word boundary does not, and should either avoid fractions near 255
  or verify by counting."
- Table III and the summary row: decide whether to replace them with this run's numbers (seeds 5000-5199).

## Done
Replace the first line with `> Done (date): <share of samples with a falling boundary> tt / ss / ff, worst <x> LSB;
see docs/tx_fine_tune.md`.
