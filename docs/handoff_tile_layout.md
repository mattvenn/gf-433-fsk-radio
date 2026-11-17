> Running: step 3/5 (close the floorplan on the real blocks) since 10:40. Steps 1-2 done (every re-laid-out cell CHECK OK).

# Handoff: move the block pins to the agreed floorplan, then lay out the tile with the real blocks (sim server)

**Goal: the 2x2 tile (`_pgvaa` template) laid out as the agreed floorplan, with every block's pins where the
floorplan wants them, the receiver and the debug mux in it, and the tile clean in DRC (magic and KLayout), LVS
(with mutations) and antenna, and passing the TT precheck.** The floorplan was agreed with Matt on the floorplan page
(2026-11-17): variant **"B - Matt's edit, tidied: pins moved on 13 blocks"**. Its data is in the repo; this handoff
turns it into GDS. Write it up in `docs/tile_layout.md`.

This handoff **replaces `docs/handoff_rx_integration_prep.md`** (never started): its rx_en bit, a2 pin, VAPWR split,
pins and `info.yaml` work are folded in below.

## Where things are
- **Branch: `floorplan`.** It has everything (`rx-option-b` plus the floorplan tool). Clone it:
  `cd /foss/designs && git clone -b floorplan https://github.com/mattvenn/gf-433-oscillator.git gf433-tile`.
  Commit and push to `floorplan` only, `git pull --rebase --autostash` before every push. Never push to `main` or
  `rx-option-b`.
