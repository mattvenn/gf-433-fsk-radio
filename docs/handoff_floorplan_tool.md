> Done (2026-11-16): page https://claude.ai/artifact/942zW17HYnwDF8qCuYhQk3, see docs/floorplan_spec.md

# Handoff: port the OOK radio's interactive floorplan page to this project (cloud session)

**Goal: an interactive floorplan page for this project's 2x2 GF180 tile, ported from the OOK radio's tool, with this
project's blocks, pins, nets, supply domains and rules, so that Matt and Claude can agree the tile floorplan with the
receiver in it.** Matt drags blocks; Claude proposes named variants; the chosen one is exported to
`layout/floorplan/floorplan.json` for the tile generator to read later.

**This needs a Claude Code session with the Artifact tool** (a claude.ai cloud session, as the OOK page was built), not
the sim server: the page is a claude.ai artifact with a shared database. It runs no simulations.

## Where things are
- **Branch: `floorplan`** (made from `rx-option-b` on 2026-11-16). Work and push only there. Two server agents are
  pushing to `rx-option-b` meanwhile (`docs/handoff_rx_chain2.md`, `docs/handoff_rx_integration_prep.md`); when the
  integration prep reports Done, merge `rx-option-b` into `floorplan` and regenerate `blocks.json` (the macro's size
  and `rx_en` pin, `vco_top`'s new a2 pin and the VAPWR stripes change). Never push to `rx-option-b` or `main`.
- **The tool to port** is in `github.com/mattvenn/ook-asic-radio` (public; clone it read-only):
  - `docs/floorplan_spec.md`: the spec, the page as built, and how the chosen floorplan was reached. **Read it all.**
  - `layout/floorplan/page/`: `page.html` (UI), `engine.js` (orientations, pins, nets, rule checks, export / import),
    `place.js` (annealing placer and decap fill), `refine.js`, `pinfit.js`, `pinreport.js` (`floorplan.json` and
    `pins.md`), `check.js` (prints the checklist from the command line).
  - `tools/floorplan_blocks.py` (block outlines and pins from the GDS; needs `pip install klayout`),
    `tools/floorplan_page.py` (inlines everything into one artifact page; `--dev` for a local preview),
    `tools/floorplan_draw.py`, `tools/floorplan_dump.js`.
  - `layout/floorplan/{tile,blocks,variants,floorplan}.json`, `pins.md`: the data formats.
- **This project:**
  - `docs/top_layout.md` (the tile facts: 2x2 = 711.20 × 325.36 µm, the ua pads on the bottom edge, the digital pins on
    the top edge, Metal4 stripes; and where every block sits now);
  - `layout/gen/tt_wrapper.py` (the current tile: placements, orientations, stripes) and `lvs/make_source.py`;
  - `docs/rx_layout.md` (the receiver cells and `rx_top`, Table S1), `docs/rx_design.md` (the receiver),
    `docs/tx_fine_tune.md` (the macro), `docs/tx_driver.md`, `docs/platform.md` ("Supplies and pins");
  - the top-level block diagram in `docs/learning.md`'s figures and the receiver chain description.
- **Ownership:** you own `layout/floorplan/`, the ported `tools/floorplan_*`, `docs/floorplan_spec.md` (this project's
  version) and this handoff. Don't change any block's layout, schematic, or the tile generator.

## Decisions already made (Matt, 2026-11-16)
- **Supplies:** the quiet analog (`vco_top`: ring, `cgm_ref`, coarse DAC, `lsdiv`; `mdac`; `vctrl_pd`) and the receiver
  on **VAPWR**; the TX driver `tx_drv` and the digital macro `tx_fine` on **VDPWR**; VGND shared. VAPWR is set to
  3.3 V. The tile uses the `_pgvaa` template (VAPWR stripes).
- **rx_en** is CTRL[4] of `tx_fine` (a new macro pin, coming from the integration prep).
- **Pins:** ua[0] vctrl (bench override), ua[1] vbn (monitor), ua[2] / ua[3] TX out_n / out_p, **ua[4] / ua[5] RX
  in_p / in_n**; uo[0:3] ck and the dividers, **uo[4] / uo[5] RX q_i / q_q**; ui[0:4] coarse code, ui[5:6] TX enables,
  ui[7] FSK; uio[0:3] SPI; clk, rst_n to the macro.

## What goes in the tile

| Instance | Cell (GDS) | Size | Supply | Notes |
|---|---|---|---|---|
| vco_top | `layout/vco_top.gds` | 386.6 × 70.8 µm | VAPWR (VDD and VDD_LS) | ring core, `cgm_ref`, `lsdiv` and its decap; a2 pin coming (integration prep) |
| mdac | `layout/mdac.gds` | from the GDS | VAPWR | fine-tune DAC: current into `vg`, `vbnf` from vco_top, 37 control lines from the macro |
| vctrl_pd | `layout/vctrl_pd.gds` | from the GDS | VAPWR | 200 kΩ pull-down on vctrl (ua[0]) |
| tx_drv | `layout/tx_drv.gds` | from the GDS | VDPWR | 12.6 mA of 434 MHz edges into ua[2] / ua[3] |
| tx_fine | `macro/tx_fine/gds/tx_fine.gds` | from the GDS | VDPWR | the digital macro (25 MHz clock, and the ck domain at f / 4 ≈ 108 MHz); its pins face the TT digital pins and the analog |
| rx_top | `layout/rx_top.gds` | 299.4 × 376.0 µm | VAPWR | **taller than the tile**: see below |
| decaps | estimates | editable | VAPWR / VDPWR | fill |

**rx_top doesn't fit as drawn** (376 µm against 325.36 µm). Offer it on the page **both** as one block and as its
cells (`rx_lna`, `rx_bias`, `rx_lsq`, `rx_lobuf` × 2, `rx_mix` × 2, `rx_bb` × 2, `rx_lim` × 2, `rx_decap`; sizes in
`docs/rx_layout.md` Table S1), with the nets between them, so that Matt can explore a flatter shape. A variant that
places the cells individually becomes the brief for an `rx_top` re-layout.

Add a variant **"current"** that reproduces today's tile from `tt_wrapper.py` (with an empty reserved receiver area), so
everything else is compared against it.

## Nets (for flylines and wire-length checks)
- **Pads:** ua[4] / ua[5] → rx `inp` / `inn`; tx_drv `out_n` / `out_p` → ua[2] / ua[3]; ua[0] → vco_top `vctrl` and
  vctrl_pd; ua[1] → vco_top `vbn`.
- **LO:** vco_top `ls` → rx `ls` (I) and → tx_drv `ls`; vco_top `a2` → rx `aq` (Q).
- **Fine tuning:** tx_fine's 37 DAC lines → mdac; mdac → vco_top `vg`; vco_top `vbnf` → mdac.
- **Clocks and control:** vco_top `ck` → tx_fine `ck`; tx_fine `rx_en` → rx `en`; the TT digital pins (top edge) →
  tx_fine and → vco_top's coarse-code bits; ui[5:6] → tx_drv enables.
- **RX outputs:** rx `q_i` / `q_q` → uo[4] / uo[5].
- Check the exact names against the GDS labels, `lvs/make_source.py` and the xschem symbols.

## Rules, ranked (this project's; refine them with Matt on the page)
The radio is half-duplex: while receiving, the TX driver's arms are off. But **the ring, lsdiv and its ck run all the
time**, and so does the macro's 25 MHz clock.
1. **RX input far from the digital macro and from everything the ring clocks.** Three different mechanisms:
   - **Ring-derived signals** (ck = f / 4, the ÷16 / ÷64 / ÷1024 outputs on uo[0:3], the macro's ck domain) are
     phase-locked to the LO, so their harmonic at 433.92 MHz lands **exactly at 0 Hz** after the mixer: a DC offset,
     which the AC couplings remove while it is steady (the ÷1024's neighbours at ±424 kHz fall outside the
     8.5–143 kHz pass band). The hazard is a **step**: switching CK_EN or the divider outputs on or off, or a big
     change in their load, during RX gives an offset step that blanks the receiver for about 1 ms
     (`docs/rx_design.md`, "Offsets"). Firmware should set them before `rx_en`'s settling window, not during a packet.
   - **The 25 MHz clock** (from the RP2350) is not locked to the LO: its harmonics at 425 and 450 MHz land 8.9 and
     16 MHz away after mixing, outside the pass band, but they pass the LNA (−3 dB at about 200 MHz either side) and
     add to its load. Crossings between the 25 MHz and the ck domains in the macro make beat products at frequencies
     that are not locked to the LO; one that lands within ±143 kHz of it is in band. This is the one that can't be
     filtered.
   - **Supply and substrate coupling into the ring itself** (the LO) puts spurs on the LO, and a strong interferer
     mixed by an LO spur lands in band (reciprocal mixing). The VAPWR split is the main defence.
   So: maximise the distance from the macro and from the ring-derived digital wires to ua[4] / ua[5] and the LNA
   input, and list "gate ck and the dividers during RX (and when)" as an open question.
2. **The LO wires.** `a2` → rx `aq` as short as possible: every fF on a2 slows the ring and shifts the I/Q phase.
   `ls` → rx `ls` short, and the two LO wires' loads matched (`docs/rx_layout.md`: matching them should bring the
   extracted I/Q phase from 77° back towards 72°). So the receiver's LO end sits next to lsdiv and the ring's a2 pin.
3. **LNA at ua[4] / ua[5]**, with short, symmetric input wires.
4. **TX driver at ua[2] / ua[3]**, with short, wide output wires (12.6 mA). It is off during RX, so its distance from the
   RX is a soft preference, except that ua[3] is the pad next to ua[4].
5. **Supply domains:** the VAPWR blocks together with their own stripes and decap, the VDPWR blocks together with
   theirs. List every signal that crosses between them (all 3.3 V to 3.3 V, no level shifters), and flag any VAPWR
   block whose nearest stripe is a VDPWR one.
6. **No digital or LO wire over the receiver.** The baseband and limiter AC-coupling nodes are about 60 MΩ
   (`docs/rx_layout.md`); keep the macro's wires, ck and the dividers off `rx_top`.
7. **Short fine-tune bus:** the 37 lines from tx_fine to mdac, and mdac next to vco_top's `vg`.
8. **The macro near the top edge** (the TT digital pins), with a routing channel for them.
9. **Fit and spacing:** everything inside 711.20 × 325.36 µm, ≥ 2–3 µm between blocks for guard rings, decap as fill.
10. **Power stripes:** vertical Metal4 VDPWR / VAPWR / VGND stripes need clear lanes; no Metal5. Flag a stripe that
    crosses a block using Metal4.

## What to change in the tool
- `tile.json` from the 2x2 analog DEF with the VAPWR template (tt-support-tools, `tech/gf180mcuD/def/analog/`; find the
  `_pgvaa` variant and say which file you used).
- `blocks.json` from this project's GDS with the ported `tools/floorplan_blocks.py` (including `rx_top` and its cells,
  and per cell the Metal4 boxes for the stripe-lane check).
