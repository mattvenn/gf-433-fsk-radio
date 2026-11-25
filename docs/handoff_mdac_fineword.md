> Not started.

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

## Done
Replace the first line with `> Done (date): <share of samples with a falling boundary> tt / ss / ff, worst <x> LSB;
see docs/tx_fine_tune.md`.
