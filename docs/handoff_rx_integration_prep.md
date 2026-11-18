> Superseded (2026-11-17) by docs/handoff_tile_layout.md, which folds in parts A-C. Not to be started.

# Handoff: prepare the tile for the receiver (rx_en SPI bit, pins, VAPWR split, a2 pin) (sim server)

**Goal: get every block and pin ready for the receiver's floorplan, without placing the receiver.** Three decisions
from Matt (2026-11-16) are implemented here, so the floorplan can start from blocks whose pins and supplies are final:
1. **rx_en is an SPI register bit,** CTRL[4] in `tx_fine` (resets to 0: the receiver is off after reset).
2. **Supply split:** the quiet analog (the VCO: `vco_top` with the ring, `cgm_ref`, the coarse DAC and `lsdiv`;
   `mdac`; `vctrl_pd`) and the receiver go on **VAPWR**; the noisy blocks (the TX driver `tx_drv` and the digital
   macro `tx_fine`) stay on **VDPWR**. **VAPWR is set to 3.3 V,** the same as VDPWR, so signals cross between the
   two domains without level shifters.
3. **Pins:** the receiver's antenna on **ua[4] / ua[5]**, its outputs q_i / q_q on **uo[4] / uo[5]**.

The floorplan itself (placing and reshaping `rx_top`, which at 299 × 376 µm is taller than the 325.36 µm tile) is
**not** in this handoff: Matt wants to look at it first.

## Where things are
- **Branch: `rx-option-b`.** Clone it: `cd /foss/designs && git clone -b rx-option-b
  https://github.com/mattvenn/gf-433-oscillator.git gf433-rx-prep`. Commit and push to `rx-option-b` only,
  `git pull --rebase --autostash` before every push. Never push to `main`.
- **Read first:** `docs/tx_fine_tune.md` (the macro, its register map, Table VI, and how it was hardened),
  `docs/rx_layout.md` ("Before the second pass" and "Integration"), `docs/top_layout.md`, `docs/platform.md`
  ("Supplies and pins").
- **Files involved:** `src/tx_fine.v`, `test/test_tx_fine.py` (cocotb), `macro/tx_fine/config.json`,
  `macro/tx_fine/pin_order.cfg`, `src/project.v`, `info.yaml`, `layout/gen/vco_top.py`, `layout/gen/tt_wrapper.py`,
  `lvs/make_source.py`, and the checks `layout/gen/check_top.sh`, `layout/gen/pex_top.sh`, `layout/gen/check_tt.sh`.
- **Ownership:** you own the files above and `build/rx_prep/`. Don't edit any `rx_*` cell, any schematic under
  `xschem/`, or anything under `sim/`. Stage and commit in one command, never `git add -A`; never commit `build/` or
  `sim.yaml`. At most 8 CPUs.

## Part A: the rx_en bit in tx_fine
1. **RTL** (`src/tx_fine.v`): widen `ctrl` from 4 to 5 bits; CTRL[4] = RX_EN, reset 0. Add an output port `rx_en`
   driven by it. The read-back mux returns all 5 bits. Update the register-map comment at the top of the file.
2. **Tests** (`test/test_tx_fine.py`): add a test that RX_EN resets to 0, can be written to 1 and back, reads back
   correctly, and doesn't disturb CTRL[3:0]. Run the whole suite: every existing test must still pass.
3. **Mutation test:** on a copy of the RTL, tie `rx_en` to 0 (or drop the bit from the write decode); the new test
   must fail. Record it next to the three existing RTL mutations.
