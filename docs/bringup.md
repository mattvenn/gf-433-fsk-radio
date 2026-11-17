# Bring-up plan

[![Made with Claude](https://img.shields.io/badge/Made%20with-Claude-D97757?logo=anthropic&logoColor=white)](https://claude.com/claude-code)

**Draft, written before silicon** (2026-11-17, branch `floorplan`). Drafted by Claude (the AI) from the design docs;
every expected value is a simulation result, with the doc it comes from. "TBD" means no simulated number exists yet.

How to test the tile: the digital first, then the voltage-controlled oscillator (VCO) and transmitter (TX), then the
receiver (RX) on one board, then two boards talking. Each stage uses only parts the earlier stages have checked, so if
a stage fails, stop and debug it before moving on. Keep raw captures in `bench/data/<date>/` and fill in the Result
columns.

## 1. Before power

**Equipment**
- 2 × Tiny Tapeout (TT) GF180 demo boards with the RP2350, running a firmware that selects
  `tt_um_mattvenn_gf433_vco`, gives a 25 MHz project clock (10-50 MHz works, `info.yaml`), drives `ui_in` and talks
  Serial Peripheral Interface (SPI) on `uio[3:0]`.
- 433 MHz antennas: a two-wire dipole (2 × 16.5 cm) or an SMA on the TX pair `ua[2]` / `ua[3]` and the RX pair
  `ua[4]` / `ua[5]`, per board.
- A scope with 1 MΩ and, if possible, a high-impedance (≥ 10 MΩ) or active probe for `ua[0]`.
- A frequency counter, or the RP2350's programmable I/O (PIO) as a counter, plus a software-defined radio (SDR)
  covering 300-600 MHz, such as an RTL-SDR.
- A digital multimeter (DMM), SMA DC blocks, a step attenuator (≥ 100 dB in total) and SMA cables.
- For the RX tests: a 433 MHz signal generator, or an SDR that can transmit (an RTL-SDR can't; a HackRF or PlutoSDR
  can).

**Pin rules**
- `ua[1]` is tied to the on-chip ground (VGND). It is the reference for every reading on `ua[0]`. Never drive it.
- `ua[0]` is the debug bus (`DBG_SEL`). Drive it only with `DBG_SEL` = 8 (vctrl), and only between 0 and 3.3 V.
- The TX pins are 3.3 V push-pull. Never connect them straight to the RX pins or an SDR: use a DC block and ≥ 30 dB
  of attenuation (the RX input 1 dB compression point is about −23.5 dBm, `rx_design.md`).
- The RX inputs self-bias at about 1.37 V (`rx_design.md`, input option b). Feed them through a DC block.

**SPI** (`src/tx_fine.v`, `tx_fine_tune.md` Table VI): mode 0, MSB first, 16-bit frames, `[15]` 1 = read,
`[14:12]` address, `[11:0]` data. Read data comes back on MISO (`uio[3]`) in the same frame. Keep SCLK below
clk / 8 (3.1 MHz at a 25 MHz clock). **Raise CS_n after every 16-bit frame**: the bit counter wraps at 32, so a
longer frame writes again.

## 2. Power-up and digital

One board, no antennas.

| # | Test | Expected | Source | Result |
|---|---|---|---|---|
| D1 | Select the project, 25 MHz clock, reset | `uo[0]` (ck) low: gated off after reset | `tx_fine_tune.md` | |
| D2 | Read address 7 | ID = 0x433 | `src/tx_fine.v` | |
| D3 | Read every register after reset | MED_INT 512, MED_FRAC 0, FSK_DEV 0, CTRL 0, EFF_INT 512, DBG_SEL 0 | Table VI | |
| D4 | Write and read back each register: walking ones and 0 / all ones in the used bits | reads back the written bits; unused bits read 0 (`src/tx_fine.v` read mux); address 6 reads 0; one write doesn't disturb another register | `tile_layout.md` (cocotb) | |
| D5 | Write MED_INT = 600, read EFF_INT | 600 (no FSK) | Table VI | |
| D6 | Send a 32-bit frame (CS_n low throughout) | the second word is written again: a reminder to keep frames at 16 bits | Table VI | |
| D7 | Supply current: reset vs CTRL.RX_EN = 1 | about 7.0 mA more on VAPWR with the RX on | `rx_design.md` | |

**Pass:** D2 to D6 exact. If D2 fails, check the clock, the project select and the SCLK rate first.

## 3. VCO and TX

One board. Count `uo[3]` (f / 1024) with the RP2350 or a counter: f = 1024 × the count. At 433.92 MHz it is
423.75 kHz. `uo[1]` (f / 16, 27.1 MHz) gives the same with more resolution (`tuning.md`, "Counting").

| # | Test | How | Expected | Source | Result |
|---|---|---|---|---|---|
| T1 | Oscillates | Reset, code 9 on `ui[4:0]` | `uo[3]` toggles; about 420.5 MHz × (1 / 1024) = 410.7 kHz at tt, word 512 | `tx_fine_tune.md` Table VII and below it | |
| T2 | Coarse sweep | Codes 0-31, MED_INT 512, record f per code | monotonic, about 21 MHz per code; 433.92 MHz reached from code 9 (tt), 11 (ss), 7-8 (ff) | `tuning.md`, `STATUS.md` | |
| T3 | Dividers | Scope `uo[1]`, `uo[2]`, `uo[3]` | ratios 16 : 64 : 1024 exactly (f / 16 = 27.1 MHz, f / 64 = 6.78 MHz at 433.92) | `tx_fine_tune.md` | |
| T4 | MED_INT | Code fixed, words 0, 256, 512, 768, 1023, then 512 → 513 | LSB 31.1 kHz tt (27.4 ss … 35.6 ff); range 28.0-36.5 MHz, > 1.3 coarse steps | Table VII | |
| T5 | MED_FRAC | MED_FRAC = 0, 64, 128, 192 with CTRL.SD_EN = 1 | f steps of LSB / 256 (115-150 Hz); monotonic but bowed, up to +0.4 LSB at fraction ½ (ΣΔ cell charge injection) | `tx_fine_tune.md` | |
| T6 | CK_EN | CTRL.CK_EN = 1, scope `uo[0]` and watch the SDR | f / 4 (108 MHz) appears. The pads are clean only to about 50 MHz, so expect a poor waveform; an on-channel line may appear at 4 × ck | `platform.md`, `tx_fine_tune.md` | |
| T7 | Tune to 433.92 MHz | Run the procedure in `tuning.md` (coarse search, LSB, set, servo) | within 0.3-0.6 kHz of the target after two or three 10 ms steps, relative to the RP2350 crystal (±30 ppm, ±13 kHz) | `tuning.md` Fig. 2 | |
| T8 | TX on | `ui[5]` = `ui[6]` = 1, dipole on `ua[2]` / `ua[3]`, SDR nearby | a carrier at the counted f (to within the crystal errors) | `tx_driver.md` | |
| T9 | TX power | Cabled: each arm through a DC block and attenuator into the SDR or scope at 50 Ω | +6.26 dBm into the 73 Ω dipole (+3.7 … +9.3 over corners); single-ended into 50 Ω: TBD; 3rd harmonic −14.1 dBc (tt) | `tx_driver.md` | |
| T10 | Off is off | `ui[5]` = `ui[6]` = 0 | no carrier: −83 dBm into the dipole (extracted) | `tx_driver.md` | |
| T11 | One arm | `ui[5]` only, then `ui[6]` only | carrier from each arm alone, roughly equal; tells a dead arm from a dead splitter | `tx_driver.md` | |
| T12 | TX pulling | Count f with the TX off and on | TBD (no simulated number for the count shift) | | |
| T13 | FSK | MED_INT 512, FSK_DEV = 0x030 (3 LSB, 4.8 fixed point), CTRL.FSK_EN = 1; `ui[7]` = 0 then 1 | two counts 6 LSB apart: about 204 kHz (±100 kHz); FSK_INV swaps them | `tx_fine_tune.md` Fig. 3 | |
| T14 | FSK word | Read EFF_INT with `ui[7]` = 0 and 1 | 509 and 515; saturates at 0 and 1023 | Table VI | |
| T15 | FSK on air | Toggle `ui[7]` at 10-50 kbit/s, SDR waterfall | two tones 200 kHz apart. Keep both words inside one block of 32 (avoids the major-carry spike) | `tx_fine_tune.md` | |
| T16 | vctrl read | DBG_SEL = 8, high-impedance probe on `ua[0]` against `ua[1]` | about 0 V: vctrl is pulled down by 200 kΩ on chip | `tuning.md` | |
| T17 | vctrl override | DBG_SEL = 8, drive `ua[0]` through 1 kΩ at 0 … 3.3 V, count f | flat below about 1 V, then up to about 50 MHz/V; 1.65 V gave +20.7 MHz at tt (schematic ring) | `tuning.md` Fig. 1, `sim/mixed/results.md` | |

Notes:
- The silicon frequency should be close to simulation: the GF silicon / simulation factor measured on ttgf0p2 rings
  is about 1.0 at typical (`gf_silicon_factor.md`). The 433.92 MHz code may still differ by one.
- FSK_DEV is in DAC least significant bits (LSBs), 4.8 fixed point: FSK_DEV = 16 × (deviation / LSB). For 100 kHz
  at 31.1 kHz per LSB, 16 × 3.2 = 51 (0x033). The `tuning.md` procedure rescales it from the counts.
- Do T16 with only DBG_SEL bit 3 set. Drive `ua[0]` only after the readback shows DBG_SEL = 8.

## 4. RX on one board

One board, RX dipole or SMA on `ua[4]` / `ua[5]`, TX off. The RX is zero intermediate frequency (zero-IF): the local
oscillator (LO) is the ring itself, so the LO frequency is the counted f. A tone at f + Δ gives limiter outputs
`q_i` (`uo[4]`) and `q_q` (`uo[5]`) toggling at |Δ|, with the I/Q order set by the sign of Δ.

| # | Test | How | Expected | Source | Result |
|---|---|---|---|---|---|
| R1 | RX_EN | CTRL = 0x10. Count f before and after | RX current about 7.0 mA (VAPWR); ring moves ≤ 7 kHz (0.23 LSB), since the Q tap copy stays on | `rx_design.md` "rx_en" | |
| R2 | Bias | DBG_SEL = 4, high-impedance probe on `ua[0]` | nb about 0.98 V tt (0.84-0.85 ff); 0 V with RX_EN = 0 | `sim/mixed/results.md` | |
| R3 | Input bias | DMM on `ua[4]`, `ua[5]` (no generator) | about 1.37 V each | `rx_design.md` | |
| R4 | Idle outputs | No signal: scope `uo[4]`, `uo[5]` | no chatter on noise alone (hysteresis ±34-37 mV); TBD what the idle state looks like on silicon | `rx_design.md` Table IV | |
| R5 | Tone | Tune to 433.92 MHz (T7). Generator at f + 50 kHz, −70 dBm, DC-blocked into `ua[4]` (`ua[5]` to ground through a DC block and 50 Ω) | `q_i`, `q_q` square waves at 50 kHz, about 72° apart (I/Q phase 71-74°) | `rx_design.md` | |
| R6 | Sign | Repeat at f − 50 kHz | the same rate, I/Q order reversed. Which order means "above" is TBD: the circuit's sign is opposite to the model's | `rx_design.md` Table VI | |
| R7 | Passband | Δ = ±2, 5, 10, 20, 50, 100, 150, 300, 1000 kHz at a fixed level | toggles track Δ between about 8.5 kHz and 143 kHz (the baseband −3 dB points); weaker outside | `rx_design.md` Table IV | |
| R8 | Baseband | DBG_SEL = 1, then 2 (one bit at a time), Δ = 50 kHz | a 50 kHz signal on `ua[0]` (the positive output of each baseband arm, `oi_p` / `oq_p`); DC level and amplitude TBD | tile LVS source | |
| R9 | Sensitivity | Step the level down at Δ = 50 kHz; then 2-FSK ±100 kHz from the generator, if it can | `q_i` / `q_q` clean down to about −95 dBm at the antenna (FSK decoded with no errors at −95 and −70 dBm); model sensitivity −110.4 dBm (bit error rate 1e-3, 10 kbit/s) | `rx_design.md` | |
| R10 | Overload | Raise the level to −20 dBm | input 1 dB compression about −23.5 dBm (the baseband limits much earlier, by design); decoding at this level TBD | `rx_design.md` | |
| R11 | Recovery | Switch a strong tone on and off | blanked for about 1 ms (the AC couplings recover in 0.5-0.9 ms after a 10 mV step) | `rx_design.md` | |
| R12 | LO leakage | SDR cabled to `ua[4]` (DC block, attenuator), RX_EN = 1, TX off | the ring's line at about −108.7 dBm into a 73 Ω dipole | `rx_design.md` | |

Notes:
- **nb is a weak node.** Read it with a high-impedance probe only: a 1 MΩ load pulls it from 0.979 to 0.959 V
  (−2 %), and 100 kΩ to 0.629 V (−36 %) (`sim/mixed/results.md`). The same care applies to the baseband nodes.
- **One DBG_SEL bit at a time.** Two bits on join their nodes through about 1 kΩ (the switch on-resistance is
  0.84-1.25 kΩ, `tile_layout.md`). The firmware should refuse any value that isn't 0, 1, 2, 4 or 8.
- Read every `ua[0]` voltage against `ua[1]`, not the board ground.
- The generator's absolute frequency and the RP2350's count disagree by up to the sum of their reference errors
  (±13 kHz for the RP2350 alone), so set Δ well above that or calibrate the generator against the count first.

## 5. Two boards

Board A transmits, board B receives. Both run the `tuning.md` procedure against their own RP2350 crystals.

| # | Test | How | Expected | Source | Result |
|---|---|---|---|---|---|
| L1 | Offset | A: TX on, no FSK. B: RX_EN. Count both | B's `q_i` / `q_q` toggle at |f_A − f_B|, up to ±26 kHz from the two crystals (±13 kHz each) | `tuning.md` | |
| L2 | Set the offset | Move B's MED_INT / MED_FRAC until L1's toggle rate is the chosen offset (e.g. 0 or 20 kHz) | the rate follows B's word at its LSB (about 31 kHz per word) | Table VII | |
| L3 | FSK | A: FSK_DEV for ±100 kHz, `ui[7]` sends a known pattern | B's quadrature steps reverse direction with each bit; about 8 quadrant steps per bit at 50 kbit/s | `rx_design.md` Table VI | |
| L4 | Decode | B's RP2350 PIO counts `q_i` / `q_q` as a quadrature counter (rotation direction per bit); learns the sign from a preamble | the pattern recovered, no errors at 1 m | `rx_design.md` | |
| L5 | Cabled sensitivity | A's `ua[3]` through a DC block and step attenuator into B's `ua[4]`. Start at 60 dB, step down to the error threshold. Check that disconnecting the cable stops reception (leakage) | threshold near A's power (T9) − attenuation = −110 dBm (model); TBD on silicon | `rx_design.md` Table VII | |
| L6 | Range | Dipoles, line of sight, 1, 3, 10, 30 m …, record the bit errors | at 1 m, free-space loss is 20 log10(4π × 1 m / 0.691 m) = 25.2 dB, so B sees about +6 − 25 = −19 dBm (before antenna gain), above the −23.5 dBm compression point (see R10). Range: TBD | `tx_driver.md` + calculation | |
| L7 | Swap | Swap A and B, repeat L5 | thresholds agree within a few dB | | |

The decoder needs both arms. If `q_q` is dead, B can still detect FSK from `q_i`'s frequency alone, if the offset
is set so the two tones land at different rates (e.g. offset 20 kHz: 80 and 120 kHz).

## 6. Open questions and testability gaps

Things that are hard or impossible to observe with the current pins, for deciding on an extra debug option:

- **Only one side of each baseband arm.** DBG_SEL 1 / 2 tap `oi_p` / `oq_p`, not `oi_n` / `oq_n`. The differential
  signal, the arm's DC offset and the common mode can't be separated. A switch on each negative output (or a
  differential tap pair on `ua[0]` / a spare pin) would show the offset that the limiter must reject.
- **Nothing between the antenna and the baseband.** The low-noise amplifier (LNA) output, the mixer inputs and the
  RX LO buffers (`lo_i`, `lo_q`) are invisible. A weak `q` can be a low LNA gain, a dead LO buffer or a bad mixer.
  A debug switch on the LNA's output common mode (a DC level), and a divided copy of the Q LO on a spare `uo` pin,
  would split them.
- **The Q LO path only shows up at the end of the chain.** If `q_q` is dead, the Q tap level shifter (`rx_lsq`),
  the Q LO buffer, the Q mixer, Q baseband and Q limiter are all suspects. A digital tap of the Q LO (divided, like
  `uo[3]`) on `uo[6]` would separate them, and would also measure the 72° tap spacing directly.
- **Limiter input and comparator.** The comparator hysteresis (±34-37 mV) and the limiter stage's gain can't be
  measured; only the full-swing `q` outputs leave the chip. A DBG_SEL bit on the limiter stage output would show
  the signal against the hysteresis.
- **The VCO's internal nodes.** vg (the ring's shared node) and vbnf (the reference's RC-filtered bias) are not on
  any pin, so a slow or failed reference start-up (138 µs in simulation) shows only as a wrong frequency. A DBG_SEL
  bit on vbnf (high impedance, through the same switch) would allow a direct check.
- **The medium DAC and ΣΔ lines.** EFF_INT reads the integer word, but not the decoded 37 lines or the ΣΔ cell. A
  crossed line shows only as a frequency error (the mixed-signal mutants caught it that way). A register read of
  the ΣΔ bit, or a toggle count, would help.
- **Frequency without the dividers.** All counting goes through lsdiv's level shifter and ÷4, then the macro's
  ripple divider. If the ÷4 fails, only the TX carrier (from the level shifter, before the ÷4) on an SDR shows the
  ring is running. A raw ring tap is not possible at 434 MHz on a digital pad (about 50 MHz safe).
- **Per-block current.** The RX is on VAPWR and the ring, TX and macro on VDPWR, both shared with the rest of the
  chip on the demo board. Only differences (RX_EN on / off, TX on / off) can be measured. The ring's 0.39-0.52 mW is
  too small to see this way.
- **Debug bus safety.** Nothing in hardware stops two DBG_SEL bits being on, or `ua[0]` being driven while DBG_SEL
  selects nb or a baseband node. A one-hot decode in the macro (DBG_SEL as a 3-bit index) would remove the first.
- **Simultaneous TX and RX on one board.** They share the ring, so a board can't receive another board's signal
  while it transmits. Whether the TX pulls the RX LO (T12), and how much TX reaches the RX input, is TBD.
- **Stale how-to.** `docs/info.md` still says "DBG_SEL = 3" for vctrl (it is 8, bit 3), describes `uo[0]` as
  ungated f / 4 and vctrl as the fine control. It needs updating before the datasheet is built.