- `engine.js`: replace the OOK nets, zones (the LNA chain's zones) and rules with the ones above. Put the rule
  thresholds in the page's settings, as before. Add the supply-domain colouring and the crossing list.
- `place.js`: anneal around fixed anchors (the pads, the TT digital pins, the macro's top-edge pin channel).
- Keep the variant store, export / import, `pins.md` and `check.js`.

## Checks
- `node layout/floorplan/page/check.js layout/floorplan/variants.json` prints the same checklist as the page.
- **Mutation-test the rules:** move the LNA away from ua[4] / ua[5], or route a2 the long way, in a copy of a variant;
  the matching rule must fail. Overlap two blocks; the overlap check must fail.
- The "current" variant's block positions match `tt_wrapper.py` to within 0.01 µm.

## Deliverables
- The page published as a **private claude.ai artifact** with its database (variants, settings), and the link given to
  Matt. Seed it with "current" and two or three proposals, each with a short note on its trade-offs (for example:
  receiver on the right under the macro's far end; receiver in the middle beside lsdiv; the receiver flattened into
  two rows).
- `docs/floorplan_spec.md` for this project (the OOK one adapted: data, rules, the page as built, open questions).
- Everything committed and pushed to `floorplan`.

## Not in scope
- Changing any block, the tile generator (`tt_wrapper.py`), or the macro. Reading `floorplan.json` into the tile
  generator is the next step, after Matt picks a variant.
- Re-laying out `rx_top` (the chosen variant becomes its brief).

## Done
When pushed and the link is with Matt, replace the first line with `> Done (date): page <artifact link>, see
docs/floorplan_spec.md`.