4. **Re-harden** with LibreLane, as in `docs/tx_fine_tune.md`. Add `rx_en` to `pin_order.cfg` on the side facing where
   the receiver will be (the tile's right half; say which side you chose and why). **Keep the die area** in
   `config.json` unchanged if it closes; if it doesn't, grow it by the smallest step and report the new size, because
   the floorplan depends on it. It must close timing at 25 MHz tt (as before) with no DRC, LVS or antenna errors.
5. **Docs:** add RX_EN to the register map (Table VI) in `docs/tx_fine_tune.md` and to the `info.yaml` description.

## Part B: the a2 pin on vco_top
`vco_top`'s layout has no `a2` port yet, so `pex_top.sh` stops on it (`docs/rx_layout.md`). Bring the ring's a2 node
out of `ring_core_v3` to a `vco_top` pin, on the edge facing the receiver, with **the shortest wire you can**: every
femtofarad on a2 slows the ring and shifts the I/Q phase (`docs/rx_layout.md`, LO section). Report the wire's extracted
C. Then re-run `check_top.sh` (LVS against the xschem `vco_top`, which already has the `a2` port) and `pex_top.sh`.

## Part C: pins and supplies in the tile
1. **`info.yaml`:** `analog_pins: 6`; ua[4] = "RX in_p", ua[5] = "RX in_n" (433.92 MHz receive dipole); uo[4] = "RX q_i",
   uo[5] = "RX q_q" (I / Q limiter bits, for the RP2350 PIO quadrature decoder). In the description: **VAPWR must be set to
   3.3 V** (the same as VDPWR), because signals cross between the two supplies with no level shifters.
2. **`src/project.v`:** uncomment the VAPWR port.
3. **Tile power** (`layout/gen/tt_wrapper.py`, `lvs/make_source.py`): move to the `_pgvaa` template (VAPWR stripes,
   `def/analog/magic_init_project.tcl`, `docs/platform.md`). Connect the supply of `vco_top` (VDD and VDD_LS), `mdac`
   and `vctrl_pd` to **VAPWR**; keep `tx_drv` and `tx_fine` on **VDPWR**; VGND is shared. Keep each block where it is
   (no re-placement), and leave an empty, reserved region for the receiver: say where, and how big it can be.
4. **Signals that now cross supplies** (list them in the report, with their source and destination rails):
   `ls` (vco_top on VAPWR → tx_drv on VDPWR), `ck` (vco_top → tx_fine), the 37 DAC control lines (tx_fine → mdac),
   the coarse-code bits (pins → vco_top), and later rx_en (tx_fine → receiver) and q_i / q_q (receiver → uo pins). All
   are 3.3 V to 3.3 V, so they need no level shifter, but each one is a place where the two grounds and supplies meet.
5. **Tile checks:** `check_tt.sh` (LVS with its mutations, DRC, antenna) and the TT precheck must pass.

## Re-simulation (short, to show nothing broke)
- The macro: the gate-level simulation of the re-hardened netlist, if `docs/tx_fine_tune.md` has one.
- vco_top with the new a2 wire: the extracted ring frequency at tt, code 9, vctrl 1.65 V, against the value in
  `docs/top_layout.md`. A change above 0.1 % needs an explanation.
- Corners: tt only, 27 °C, 3.3 V (no circuit change, only wiring).

## Report and commit
Add a section "Integration prep (2026-11-xx)" to `docs/top_layout.md`: the macro's new size and pin, the a2 wire and its
C, the supply map (which block is on which rail, with a figure of the tile), the crossing signals, the reserved
receiver region, check results with log paths, and anything the floorplan should know. Update `STATUS.md`'s
receiver item.

## Running unattended
1. **Never end a turn with untracked work running.** Start long jobs (hardening, extraction) with the Bash tool's
   `run_in_background: true`, not `nohup … &`.
2. **One driver script** (`layout/gen/rx_prep_driver.sh`): RTL tests → mutation → harden → vco_top → tile → checks →
   summary. Each step writes `build/rx_prep/status.txt`; the last writes `build/rx_prep/DONE` or `FAILED`.
3. **Fail loudly and early:** each step checks its own outputs ("Circuits match uniquely", 0 DRC, timing met, tests
   passed) before the next. On failure, stop with the log tail; retry at most twice, then write up and stop.
4. **Heartbeat:** a wakeup at about 1.5× the step's estimated time, at least 20 and at most 60 minutes; re-arm it.
5. **Progress:** replace the first line of this file with `> Running: step N/M since HH:MM, ETA HH:MM` at each step
   change, commit and push. PushNotification when done or failed, if available.
6. **Finish in one go:** write up, commit and push without waiting to be asked.

## Traps (from this project)
- **KLayout gf180 DRC needs `feol=true beol=true`**, or it silently runs zero rules. **magic 8.3.642** for extraction,
  and simulate `rcfix.py`'s output, never the raw `rc` netlist.
- `tools/osic-mac` doesn't pass env vars into Docker: use `tools/osic-mac env K=V cmd`.
- Frequency in the ring is measured at **mid-swing**.
- **Mutation-test every checker you touch.** Judge runs by their output files and log tails, not exit codes.
- `rm` is aliased to `rm -i`: use `command rm -f`.

## Not in scope
- Placing, reshaping or wiring `rx_top` in the tile (the floorplan, with Matt).
- Any change inside the receiver cells, the VCO's circuits, or any device size.
- The other open review items (the Q tap gating, the filter order).

## Done
When pushed, replace the first line with `> Done (date): see docs/top_layout.md, "Integration prep"` and a one-line
result (macro size, a2 wire C, checks).