- **The floorplan (read these first):**
  - `docs/floorplan_spec.md`: the tool, the rules, why the floorplan looks as it does (the debug mux, the vco_top
    split, the pin study);
  - `layout/floorplan/floorplan.json`: every block's placement (`x`, `y` = lower-left of the placed bbox; `orient`,
    `rot`, `mirror` as a KLayout `DCplxTrans`; `transform` says how), the stripes, the decap rectangles, the
    reshaped macro's size, and `pins_moved` (each moved pin's target `[x, y]` in the block's own frame);
  - `layout/floorplan/pins.md`: the same per block, every pin by edge with **moved** pins marked and the edge each one
    came from, and the supply crossings;
  - the page itself (https://claude.ai/artifact/942zW17HYnwDF8qCuYhQk3) needs a claude.ai login; everything it shows
    is reproducible from the repo: `node layout/floorplan/page/check.js layout/floorplan/floorplan.json` prints the
    checklist, `node tools/floorplan_dump.js layout/floorplan/floorplan.json > f.json && python3
    tools/floorplan_draw.py f.json f.png --pins` draws it.
- **Blocks and their generators:** `layout/gen/ring_core_v3.py`, `lsdiv.py`, `cgm_ref.py`, `vco_top.py` (the
  abutments and the VDD_LS decap), `mdac.py`, `vctrl_pd.py`, `tx_drv.py`, `rx_lna.py`, `rx_bias.py`, `rx_lsq.py`,
  `rx_lobuf.py`, `rx_mix.py`, `rx_bb.py`, `rx_lim.py`, `rx_top.py` (the receiver's assembly, its A* router and
  `rx_decap`), `rx_lib.py`; the macro in `macro/tx_fine/` (`config.json`, `pin_order.cfg`), RTL `src/tx_fine.v`,
  tests `test/test_tx_fine.py`; today's tile `layout/gen/tt_wrapper.py` and its LVS source `lvs/make_source.py`.
- **Block checks to copy:** `layout/gen/check_top.sh` (vco_top), `check_ref.sh`, `check_lsdiv.sh`, `check_v3.sh`,
  `check_tx.sh`, `check_rx_block.sh`; the tile: `check_tt.sh` (LVS with 7 mutations).
- **Docs:** `docs/top_layout.md` (vco_top, the tile today), `docs/rx_layout.md` (the receiver cells, Table S1, the
  LO section), `docs/rx_design.md`, `docs/tx_fine_tune.md` (the macro, its register map Table VI, how it was
  hardened), `docs/platform.md` ("Supplies and pins").
- **Project skill:** `.claude/skills/mixed-signal-asic/` (`references/layout-sky130.md`, `verification.md`,
  `floorplan-power.md`); written for sky130, adapt to gf180mcuD.
- **Ownership:** you own everything you add for this (`layout/gen/tile.py`, new cells, `build/tile/`,
  `docs/tile_layout.md`, this handoff) and you may edit the block generators listed above, `src/tx_fine.v`,
  `test/test_tx_fine.py`, `macro/tx_fine/*`, `lvs/make_source.py`, `info.yaml`, `src/project.v`. Don't change any
  device size or schematic topology (see "Don't change"). Stage and commit in one command, never `git add -A`; never
  commit `build/` or `sim.yaml`. At most 8 CPUs.

## Decisions already made (Matt, 2026-11-16 / 17) — don't revisit
- **Template:** `tt_analog_2x2_pgvaa.def` (693.28 × 325.36 µm; every pin 17.92 µm left of the plain 2x2's).
- **Supplies:** VAPWR (3.3 V): vco_top's parts (VDD and VDD_LS), mdac, vctrl_pd, the code inverters, the receiver,
  the debug switches. VDPWR: tx_drv, tx_fine. VGND shared. All crossing signals are 3.3 V to 3.3 V, no level shifters
  (`pins.md` lists them).
- **Pins:** ua[0] the debug mux; ua[1] unused; ua[2] / ua[3] TX out_n / out_p; ua[4] / ua[5] RX in_p / in_n; uo[0:3]
  ck and the dividers; uo[4] / uo[5] q_i / q_q; ui[0:4] coarse code; ui[5:6] TX enables; ui[7] FSK; uio[0:3] SPI.
  Six analog pins (`info.yaml`: `analog_pins: 6`).
- **rx_en** is an SPI bit, CTRL[4] in tx_fine, reset 0.
- **Debug mux on ua[0]:** four switches, one next to each source: baseband I (rx_bb I `outp`), baseband Q (rx_bb Q
  `outp`), the receiver bias `nb`, and `vctrl`. Each is our own 3.3 V transmission gate (not TT's `tt_asw_5v0`).
  Selected by four SPI bits `dbg_sel[3:0]` in tx_fine, all 0 after reset; at most one should be on (firmware's job,
  no hardware interlock needed).
- **vco_top is split** into: the ring + lsdiv unit (their a0 abutment kept, no a0 wire), `cgm_ref`, and the VDD_LS
  decap. vbnf and vctrl between cgm_ref and the ring become wires (108 / 99 µm in the floorplan).
- **The receiver is placed as its cells,** not as `rx_top`.
- **The macro is re-hardened at 250 × 177 µm** (same area as now, 44,200 µm²), placed MY, with its pins where
  `pins.md` puts them (TT pins on the edge facing the top, the 37 DAC lines on the edge facing mdac, rx_en and
  dbg_sel toward the receiver).

## What to do

### 1. tx_fine: RTL, tests, re-harden
1. `src/tx_fine.v`: CTRL[4] = RX_EN (reset 0) with an output `rx_en`; a new register (next free address in Table VI)
   with DBG_SEL[3:0] (reset 0) and outputs `dbg_sel[3:0]`. Read-back for both. Update the register-map comment.
2. `test/test_tx_fine.py`: tests for both (reset values, write / read back, no effect on the other bits); the whole
   suite must still pass. Mutation-test each new test (tie an output to 0 in a copy: the test must fail).
3. `macro/tx_fine/config.json`: die 250 × 177 µm. `pin_order.cfg` from `pins.md` (section `xmac`): the edges and the
   order along each edge as given there, in the macro's own frame (it is placed MY: check which LibreLane side that
   is, and say so). Harden with LibreLane as in `docs/tx_fine_tune.md`. It must close timing at 25 MHz tt with no DRC,
   LVS or antenna errors. If it doesn't close at 250 × 177, grow it by the smallest step, report the size, and carry it
   into step 5. Gate-level sim of the hardened netlist if `docs/tx_fine_tune.md` has one.
4. Docs: Table VI in `docs/tx_fine_tune.md`, `info.yaml`'s description (VAPWR = 3.3 V; the pins above).

### 2. Block pin moves (the re-layouts)
For every block marked in `pins.md`, change its **generator** so its pins land on the edges `pins.md` gives, as close
as the internal layout allows to the positions given (they are targets from a placer, accurate to a few µm at best).
Moving a pin to another edge means re-routing inside the block, not adding a long wire round it. Keep every device
and its matching as it is.

| Block | Pins to move (details in `pins.md`) | Notes |
|---|---|---|
| ring + lsdiv unit (new cell, e.g. `vco_core`, from `vco_top.py`'s ring + lsdiv + the under-lsdiv decap fingers) | a2 out to the edge facing rx_lsq; ck to the edge facing the macro, **away from vbnf**; vg, vctrl, vbnf, ls, bit pins as `pins.md` | a2 is a ring node: shortest possible stub, report its C (`docs/rx_layout.md`, LO section). Keep the lsdiv a0 abutment |
| cgm_ref | vbnf and vctrl (both ends of the feed-through) to the edge facing the ring | |
| VDD_LS decap | none | its own small cell |
| mdac | vg and vbnf to the edge facing the ring | |
| tx_drv | out_n onto the same edge as out_p, facing the pads; ls and the enables to the opposite edge | outputs stay wide (12.6 mA) |
| rx_lna | I and Q RF outputs to the edges facing their mixers; the inputs at the ua[4] / ua[5] spacing | keep stage 1's common centroid |
| rx_bb (I and Q) | outputs to the edge facing their limiter; nb / enb toward rx_bias | **one cell for both arms** (below) |
| rx_lim (I and Q) | nb / enb toward rx_bias; q as `pins.md` | one cell for both |
| rx_lsq | lsq out toward the Q LO buffer | keep lsdiv's geometry (I/Q phase) |
| rx_lobuf (Q copy moved) | `in` / `en` as `pins.md` | one cell for both |
| rx_mix (I copy moved) | rf inputs to the edge facing the LNA | one cell for both |
| rx_bias | en, nb, enb to the edge facing the receiver | |

**The I and Q copies stay one cell each** (rx_bb, rx_lim, rx_lobuf, rx_mix: matched, `docs/rx_layout.md`). The
floorplan fitted each copy's pins separately, so the two copies' targets can differ. Choose one pin arrangement per
cell that serves both copies through their orientations (a mirror is fine), and change a copy's orientation in the
floorplan if that's what it takes. Say what you chose.

New cell: **`dbg_tg`**, the debug switch: one nfet_03v3 and one pfet_03v3 in parallel (W about 2–5 µm, minimum L)
plus an inverter for the complement gate drive, on VAPWR; pins `mod` (to the source), `bus` (to ua[0]), `ctrl`
(from tx_fine). Make an xschem schematic (the LVS source) the same way the other cells' are made, and a generator.
Estimated 15 × 12 µm; report its real size. Where `floorplan.json` puts a switch inside its source block (rx_bb I,
rx_bias…), add it to that block's layout instead, next to the source node.

Per cell: magic DRC, KLayout DRC (`feol=true beol=true`), LVS against its schematic with at least one mutation, and
antenna, with the existing check scripts.

### 3. Close the floorplan on the real blocks
1. Extend `tools/floorplan_blocks.py` to the new cells (the ring + lsdiv unit, cgm_ref and the decap as their own
   cells; `dbg_tg`) and regenerate `layout/floorplan/blocks.json`. Point the engine's `VCO_PARTS` and the debug
   switch entries (`layout/floorplan/page/engine.js`) at the real cells instead of the hard-coded sizes / estimates,
   and give tx_fine its new LEF pins.
2. Take `floorplan.json`, drop `pins_moved` (the blocks now have the pins), import it, and run
   `node layout/floorplan/page/check.js`. **No rule may fail.** If a block grew or a pin landed elsewhere, move blocks
   the least you can to get there (the page's placement is the reference), and record every change. Write the result
   back with `node layout/floorplan/page/pinreport.js` (it rewrites `floorplan.json` and `pins.md`).
3. Push this step before starting the tile, so Matt can look at it on the page.

### 4. The tile: `layout/gen/tile.py`
A new generator (keep `tt_wrapper.py` as it is, for reference) that reads `layout/floorplan/floorplan.json` and
writes `gds/tt_um_mattvenn_gf433_vco.gds` and its LEF:
- the `_pgvaa` DEF's pins (`tools/floorplan_tile.py` parses it; `tt_wrapper.py` shows how they are drawn);
- every block at its `floorplan.json` placement;
- the Metal4 stripes from `floorplan.json` (VDPWR, VAPWR, VGND; y 5 … 320.36; over the macro only on its own straps),
  with via3 landings on every block's rails, and decap in the `floorplan.json` rectangles (reuse `rx_decap`'s style:
  nfet gate caps, gate on the supply, on its own supply's stripe);
- the code inverters + antenna diodes and the tie cells as `tt_wrapper.py` has them, moved to the new positions;
- all signal nets: reuse `rx_top.py`'s A* router (M2 horizontal / M3 vertical) at tile level. Constraints:
  - no clock, digital, DAC, enable, LO or debug wire over a receiver cell (the floorplan's rule 6);
  - the baseband → limiter pairs routed as differential pairs with VGND shields, away from q_i / q_q;
  - vbnf and vctrl from cgm_ref to the ring as guarded wires (VGND both sides), ck kept away from them;
  - ls and lsq routed so their lengths stay close (I/Q LO load match; they were 163 / 149 µm in the floorplan);
  - tx_drv's outputs wide (12.6 mA; `tt_wrapper.py` used 8 µm) and short to ua[2] / ua[3];
  - the debug bus from each switch to ua[0] round the receiver;
  - no Metal5.
- `lvs/make_source.py`: the source becomes the TT top with every block as its own subcircuit (the vco_top schematic
  split the same way, the receiver cells from their xschem netlists, `dbg_tg` × 4, the hardened macro's netlist, the
  standard cells), with VAPWR / VDPWR / VGND per the supply map.

### 5. Checks (one driver: `layout/gen/tile_driver.sh`)
Harden (if not done) → block checks → `tile.py` → magic DRC → KLayout DRC (`feol=true beol=true`) → LVS
(`check_tt.sh` adapted) → antenna → TT precheck → summary. Each step checks its own output and stops on failure.
- **LVS mutations** (each must FAIL): keep `check_tt.sh`'s seven where they still apply, and add: (a) ua[4] / ua[5]
  swapped at the LNA; (b) q_i / q_q swapped at uo[4] / uo[5]; (c) two debug switches' `dbg_sel` swapped; (d) a2 and
  ls swapped at the receiver; (e) one receiver cell on VDPWR instead of VAPWR; (f) vbnf and vctrl swapped at cgm_ref.
- Judge by the output files and log tails, not exit codes. KLayout gf180 DRC needs `feol=true beol=true` or it runs
  zero rules: check the rule count in the report. Extract with magic **8.3.642**.

## Don't change
Any device size or schematic topology (other than adding `dbg_tg` and the RTL bits above); the open receiver review
items as the schematic has them (qenb tied to VSS, the two-pole filter); the decisions listed above. If something in
the floorplan can't be built (a pin that can't reach an edge, a route with no way through), stop that item, record
why, and carry on with the rest; then ask Matt.

## Running unattended (`docs/handoff_autonomy.md`)
1. **Never end a turn with untracked work running.** Long jobs (hardening, DRC, LVS, extraction) with the Bash tool's
   `run_in_background: true`, never `nohup … &`.
2. **One driver for the check run** (`layout/gen/tile_driver.sh`, step 5): each step writes
   `build/tile/status.txt`, the last writes `build/tile/DONE` or `FAILED` with the log tail.
3. **Fail loudly and early;** retry a failed step at most twice, then write up and stop.
4. **Heartbeat:** a wakeup at about 1.5× a step's estimated time, at least 20 and at most 60 minutes; re-arm it.
5. **Progress:** replace the first line of this file with `> Running: step N/5 (<what>) since HH:MM, ETA HH:MM` at
   each step change (steps 1–5 above), commit and push. PushNotification when done or failed, if available.
6. **Finish in one go:** write up, commit and push without waiting to be asked. Push at the end of each step too
   (the steps are long; Matt reviews step 3 on the page).

## Traps (from this project)
- `tools/osic-mac` doesn't pass env vars into Docker: `tools/osic-mac env K=V cmd`.
- magic **8.3.642** for extraction (8.3.684 drops substrate C); magic `rc` double-counts coupling C on ports: use
  `layout/gen/rcfix.py`'s `_rcx.spice` if you extract.
- magic's gf180mcuD tech can't read the n-well resistor back from GDS: `check_tt.sh` repaints `rnw` in `cgm_ref` from
  NWELL & RES_MK after `gds read`; keep that.
- `flatten -dotoplabels` keeps only the top cell's labels, so the blocks' own VDD labels can't short VDD to VDD_LS by
  name (`docs/top_layout.md`).
- The GF180 DCF.1a rule (no 20 × 20 µm area without active): `layout/gen/rx_fill.py` fills free areas with dummy
  COMP on 22/4.
- `rm` is aliased to `rm -i`: use `command rm -f`.
- **Mutation-test every checker you touch.**

## Not in scope
- Re-simulation. Next, after this: the VCO on the extracted tile with the real vbnf / vctrl / a2 wires (tt, code 9,
  against `docs/top_layout.md`), and the receiver chain on the tile extraction (`docs/rx_layout.md`'s benches).
- Changing the floorplan beyond what step 3 needs.

## Done
When pushed, replace the first line with `> Done (date): see docs/tile_layout.md` and a one-line result (macro size,
block pin moves done / not done, DRC / LVS / antenna / precheck, mutations caught).
