# Floorplan, top-level routing, power delivery

## Floorplan
- Top-down first: each block gets a target outline, pin sides and rail heights before it is drawn.
  The classic mistake is lots of cells and then a mess at assembly. But use **real block sizes**:
  estimates would have misled us.
- An interactive floorplan page (a claude.ai artifact) worked very well. It loaded real block bboxes and
  pins from the GDS (`blocks.json`) and tile pins from the DEF (`tile.json`). Blocks could be
  dragged and rotated using GDS orientation names (R0…MYR90 map straight onto a KLayout DCplxTrans).
  It drew flylines coloured by net class, a live ranked-rule checklist with numbers and a hover
  reason, an area panel, and named variants in shared state, and it exported `floorplan.json`, which
  the tile generator reads.
- **Pins stay free during floorplanning**: edge + order, fitted to the edge facing the connection. Most
  rule failures were fixed by pin moves alone. Pin specs go in each block's own frame (±a few µm).
- Never hand-edit generated floorplan files. Write each variant as a script and regenerate.
- Check the floorplan's net list against the schematic, which is the source of truth. It had a
  differential pair swapped and a shunt cap in series.
- Rules with numbers: aggressor ↔ sensitive distance, a coupling budget, clock edges kept off sensitive
  nets, short sensitive input paths, wide high-current lines, bias kept near its loads, decap as fill,
  block spacing ≥ 2–3 µm. **Rules need operating modes** (two blocks never active together don't
  interfere), and warnings need an "accepted, because …" record so the list shows only open problems.
- Show strap lanes on the page and flag blocks with met4/MIM obstructions, since full-height met4
  straps can't cross MIM top plates.
- Keep an area budget from day one. At 92 % use, decap was the only lever left.
- **Plan decap as part of the floorplan, not as leftover space.** Give each supply a decap budget in pF at its
  loads, and draw decap areas that can really be filled: each one crossed by a stripe pair of its supply (or with
  a planned feed), wider than the decap unit, and kept clear of routing channels. Size the decap unit to those
  areas. After placement, compare placed against planned per supply. gf-433-oscillator planned about 60 pF of
  tile decap and placed 8.6 pF: the 12 × 15.7 µm unit only went where a stripe pair crossed, so 6 of 11 areas got
  none, 3 more lost to routes or narrow width, and about 44,000 µm² (20 % of the tile) ended up as dummy fill.
  It was fine only because the blocks carried their own decap (VAPWR about 86 pF effective, 1 mV ripple). Adding
  decap after extraction means re-extracting and re-verifying, so decide it before the long runs.
- **Match the pitch of blocks that tap each other.** A detector at a 20.8 µm cell pitch fed from a chain
  whose taps sit at 11.7 µm needed tap runs up to ~60 µm: 14–32 fF to ground per tap, ~0.035 dB per fF per
  stage, 4.2 dB in all on the block (~1.1 dB on the tile). Turn or re-pin the receiving cells so their
  inputs line up with the taps before routing, and price every RF tap's C at floorplan time.
- A macro's pin edge needs a routing channel (~12 µm for 42 tracks).
- Clock harmonics land wherever they land: check them against every sensitive band. Keep sensitive
  inputs far from the digital macro, and rank aggressors by what actually switches in each mode.

## Constraints file (write it at schematic time; the floorplan and router read it)
```yaml
modes: {measure: [amp, bias, comp, dac, macro], drive: [driver, macro]}   # blocks active together
net_classes:
  sens_input: {sensitive: high, max_len: 50, pair: true}
  slow_node:  {sensitive: med, shield: VSS}                  # high-Z: coupling matters, length doesn't
  clock:      {aggressor: high, keep_from: [sens_input, analog_signal], min_gap: 20}
  power_out:  {aggressor: high, current_mA: 10, width_um: 5, pair: true, active_in: [drive]}
  trim:       {aggressor: low, static_in: [measure]}
nets:   {in_p/in_n: {class: sens_input, from: pad:ua[0]/ua[1], to: amp.inp/inn}}
blocks: {amp: {avoid_zone: {zones: [input, stage1], from: [clock, power_out, macro], min_gap: 100}}}
power:  {VAPWR: {decap_pF: 50}, VDPWR: {decap_pF: 30}}
accepted: [{rule: power_out.max_len, reason: "driver off while measuring; route ≥ 5 µm wide instead"}]
```

## Top-level router (custom A*, ~35 s for ~90 nets)
- A 0.2 µm grid over met1–met4. Obstacles are the real geometry bloated by half the net's width plus
  spacing, so routes come out DRC-clean by construction.
- Tag every shape (inst.pin, NET@strap, route net), and let a net touch only its own tags. Beware:
  tagging every polygon touching a pin as that pin once produced a 22 µm dead-end stub.
- Per-net constraints: width, layers, preferred direction, keep-outs, an `avoid` cost near other nets,
  `follow` for pairs, waypoints, and strap anchors for power trees (a power tree that starts at its own
  terminals makes zero-length routes).
- Keep-outs aren't metal, so a route can end on a halo and leave an open. Terminals come only from real
  pin shapes.
- Place fixed geometry (the TT bus) first and check it against foreign metal: it once shorted a uio
  wire to a ground strap.
- Over MIM decaps only met2 is free. Put the decap via stacks in edge bands only.
- Run a metal-connectivity trace of the placed tile. A met4 decap bus crossing a strap shorted all three
  supplies.
