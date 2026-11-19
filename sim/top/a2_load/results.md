# I/Q phase and ring frequency against the load on a2 (2026-11-19)

`python3 sim/top/a2_load/a2_load_iq.py` (about 4 minutes, 9 runs): `sim/rx/rx_lo.py`'s ring bench (the extracted ring,
the extracted lsdiv on a0 for I, an identical extracted lsdiv copy straight on a2 for Q, both mixers as the LO load),
with an extra capacitor from a2 to ground. Rows: `rows.json`. No run logged "Transient op" or "singular".

**Table 1.** I/Q LO phase (Q lags I) and ring frequency.

| Corner, code | +0 fF (symmetric taps) | +8 fF (a shorter a2 re-route) | +16.6 fF (the tile at fca76de) |
|---|---|---|---|
| tt, 9 | 409.6 MHz, 72.2° | 383.0 MHz, 75.0° | 358.4 MHz, 79.9° |
| ss, 11 | 411.2 MHz, 71.6° | 385.1 MHz, 75.1° | 360.8 MHz, 80.9° |
| ff, 7 | 409.1 MHz, 71.0° | 382.1 MHz, 75.8° | 357.1 MHz, 79.7° |

About +0.5° of I/Q skew and -0.75 % of frequency per fF on a2. The tile itself measured 74.6°: its I path also has a
long wire (ls, 59 fF, after the level shifter), which delays I and partly cancels the Q skew. Decision (Matt,
2026-11-19): make the Q tap a mirror of the I tap (the Q level shifter against the ring, branch `iq-symmetry`), and
check the tile's I/Q LO phase against 72 ± 3°.
