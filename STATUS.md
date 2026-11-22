# Where we are (2026-11-22)

This is the "pick up from here" note: the current state, what is running, the open items and the decisions. The
detail and evidence for each result are in the docs it links; the history is in git and in those docs.
Repo: github.com/mattvenn/gf-433-fsk-radio (`main`; this work on branch `verify-gaps`). Flow and rules: the project
skill `.claude/skills/mixed-signal-asic/`. Front door and datasheet: `README.md`, `docs/info.md`.

## Goal
A **433 MHz FSK transceiver** (the title in `info.yaml`) on GF180MCU for Tiny Tapeout (TT) ttgf26c: a half-duplex
433.92 MHz 2-level frequency-shift keying (2-FSK) transceiver with no inductors. On chip: an SPI-tuned (Serial
Peripheral Interface) ring voltage-controlled oscillator (VCO), a dipole transmit (TX) driver and a zero
intermediate frequency (zero-IF) I/Q receiver (RX) with limiters. The RP2350 on the TT demo board does the digital
work: tuning, demodulation and framing. Room-temperature operation only.

## Current state
**The tile is laid out and verified:** a 2x2 analog tile (variant B floorplan) holding the VCO core with the level
shifter and ÷4 (lsdiv), the mirrored Q level shifter, the constant-gm reference, the 10-bit medium DAC (digital-to-
analogue converter) and digital macro `tx_fine`, the TX driver, the receiver cells and the debug mux on ua[0]
(`docs/tile_layout.md`, generator `layout/gen/tile.py`, checks `layout/gen/tile_driver.sh`). DRC 0 (magic and
KLayout), LVS match with every mutation caught, antenna 0; the TT precheck passes in CI. Tile simulations:
`sim/top/tile_results.md` (latest: "Update 2026-11-20"); power IR / EM: `sim/power/results.md`; every test and
verdict: `docs/verification.md`. Bring-up and firmware rules: `docs/bringup.md`.

| | Result | Doc |
|---|---|---|
| Topology | Current-fed ring: five inverters between VDD and vg (3 pF PMOS decap to VDD), 5-bit binary coarse DAC plus fine leg, const-gm reference with 1 MΩ / 20 pF filter | `docs/cfed_results.md`, `docs/schematics.md` |
| GF silicon factor | about 1.0 at typical (ttgf0p2 inv_2 taps 0.993-1.001; inv_1 ring 0.935, re-measure) | `docs/gf_silicon_factor.md` |
| Tuning, extracted tile | 209.1-753.8 MHz at tt, about 19 MHz per code near 433.92 MHz, reached from code 10 (tt); tile about 3.6 % below the block-level map | `docs/bringup.md` (T2), `sim/top/tile_results.md` |
| Fine tuning / FSK | 10-bit medium DAC, LSB 27.4 / 31.1 / 35.6 kHz (ss / tt / ff), sigma-delta spurs -58 dBc, FSK ±3 LSB settles in 0.26 µs | `docs/tx_fine_tune.md` |
| 25 MHz supply spur | -84 dBc (extracted), after moving the vg decap to VDD | `docs/tx_fine_tune.md` |
| DAC mismatch (MC, N = 900) | 0 % non-monotonic, worst DNL ±0.13 | `docs/cfed_v3_check.md` |
| rms FM, 1-10 kHz | 7.3-8.3 kHz over PVT (limit 15) | `docs/cfed_sizing_results.md` |
| Start-up | 36 / 36 schematic runs reach the fundamental, worst 138 µs to 1 % | `docs/cfed_startup_results.md` |
| TX, tile | +6.28 dBm at code 9 (+5.99 dBm code 13), off -90 dBm; H3 below -55 dBc with the board low-pass filter | `sim/top/tile_results.md`, `docs/tx_harmonics.md` |
| RX, tile | settled -95 dBm pass; I/Q LO phase 72.9 / 74.1 / 72.8° (tt / ss / ff); model -110.4 dBm at BER 1e-3, 10 kbit/s | `sim/top/tile_results.md`, `docs/rx_design.md` |
| Supplies, tile | VAPWR ripple 1.0 mV p-p with TX on, VDPWR 13.7 mV; f +0.32 / -0.30 % at VDD ±4.5 % | `sim/top/tile_results.md` §6 |
| Pins | TT analog switch 11-37 Ω plus 15-60 Ω routing, about 7.7 pF per pin; checked over n_off 0-3 | `docs/pad_model.md`, `docs/platform.md` |