- No open-source router does analog-aware routing (shielding, pairs, EM widths), but the net count is
  small enough that a scripted router is realistic.

## Power delivery (Tiny Tapeout)
- The TT PDN is horizontal met5 stripes at a 57.12 µm pitch. Any same-net met4 power shape crossing a
  stripe gets via4s automatically. VDPWR/VAPWR come through power gates on the tile's **west** side
  (3v3 ~2 Ω, 1v8 ~0.8 Ω) and only two met5 stripes each, so east-side loads see ~500 µm of met5.
  VGND comes from the global grid. The stripe order and orientation are unknown, so model both and
  design for the worse.
- Block convention: full-width horizontal rails, VDD top and VSS bottom, met1+2+3 stacked. Full-height
  met4 straps at the top level land on them through via3. Document any block that breaks this.
- **A rotated block's rails are vertical: the straps must sit right over them.** A 90°-turned TX driver kept a
  strap placed for its old orientation, its VSS ended up wired by the signal router (17.6 Ω, 259 mV, a via at 80×
  EM), and LVS / DRC / precheck all passed. Gate the build on a supply-landing check (every block supply on a
  strap, Via3 cuts sized for its current, router-wired supplies only for an allow-list of tiny blocks).
- Straps on both sides plus a middle set, run as VDD/VSS pairs. Keep the noisy and quiet grounds
  separate, joined only at the straps, with the sensitive blocks' guard rings on the quiet ground.
- **Biggest finding:** sensitive blocks sat 27–67 Ω from their supply because current wound through
  other blocks' rails in series. Ideal straps and 3× routes barely helped. A **dedicated trunk per
  sensitive block** (3–4 µm, treating other blocks' rails as foreign metal) took 67 → 14 Ω and
  57 → 8 Ω, cut |Z| 2–3×, and cut the coupling from the switching driver 8.5×. Removing a parallel path
  can raise another block's R, so re-measure every block after any change.
- EM: one 1.2 µm strap with one via4 column was at 2× the limit for a ~10 mA driver. 5 µm straps with
  three via4 columns per met5 landing fixed it, together with feeding the driver's rail at several
  points (a single-point feed made a 275 % hotspot that wider routes couldn't fix).
- **Size each strap from the current it alone carries**, not a default width. In gf-433-oscillator one Metal4 strap
  fed the whole TX driver: 6 µm was 2.4 mA/µm, over the 85 °C limit; 8.5 µm gave 1.8 mA/µm. Do the arithmetic
  (I / w against the 85 °C limit) for every strap that feeds one big load, and use the LEF figure as a flag.
- **Moving straps can retune an oscillator.** New straps placed near a ring's long internal wire added 0.9 fF of
  coupling to it (ring 0.7 % slower, and the TX enables now kick that node). After any power-grid change,
  re-extract and recheck the total C on sensitive nets; keep straps off them or shield them.
- Decap behind 10–20 Ω of mesh does nothing (|Z| ≈ R_VDD + R_VSS, flat to hundreds of MHz). Put it at
  the load. Characterise decaps with an AC bench: C = Im(I)/ωV, ESR = Re(1/Y).
- Move aggressive loads onto their own supply (moving a driver to 3.3 V took a ~10 mA step off
  VDPWR). Still give VAPWR decap for the sake of the other projects sharing it (~1 V p-p of switching
  noise rode on it otherwise).
- Check the bond-wire L × on-chip C resonance. The whole chip rang ~355 mV p-p common mode for an
  assumed 2 nH / 1 nF.
- The TT figure is ~0.1 V drop at 20 mA through the PDN. Bursty loads of ~10 mA need strap width and
  count.

## Power analysis method
- **magic `extresist` is unusable for supply nets.** It lumps much of the net into the port, the
  FastHenry export is the same network, and FastHenry itself didn't work. Other magic traps: several
  port names on one net write it once per port, same-name labels short strap ends together, std-cell
  substrate labels merge VGND with an ideal substrate, and a KLayout-flattened GDS crashed ext2spice.
- What worked:
  1. Make an extraction copy: the tile minus the macro, plus the power-gate columns, met5 stripes and
     via4, with one port per supply.
  2. magic rc for the devices and C.
  3. A KLayout trace of each supply rasterised at **0.5 µm** into a conductance mesh (sheet R, R per
     cut × cuts). 1 µm read thin routes ~30 % low.
  4. ngspice solves DC R, IR, AC |Z|, EM per layer and via, and the aggressor's switching transient
     seen at the sensitive blocks' supplies.
- Probe a block's local supply at its devices' current-carrying terminals (S/D, R/C ends), not bulk.
- **Don't spread a block's DC current by contact area.** That puts DC into decap, which draws none. A thin decap
  feed then shows up as an EM hotspot: gf-433-oscillator had a 0.6 µm decap VDD line with one via reported at 27×
  the limit. Weight the current onto the devices that carry it (the output stage's sources), and treat a decap
  feed as an AC / ESR question, not an EM one. A single via in a decap feed is series resistance that halves
  the decap's use.
- Point injection over-reads EM at mcon/via1 (a 71 % reading was really ~9 %). Sanity-check hot spots.
- Make what-ifs cheap (a strap-width json, `IDEAL=1`, trunk multipliers), and **check the copy for
  shorts before simulating**.
- Runtime: ~45–50 min per variant (DC R ~25, IR ~15, EM ~10 min). A scipy mesh solve
  (`power_r.py`) is a quick cross-check only.
