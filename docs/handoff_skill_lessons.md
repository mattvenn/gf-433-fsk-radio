> Done (2026-11-18): claude-config c0633c2 (lessons added; GF180 facts in references/gf180.md). Lessons already covered were skipped.

# Handoff: carry this project's lessons into the mixed-signal-asic skill (an agent with `claude-config` checked out)

**Goal: add the lessons below to the canonical `mixed-signal-asic` skill in `mattvenn/claude-config`.** This project
(GF180 VCO and FSK receiver for Tiny Tapeout) learned them, but they only exist in this repo's docs: the skill hasn't
been updated since it was copied in (`.claude/skills/mixed-signal-asic/`, commit 45f04db), and the cloud session that
found the gap can't reach `claude-config`.

## How
1. Read the skill's `SKILL.md` and `references/` in `claude-config` first, and check each lesson isn't already there
   (the canonical copy may be newer than the one in this repo).
2. For each lesson, open its source below and write it in the skill's own style: the trap in one or two lines, then the
   fix. **Keep lessons general where they are general**; put GF180-specific facts in a new `references/gf180.md`
   (the skill is sky130-only today), and link it from `SKILL.md`.
3. Commit to `claude-config` with a message that names this project as the source, and push.
4. Copy the updated skill into this repo's `.claude/skills/mixed-signal-asic/` on branch `rx-option-b` (so the project
   copy matches), commit and push.
5. Replace the first line of this file with `> Done (date): claude-config <commit>` and push.

Sources are on branch `rx-option-b` of `mattvenn/gf-433-fsk-radio`.

## General lessons (into `SKILL.md` or the matching reference)

| Lesson | Source |
|---|---|
| **netgen treats PDK resistors as black boxes:** it doesn't compare their W / L, so a wrong-size resistor passes LVS even with "fail on property errors". Add a device-by-device size diff (every MOS W / L / m and every resistor W / L) next to LVS. Put this beside the existing circular-LVS note. | `xschem/gen/check.py`, `docs/schematics.md` ("Checks"), `docs/rx_layout.md` ("Checks") |
| **magic `rc` extraction double-counts coupling C** on ports and split nets (their total C goes to VSS *and* the coupling caps stay). Always simulate a fixed netlist. Here the error made the extracted VCO read 0.87× the schematic; the truth was 0.98×. | `docs/rc_extraction_fix.md`, `layout/gen/rcfix.py` |
| **A copy of a block's schematic is not a match:** two level shifters from the same schematic delayed by 119° and 55° at 434 MHz, because the laid-out one had 1.4 fF on its input node against 0.4 fF. Anything that must match (I / Q paths, replicas) must copy the **layout and the load**, not just the schematic. | `docs/rx_design.md` ("LO taps (A1)"), `docs/rx_layout.md` (LO section) |
| **MOS caps: check the DC bias and which terminal faces the sensitive node.** An NMOS AC-coupling cap's junction leakage fought a > 1 GΩ bias element and biased the next stage off (0.56 V instead of 1.30 V); a PMOS with its gate on the high-Z node fixed it. | `docs/rx_design.md` ("The AC coupling") |
| **Long server runs** (the "Running unattended" block): start jobs with `run_in_background`, never a bare `nohup`; one driver per handoff with status / DONE / FAILED files; fail early on output checks; a heartbeat wakeup; push a `Running: step N/M` line at each step; write up in the same session. Tested: results pushed under 2 minutes after the last sim. | `docs/handoff_autonomy.md` |
| **Corner policy:** the full corner set once per circuit change to find the 3–4 bounding corners, iterate on those, full PVT plus Monte Carlo only at sign-off on the extracted layout. | `docs/handoff_autonomy.md` ("Corner policy") |
| **ngspice:** sources whose PULSE breakpoints nearly coincide stop a long transient ("timestep too small" at the same time every run): use smooth sources or full-precision timing. Some operating points need `option rshunt=1e12` (or `gmin`) to converge. | `docs/rx_design.md` ("Ideal LO in the chain benches"; the rx_en notes under Table II) |
| **Measure a ring's frequency at mid-swing,** not VDD/2, when the ring doesn't swing rail to rail (a current-fed ring swings vg…VDD and never crosses VDD/2). | this repo's `CLAUDE.md` ("Tool traps"), `docs/schematics.md` |
| **xschem-viewer** only knows the xschem, sky130 and IHP libraries: copy the PDK symbols you use next to the `.sch` (here `xschem/symbols/`) and reference them by the same relative name. | `docs/schematics.md` ("Notes") |

## GF180 / Tiny Tapeout GF facts (into a new `references/gf180.md`)

| Fact | Source |
|---|---|
| KLayout gf180mcu DRC needs `feol=true beol=true`, or the deck can silently run zero rules (print the rules that ran). | `CLAUDE.md` ("Tool traps"), `layout/gen/check_v2.sh` |
| Extract with magic 8.3.642: 8.3.684 drops substrate C (already in the skill for sky130; true for GF180 too). | `CLAUDE.md`, `docs/gf_silicon_factor.md` (Fig. 4) |
| The GF180 ngspice models give **one mismatch draw per instance, ignoring `m`**: split devices into unit instances for Monte Carlo. | `CLAUDE.md` ("Tool traps") |
| **No MIM caps on TT GF** (no Metal5 for projects; GF180's MIM needs it): large caps are MOS gate caps, about 4 fF/µm² for the 3.3 V oxide. | `docs/platform.md` ("Process and tile") |
| **Hi-res poly is 1 kΩ/sq** (`ppolyf_u_1k`); the 2k / 3k models in the ngspice library are other process options, not available. | `docs/platform.md` |
| TT GF tiles: 1x2 = 346.64 × 325.36 µm, 2x2 = 711.20 × 325.36 µm; the analog pins are Metal4 pads on the bottom edge, the digital pins on the top; power is vertical Metal4 stripes (VDPWR / VGND, plus VAPWR with the `_pgvaa` template). | `docs/platform.md`, `docs/top_layout.md` |
| VAPWR and VIO are independent of VDPWR (3.3–5 V each, VAPWR ≤ VIO); signals crossing between VAPWR and VDPWR need level shifters unless both are 3.3 V. | `docs/platform.md` ("Supplies and pins") |
| The TT power switch on VDPWR is about 1.3 Ω, common to the whole tile: large switching loads move everything else on VDPWR. | `docs/platform.md`, `docs/tx_fine_tune.md` |
| The GF analog pin: tnt's switch is 11–37 Ω (tt), plus 15–60 Ω of routing and about 7.7 pF with the pin open; at 434 MHz into 50 Ω it loses 0.5–0.9 dB against DC. | `docs/platform.md`, `docs/pad_model.md` |
| **GF silicon / extracted-tt factor ≈ 1.0** (ttgf0p2 ring #614: 0.993–1.001; worst 0.935), against sky130's 0.866. | `docs/gf_silicon_factor.md` |
| GF pins toggle cleanly to about 50 MHz (measured on ttgf0p2), not 100 MHz+. | `docs/platform.md` |
| `tools/osic-mac` (the IIC-OSIC-TOOLS Docker wrapper) doesn't pass env vars into the container: use `tools/osic-mac env K=V cmd`. | `CLAUDE.md` ("Tool traps") |

## Not in scope
- Rewriting the skill or its scripts beyond adding these lessons.
- Anything in this project's design.