## In progress
**Full verification run** on branch `verify-gaps` (`docs/handoff_full_verification.md`, plan
`docs/plan_verify_gaps.md`), on this machine (the sim server). Started 2026-11-21 09:41; 973 jobs; 535 OK and none
failed as of 2026-11-22 21:30. Expected finish about Wednesday 2026-11-25 evening. The driver pushes a
`Running: step N/M` commit at each change; don't touch `build/`, `sim/` or the run while it goes.

## Open items / next steps
1. **Submit to `TinyTapeout/tinytapeout-gf-26c` before 2026-12-07** (the project is not in it yet).
2. After the full run:
   - write it up in `docs/verification.md`;
   - fix the scheduler starvation in `sim/sched.py`;
   - add a no-push option to the driver;
   - fix the stale "about 21 MHz per code" in `docs/tuning.md` and the tuning row in `docs/verification.md` (now about
     19 MHz per code, `docs/bringup.md`);
   - merge `verify-gaps` to `main`.
3. Ask tnt about VDPWR before the power switch (bond wires, chip grid) and the ground path (R, L); ground ripple is
   not modelled.
4. lsdiv block power is about 1.7× the schematic (0.63 mW at tt, routing C on the TSPC nodes;
   `docs/lsdiv_layout.md`). Don't clock the ÷4 below about 150 MHz.
5. Optional: re-tune the tempco. f(T) is a parabola peaking near 35 °C (+100...+140 ppm/°C at 27 °C); moving the
   n-well length lnw would put the peak at 27 °C (`docs/ref_layout.md`, "Tempco").
6. Minor, unexplained: the common baseband start-up offset is about -1.1 V on both arms against -0.83 V at fca76de
   (`sim/top/tile_results.md`, "Update 2026-11-20").
7. Bench: re-measure the ttgf0p2 inv_1 ring (`bench/lab_todo.md`); check `uio[1]` toggles first (it read held low on
   the ttgf0p2 carrier).
8. Later, not crucial: extra debug options (`docs/bringup.md` section 6): a divided Q LO on `uo[6]`, debug switches on
   `oi_n` / `oq_n`, the macro keeping only the lowest DBG_SEL bit.
9. Dummy fill: TT adds it later (Matt 2026-11-22: leave as is).
10. Sign-off: full PVT (5 corners × 0 / 27 / 70 °C × VDD ±4.5 %) plus Monte Carlo on the extracted tile; the full
    run covers this.

