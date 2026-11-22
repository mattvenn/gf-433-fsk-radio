> Done (2026-11-16): see docs/rx_layout.md, Table S2. Second-pass FSK through the real LO at -70 dBm, tt: 0 errors of 4, steps -8/+8/-8/+8 (first pass -8/+7/-7/+7), 1 glitch < 1 us, LO I/Q 72.8 deg, 7.36 mA, 6.6 h.

# Handoff: FSK decode on the second-pass receiver layout (sim server)

**Goal: run the FSK chain through the real ring LO on the second-pass extracted `rx_top`, at −70 dBm and tt, and fill
the one empty result in `docs/rx_layout.md`** (Table S2, row "FSK decode, −70 dBm, tt", column "Second pass", which
now says "not re-run"). Nothing else changes: no layout, no extraction, no schematic.

Why: the second pass (2026-11-16, commit 8daca41) trimmed the empty space in the receiver cells (rx_top 131,434 →
112,573 µm²) without changing any device size. Every other bench was re-run on the new extraction and moved by at
most 0.3 dB / 0.2°, but the 9-hour chain run was stopped before it finished. The first pass decoded 0 of 4 bits wrong,
with steps −8, +7, −7, +7 (the same as the schematic). This run checks the second pass does the same.

## Where things are
- **Branch: `rx-option-b`** (the receiver is only there). Clone it:
  `cd /foss/designs && git clone -b rx-option-b https://github.com/mattvenn/gf-433-fsk-radio.git gf433-rx-chain2`.
  Commit and push to `rx-option-b` only, `git pull --rebase --autostash` before every push. Never push to `main`.
- **The bench:** `layout/gen/rx_pexbench.py chain` (the `sim/rx/rx_chain.py realfsk` flow with the extracted
  `rx_top`, C only, and the extracted `lsdiv` on a0). Its inputs are committed: `layout/pex/rx_top_c.spice` (second
  pass) and the lsdiv extraction. **No extraction is needed**, so magic's version doesn't matter here.
- **Results so far:** `docs/rx_layout.md`, section "Second pass: empty space trimmed", Tables S1 and S2. The
  first-pass chain result is Table IX and `docs/rx_layout_results/chain.json`.
- **Ownership:** you own `build/rx_chain2/`, `docs/rx_layout_results/second_pass/chain.json`, this handoff, and the
  FSK row / summary sentence of `docs/rx_layout.md`. Don't edit anything else.
- **Resources:** one ngspice process at nice 19 (the driver does that). Stage and commit in one command, never
  `git add -A`; never commit `build/` or `sim.yaml`.

## Config (edit here, not in the script)
- Level −70 dBm, corner tt, 27 °C, 3.3 V (as the first pass and the schematic run): `CHAIN_LEVEL` at the top of
  `layout/gen/rx_chain2_driver.sh`.

## Run
1. Read this handoff and `docs/rx_layout.md` (summary, "Second pass", Table IX).
2. Start the driver from the repo root with the Bash tool's `run_in_background: true`:
   `bash layout/gen/rx_chain2_driver.sh`
   - step 1, smoke test (under 1 minute): the extracted rx_lim's hysteresis must come out at ±36.3 mV. If it
     doesn't, the server's ngspice or PDK models differ from the laptop's: stop and report, don't run the chain.
   - step 2, the chain: about 9 h (8.7 h on the first pass; 53 min of it is the pre-run that checks the ring has
     settled). Log `build/rx_chain2/chain.log`.
   - step 3, output checks; then `build/rx_chain2/DONE` (or `FAILED` with the log tail).
   Each step pushes this file's first line (`> Running: step N/3 ...`).
3. Heartbeat: schedule a wakeup about every 60 minutes (re-arm it each time) in case a notification is missed.
   Check `build/rx_chain2/status.txt` and the log tail for "singular" or "Transient op" failures.

## Write-up (straight after DONE, without waiting to be asked)
1. Copy `build/rx_chain2/chain.json` to `docs/rx_layout_results/second_pass/chain.json`.
2. In `docs/rx_layout.md`:
   - Table S2, row "FSK decode, −70 dBm, tt": replace "not re-run" with the result, e.g. "0 of 4 errors, steps −8,
     +7, −7, +7". If the result differs from the first pass, add rows for the steps per bit, LO I/Q phase at the
     mixer switches (`lo_iq_phase`), supply current (`idd_ma`) and ring drift (spread of `f_ring_track`), as in
     Table IX.
   - The paragraph under Table S2 that says the chain "was stopped on the second pass ... that is not checked":
     replace it with the result.
   - The summary paragraph at the top: the sentence "it was not re-run on the second pass (below)" → the result.
3. Set this handoff's first line to `> Done (YYYY-MM-DD): see docs/rx_layout.md, Table S2` plus the one-line result,
   and update the FSK clause of the first line of `docs/handoff_rx_layout.md` the same way.
4. Commit only those files, push, and send Matt a PushNotification with the result (bit errors and steps).

**Stop rules:** any bit error, a step count off the first pass by more than 2, or an LO I/Q phase outside 72 ± 25°:
still write it up and push, but put the problem first in the Done line and the notification. Don't change any
layout or device to fix it; that is Matt's decision.

## Rules for the server agent (from `docs/handoff_autonomy.md`)
1. Never end a turn with untracked work running: start the driver with `run_in_background: true`.
2. One driver (`layout/gen/rx_chain2_driver.sh`), every step chained in it; each step checks its own outputs and
   writes `build/rx_chain2/status.txt`; the end writes `DONE` or `FAILED`.
3. Fail loudly: on `FAILED`, diagnose and retry at most twice, then write up and stop.
4. Heartbeat fallback: a wakeup at most 60 minutes apart, re-armed each time.
5. Progress where the laptop can see it: the `Running` line at each step change, the `Done` line at the end, a
   PushNotification when it finishes or fails.
6. Finish the whole brief in one go: write up, commit and push straight after the driver ends.