## Decisions (Matt), newest first
- **2026-11-22:** a PLL is out of scope here, a separate project. Decap closed - about 8.6 pF placed, supplies checked
  (VAPWR 1.0 mV ripple, VDPWR 13.7 mV), and there's no room for more without going to a 3x2 tile
  (`docs/tile_layout.md`'s closing list still says 7.4 pF). Dummy fill left as is: TT adds it later.
- **2026-11-20/21 (full run):** firmware rule 2 is a **2 ms wait** after rx_en, after TX and after a strong signal
  (the extracted design needs 1.47 ms after rx_en, 1.90 ms after an in-band burst); no trims; the 16-bit packet is
  kept whole; chatter limit at most 1 glitch per 4 bits. The full run goes on the sim server.
- **2026-11-20:** the unsettled 14 µs RX runs (`rxh_*`) check phase and sign only; frequency is checked on the
  settled runs (`rxs_*`). The ss I/Q LO phase of 76.1° was accepted (quadrature decoding works at 50-110°); after
  the nb fix it is 74.1° and passes anyway. nb is routed away from the LO wires (`tile_nets.KEEP_AWAY`).
- **2026-11-19:** the I and Q LO taps must match: the Q level shifter is mirrored under lsdiv (merged a899165). This
  fixed the a2 load (VCO shift -12.5 % -> -3.6...-3.9 %, `sim/top/a2_load/results.md`) and the I/Q skew; the tile
  gets a 72 ± 3° I/Q LO check. The TX final-stage shrink to 20-22 µm is dropped: the 40 µm stage stays.
- **2026-11-17:** floorplan variant B. No TX/RX hardware interlock: firmware keeps RX_EN off while transmitting and
  waits before trusting `q_i` / `q_q` (the "about 1 ms" wait is superseded by 2 ms, above). The SPI stays on
  `uio[0..3]` = SCLK, MOSI, CS_n, MISO via PIO or SoftSPI (`docs/bringup.md`). Extra debug options deferred.
- **2026-11-13:** VAPWR and VDPWR are separate supplies, both 3.3 V by default on the demo board (`docs/platform.md`).
- **2026-11-12:** receiver option B: zero IF, I/Q mixers on two ring taps 72° apart, a limiter per arm, two bits to
  uo[4] / uo[5], decoded by the RP2350 PIO (`docs/rx_design.md`). TX harmonics fixed by a board 5th-order pi
  low-pass filter (the one board exception), after on-chip slew control failed (`docs/tx_harmonics.md`). The ua pin
  current at ff / 15 Ω (10.8-11.1 mA rms against 10 mA) is acceptable. Kept as is: the sigma-delta charge injection
  (+0.4 LSB) and the FSK overshoot at a major carry (firmware keeps the FSK pair inside one block of 32). Not
  pursued: the 0.10 % low shift after the decap redraw (the RP2350 servo tunes absolute f).
- **2026-11-11:** the ttgf26c pin plan isn't known until tapeout, so designs are checked over n_off 0-3.
- **2026-11-10:** no board components except the dipoles (and later the TX filter), so all fine tuning is on chip:
  option C, a 10-bit medium current DAC with sigma-delta dither, an SPI register from the RP2350, FSK as a digital
  offset, a ÷16 / ÷64 / ÷1024 divider to `uo_out`; vctrl tied inside the chip, ua[0] kept for debug; the RP2350
  counts and servos (frozen during packets); the RX gets its own dipole.

## How we got here
Starved-ring study (`docs/vco_study.md`), then the layout showed about 10 fF per ring node and charge sharing broke
the starved stage, so the current-fed ring won the topology comparison (`docs/cfed_results.md`). Then sizing and PVT
(`docs/cfed_sizing_results.md`), the v3 core layout (`docs/ring_layout_v3.md`), lsdiv (`docs/lsdiv_design.md`), the
reference (`docs/ref_layout.md`), `vco_top` (`docs/top_layout.md`), fine tuning (`docs/tx_fine_tune.md`), the TX
driver (`docs/tx_driver.md`), the receiver (`docs/rx_design.md`) and the tile. Detail: those docs and `git log`.

## How things run
- **This machine is the sim server.** Long runs (over about 5 minutes) go through a `docs/handoff_<topic>.md` under
  the rules in `docs/handoff_autonomy.md` (including "Corner policy": iterate at 27 °C, 3.3 V on the bounding
  process corners; 0 / 70 °C and VDD ±4.5 % for robustness and sign-off).
- **Tools:** `tools/osic-mac <cmd>` runs IIC-OSIC-TOOLS. It doesn't pass env vars into Docker: use
  `tools/osic-mac env K=V cmd`.
- **Chosen design settings:** `sim/results/2026-11-08/winner_sets.txt`, plus `lnw=5.023 topo=cfed kc=0.75 k=6
  cvg=3e-12 ka=16 wfu=0.30 wff=0.30 rf=1e6 cf=20e-12` (circuit in `sim/vco/vco_bias.py`).
- **Viewers:** GDS `https://gds-viewer.tinytapeout.com/?url=<raw github URL>&pdk=gf180mcuD`; schematics via the
  xschem-viewer links in `docs/schematics.md`.

## Known issues and traps
- **magic RC extraction double-counts coupling C** on ports and split nets: simulate the `_rcx.spice` files
  (`layout/gen/rcfix.py`, `docs/rc_extraction_fix.md`).
- **`map.csv` reads about 1.3 % high** (before vg settles); the extracted layout runs at about 0.98× the schematic.
- **Kvco is not linear:** the fine leg is flat below about 1 V, square-law above; measure Kvco at the operating point.
- **xschem-viewer has no GF180 library:** the symbols are copied into `xschem/symbols/`.
- **Leftover Docker containers** from killed runs: check with `docker ps`.
- **Never commit `sim.yaml`:** it holds the VNC password.
