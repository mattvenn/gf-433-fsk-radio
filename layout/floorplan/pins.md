# Floorplan: block positions and pin positions

Generated from the floorplan page's variant **B on the real blocks (tile step 3, 2026-11-17)** by `layout/floorplan/page/pinreport.js`; the placements are also in `floorplan.json` next to this file. Receiver: placed as its cells (the brief for an rx_top re-layout).

- Coordinates in µm, tile origin at its lower-left. **Placement**: lower-left of the placed (transformed) bbox, and the GDS orientation (KLayout `DCplxTrans(1, rot, mirror, …)`, mirror about x first).
- **Pins**: in each block's *own* frame (its bbox lower-left = 0, 0, before the orientation), grouped by the block's own edge; the tile direction each edge faces after placement is in brackets. "est." = not in the GDS yet (vco_top a2, tx_fine rx_en).

## Checks

| rule | status | value |
|---|---|---|
| 1. RX input far from the macro and clocks | pass | 211 µm |
| 2. LO wires short and matched | warn | a2 33 µm |
| 3. LNA at ua[4] / ua[5] | pass | 9 µm |
| 4. TX driver at ua[2] / ua[3] | pass | 0 µm |
| 5. Supply domains | warn | 47 crossings |
| 6. No digital or LO wire over the RX | pass | 7 round, +197 µm |
| 7. Short fine-tune bus | pass | 6 µm |
| 8. Macro near the top edge | pass | 12.6 µm |
| 9. Fit and spacing | pass | none |
| 10. Power stripes | pass | 38 clear |
| 11. VCO bias wires (vco_top split) | warn | 113 µm |
| 12. Debug mux next to its sources | pass | 20 µm |
| D. Decap VAPWR | info | ≈ 59.4 pF |
| D. Decap VDPWR | info | ≈ 1.7 pF |

## vco.core (ring_core_v3 + lsdiv, VAPWR)

- Size: 110.58 × 69.76 (GDS)
- Placement: x 272.01, y 133.50, MX (rot 0, mirror true)

- Pins moved: none: keeps its layout

**N edge** (faces south in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| ls | 20.98 | 69.56 |  |
| vctrl | 110.08 | 69.56 |  |

**S edge** (faces north in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| vg | 72.58 | 0.30 |  |

**W edge** (faces west in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| a2 | 0.10 | 32.30 |  |

**E edge** (faces east in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| bit4 | 110.48 | 55.79 |  |
| bitb4 | 110.48 | 56.59 |  |
| bit3 | 110.48 | 57.39 |  |
| bitb3 | 110.48 | 58.19 |  |
| bit2 | 110.48 | 58.99 |  |
| bitb2 | 110.48 | 59.79 |  |
| bit1 | 110.48 | 60.59 |  |
| bitb1 | 110.48 | 61.39 |  |
| bit0 | 110.48 | 62.19 |  |
| bitb0 | 110.48 | 62.99 |  |
| vbnf | 110.48 | 63.99 |  |
| ck | 110.48 | 66.19 |  |

## vco.ref (cgm_ref, VAPWR)

- Size: 238.75 × 69.19 (GDS)
- Placement: x 426.00, y 3.50, R0 (rot 0, mirror false)

- Pins moved: none: keeps its layout

**N edge** (faces north in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| vbnf | 2.19 | 68.60 |  |

**W edge** (faces west in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| vctrl_l | 0.49 | 68.60 |  |
| vctrl | 0.49 | 68.60 |  |

**E edge** (faces east in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| vbn | 238.65 | 48.60 |  |

## vco.decap (decap_ls, VAPWR)

- Size: 34.02 × 59.95 (GDS)
- Placement: x 13.91, y 56.95, R270 (rot 270, mirror false)

- Pins moved: none: keeps its layout

## xdbg_bbi (dbg_tg, VAPWR)

- Size: 7.41 × 15.97 (GDS)
- Placement: x 260.80, y 140.00, R0 (rot 0, mirror false)

- Pins moved: none: keeps its layout

**N edge** (faces north in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| ctrl | 3.40 | 15.78 |  |

**W edge** (faces west in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| mod | 0.15 | 6.48 |  |

**E edge** (faces east in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| bus | 7.26 | 6.48 |  |

## xdbg_bbq (dbg_tg, VAPWR)

- Size: 7.41 × 15.97 (GDS)
- Placement: x 118.00, y 150.50, R90 (rot 90, mirror false)

- Pins moved: none: keeps its layout

**N edge** (faces west in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| ctrl | 3.40 | 15.78 |  |

**W edge** (faces south in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| mod | 0.15 | 6.48 |  |

**E edge** (faces north in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| bus | 7.26 | 6.48 |  |

## xdbg_nb (dbg_tg, VAPWR)

- Size: 7.41 × 15.97 (GDS)
- Placement: x 399.00, y 89.50, R90 (rot 90, mirror false)

- Pins moved: none: keeps its layout

**N edge** (faces west in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| ctrl | 3.40 | 15.78 |  |

**W edge** (faces south in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| mod | 0.15 | 6.48 |  |

**E edge** (faces north in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| bus | 7.26 | 6.48 |  |

## xdbg_vctrl (dbg_tg, VAPWR)

- Size: 7.41 × 15.97 (GDS)
- Placement: x 427.00, y 76.00, R90 (rot 90, mirror false)

- Pins moved: none: keeps its layout

**N edge** (faces west in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| ctrl | 3.40 | 15.78 |  |

**W edge** (faces south in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| mod | 0.15 | 6.48 |  |

**E edge** (faces north in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| bus | 7.26 | 6.48 |  |

## xmdac (mdac, VAPWR)

- Size: 156.83 × 104.24 (GDS)
- Placement: x 276.08, y 207.00, MY (rot 180, mirror true)

- Pins moved: none: keeps its layout

**S edge** (faces south in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| vbnf | 50.57 | 0.19 |  |
| vg | 94.86 | 0.19 |  |

**W edge** (faces east in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| ns30 | 0.19 | 14.82 |  |
| ns28 | 0.19 | 18.72 |  |
| ns26 | 0.19 | 19.40 |  |
| ns24 | 0.19 | 23.30 |  |
| ns22 | 0.19 | 23.98 |  |
| ns20 | 0.19 | 27.88 |  |
| ns18 | 0.19 | 28.56 |  |
| ns16 | 0.19 | 32.46 |  |
| ns14 | 0.19 | 33.14 |  |
| ns12 | 0.19 | 37.04 |  |
| ns10 | 0.19 | 37.72 |  |
| ns8 | 0.19 | 41.62 |  |
| ns6 | 0.19 | 42.30 |  |
| ns4 | 0.19 | 46.20 |  |
| ns2 | 0.19 | 46.88 |  |
| nb4 | 0.19 | 50.78 |  |
| nb2 | 0.19 | 51.46 |  |
| nb0 | 0.19 | 55.36 |  |
| nsd | 0.19 | 56.04 |  |
| nb1 | 0.19 | 59.94 |  |
| nb3 | 0.19 | 60.62 |  |
| ns1 | 0.19 | 64.52 |  |
| ns3 | 0.19 | 65.20 |  |
| ns5 | 0.19 | 69.10 |  |
| ns7 | 0.19 | 69.78 |  |
| ns9 | 0.19 | 73.68 |  |
| ns11 | 0.19 | 74.36 |  |
| ns13 | 0.19 | 78.26 |  |
| ns15 | 0.19 | 78.94 |  |
| ns17 | 0.19 | 82.84 |  |
| ns19 | 0.19 | 83.52 |  |
| ns21 | 0.19 | 87.42 |  |
| ns23 | 0.19 | 88.10 |  |
| ns25 | 0.19 | 92.00 |  |
| ns27 | 0.19 | 92.68 |  |
| ns29 | 0.19 | 96.58 |  |
| ns31 | 0.19 | 97.26 |  |

## xvpd (vctrl_pd, VAPWR)

- Size: 32.49 × 12.00 (GDS)
- Placement: x 400.00, y 106.00, R0 (rot 0, mirror false)

- Pins moved: none: keeps its layout

**W edge** (faces west in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| b | 0.58 | 0.90 |  |

**E edge** (faces east in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| a | 31.91 | 11.10 |  |

## xbits (bits_inv, VAPWR)

- Size: 19.04 × 9.04 (standard cells, tt_wrapper.py)
- Placement: x 393.00, y 150.00, R90 (rot 90, mirror false)

- Pins moved: none: keeps its layout

**N edge** (faces west in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| in | 10.08 | 7.84 |  |

**S edge** (faces east in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| out | 10.08 | 0.00 |  |

## xtxd (tx_drv, VDPWR)

- Size: 72.97 × 105.92 (GDS)
- Placement: x 167.53, y 0.05, R270 (rot 270, mirror false)

- Pins moved: none: keeps its layout

**W edge** (faces north in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| en_n | 0.20 | 87.55 |  |
| en_p | 0.20 | 94.83 |  |
| ls | 0.20 | 102.81 |  |

**E edge** (faces south in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| out_p | 72.57 | 10.83 |  |
| out_n | 72.57 | 54.51 |  |

## xmac (tx_fine, VDPWR)

- Size: 250.00 × 176.80 (GDS)
- Placement: x 438.00, y 136.00, MY (rot 180, mirror true)

- Pins moved: none: keeps its layout

The 37 DAC lines (dac_tn[0:30], dac_bn[0:4], dac_sdn) are on its own east edge, y 8.1 … 250.0 (as hardened).

**N edge** (faces north in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| clk | 236.60 | 176.52 |  |
| rst_n | 237.72 | 176.52 |  |
| fsk | 238.84 | 176.52 |  |
| sclk | 239.96 | 176.52 |  |
| mosi | 241.08 | 176.52 |  |
| cs_n | 242.20 | 176.52 |  |
| ck_o | 243.32 | 176.52 |  |
| div16 | 244.44 | 176.52 |  |
| div64 | 245.56 | 176.52 |  |
| div1024 | 246.68 | 176.52 |  |
| miso | 247.80 | 176.52 |  |

**S edge** (faces south in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| dbg_sel[3] | 244.44 | 0.28 |  |
| dbg_sel[2] | 245.56 | 0.28 |  |
| rx_en | 246.68 | 0.28 |  |
| ck | 247.80 | 0.28 |  |

**E edge** (faces west in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| dbg_sel[1] | 249.72 | 10.36 |  |
| dbg_sel[0] | 249.72 | 28.28 |  |

## rx.lna (rx_lna, VAPWR)

- Size: 98.06 × 75.53 (GDS)
- Placement: x 76.50, y 3.00, R90 (rot 90, mirror false)

- Pins moved: none: keeps its layout

**N edge** (faces west in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| oqp | 90.44 | 75.34 |  |
| oqn | 91.80 | 75.34 |  |

**S edge** (faces east in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| nb | 82.96 | 0.20 |  |
| enb | 84.32 | 0.20 |  |
| oip | 89.08 | 0.20 |  |
| oin | 90.44 | 0.20 |  |

**W edge** (faces south in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| inp | 0.15 | 16.68 |  |
| inn | 0.15 | 67.00 |  |

## rx.bias (rx_bias, VAPWR)

- Size: 84.19 × 24.82 (GDS)
- Placement: x 398.00, y 3.00, R90 (rot 90, mirror false)

- Pins moved: none: keeps its layout

**N edge** (faces west in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| nb | 80.92 | 24.61 |  |
| en | 82.28 | 24.61 |  |
| enb | 83.64 | 24.61 |  |

## rx.lsq (rx_lsq, VAPWR)

- Size: 40.49 × 54.75 (GDS)
- Placement: x 216.45, y 107.20, MX (rot 0, mirror true)

- Pins moved: none: keeps its layout

**N edge** (faces south in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| qenb | 3.82 | 54.55 |  |

**W edge** (faces west in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| lsq | 0.15 | 3.10 |  |

**E edge** (faces east in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| aq | 40.39 | 7.12 |  |

## rx.lobuf_q (rx_lobuf, VAPWR)

- Size: 63.60 × 19.54 (GDS)
- Placement: x 54.34, y 96.97, MXR90 (rot 90, mirror true)

- Pins moved: none: keeps its layout

**N edge** (faces east in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| in | 58.48 | 19.34 |  |

**S edge** (faces west in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| lo | 36.82 | 0.20 |  |
| lob | 38.18 | 0.20 |  |

**E edge** (faces north in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| en | 63.45 | 9.20 |  |

## rx.mix_q (rx_mix, VAPWR)

- Size: 44.36 × 28.14 (GDS)
- Placement: x 23.69, y 106.13, MXR90 (rot 90, mirror true)

- Pins moved: none: keeps its layout

**N edge** (faces east in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| lo | 27.20 | 27.93 |  |
| lob | 28.56 | 27.93 |  |

**S edge** (faces west in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| rfp | 1.36 | 0.20 |  |
| rfn | 2.72 | 0.20 |  |

**E edge** (faces north in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| bbp | 44.21 | 13.28 |  |
| bbn | 44.21 | 14.64 |  |

## rx.lobuf_i (rx_lobuf, VAPWR)

- Size: 63.60 × 19.54 (GDS)
- Placement: x 190.17, y 81.44, MXR90 (rot 90, mirror true)

- Pins moved: none: keeps its layout

**N edge** (faces east in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| in | 58.48 | 19.34 |  |

**S edge** (faces west in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| lo | 36.82 | 0.20 |  |
| lob | 38.18 | 0.20 |  |

**E edge** (faces north in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| en | 63.45 | 9.20 |  |

## rx.mix_i (rx_mix, VAPWR)

- Size: 44.36 × 28.14 (GDS)
- Placement: x 159.53, y 91.06, MXR90 (rot 90, mirror true)

- Pins moved: none: keeps its layout

**N edge** (faces east in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| lo | 27.20 | 27.93 |  |
| lob | 28.56 | 27.93 |  |

**S edge** (faces west in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| rfp | 1.36 | 0.20 |  |
| rfn | 2.72 | 0.20 |  |

**E edge** (faces north in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| bbp | 44.21 | 13.28 |  |
| bbn | 44.21 | 14.64 |  |

## rx.bb_i (rx_bb, VAPWR)

- Size: 130.66 × 144.19 (GDS)
- Placement: x 138.50, y 164.50, R0 (rot 0, mirror false)

- Pins moved: none: keeps its layout

**S edge** (faces south in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| inp | 36.72 | 0.20 |  |
| inn | 38.08 | 0.20 |  |
| outp | 121.04 | 0.20 |  |
| outn | 122.40 | 0.20 |  |
| enb | 123.76 | 0.20 |  |
| nb | 125.12 | 0.20 |  |

## rx.bb_q (rx_bb, VAPWR)

- Size: 130.66 × 144.19 (GDS)
- Placement: x 4.05, y 163.09, R0 (rot 0, mirror false)

- Pins moved: none: keeps its layout

**S edge** (faces south in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| inp | 36.72 | 0.20 |  |
| inn | 38.08 | 0.20 |  |
| outp | 121.04 | 0.20 |  |
| outn | 122.40 | 0.20 |  |
| enb | 123.76 | 0.20 |  |
| nb | 125.12 | 0.20 |  |

## rx.lim_i (rx_lim, VAPWR)

- Size: 115.74 × 59.98 (GDS)
- Placement: x 276.27, y 3.00, MX (rot 0, mirror true)

- Pins moved: none: keeps its layout

**S edge** (faces north in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| inp | 6.12 | 0.20 |  |
| inn | 7.48 | 0.20 |  |

**W edge** (faces west in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| q | 0.15 | 3.10 |  |

**E edge** (faces east in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| enb | 115.59 | 39.12 |  |
| nb | 115.59 | 41.16 |  |

## rx.lim_q (rx_lim, VAPWR)

- Size: 115.74 × 59.98 (GDS)
- Placement: x 276.27, y 68.50, MX (rot 0, mirror true)

- Pins moved: none: keeps its layout

**S edge** (faces north in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| inp | 6.12 | 0.20 |  |
| inn | 7.48 | 0.20 |  |

**W edge** (faces west in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| q | 0.15 | 3.10 |  |

**E edge** (faces east in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| enb | 115.59 | 39.12 |  |
| nb | 115.59 | 41.16 |  |

## rx.decap (rx_decap, VAPWR)

- Size: 55.74 × 40.90 (GDS)
- Placement: x 17.00, y 12.00, MX (rot 0, mirror true)

- Pins moved: none: keeps its layout

## Stripes, decap, reserved areas

- VGND stripe: x 14.01, w 2.00 (Metal4, y 5 … 320.36)
- VGND stripe: x 23.79, w 2.00 (Metal4, y 5 … 320.36)
- VAPWR stripe: x 49.52, w 2.00 (Metal4, y 5 … 320.36)
- VGND stripe: x 54.44, w 2.00 (Metal4, y 5 … 320.36)
- VAPWR stripe: x 66.88, w 2.00 (Metal4, y 5 … 320.36)
- VGND stripe: x 69.88, w 2.00 (Metal4, y 5 … 320.36)
- VAPWR stripe: x 118.10, w 2.00 (Metal4, y 5 … 320.36)
- VGND stripe: x 131.67, w 2.00 (Metal4, y 5 … 320.36)
- VGND stripe: x 159.63, w 2.00 (Metal4, y 5 … 320.36)
- VAPWR stripe: x 185.36, w 2.00 (Metal4, y 5 … 320.36)
- VGND stripe: x 190.27, w 2.00 (Metal4, y 5 … 320.36)
- VAPWR stripe: x 201.33, w 2.00 (Metal4, y 5 … 320.36)
- VGND stripe: x 204.33, w 2.00 (Metal4, y 5 … 320.36)
- VAPWR stripe: x 207.41, w 2.00 (Metal4, y 5 … 320.36)
- VAPWR stripe: x 216.55, w 2.00 (Metal4, y 5 … 320.36)
- VDPWR stripe: x 235.03, w 2.00 (Metal4, y 5 … 320.36)
- VGND stripe: x 238.35, w 2.00 (Metal4, y 5 … 320.36)
- VAPWR stripe: x 260.90, w 2.00 (Metal4, y 5 … 320.36)
- VGND stripe: x 263.96, w 2.00 (Metal4, y 5 … 320.36)
- VAPWR stripe: x 293.61, w 2.00 (Metal4, y 5 … 320.36)
- VAPWR stripe: x 351.99, w 2.00 (Metal4, y 5 … 320.36)
- VGND stripe: x 354.99, w 2.00 (Metal4, y 5 … 320.36)
- VAPWR stripe: x 399.10, w 2.00 (Metal4, y 5 … 320.36)
- VGND stripe: x 412.67, w 2.00 (Metal4, y 5 … 320.36)
- VGND stripe: x 420.51, w 2.00 (Metal4, y 5 … 320.36)
- VAPWR stripe: x 429.48, w 2.00 (Metal4, y 5 … 320.36)
- VGND stripe: x 467.88, w 1.60 (Metal4, y 5 … 320.36)
- VDPWR stripe: x 470.48, w 1.60 (Metal4, y 5 … 320.36)
- VGND stripe: x 507.88, w 1.60 (Metal4, y 5 … 320.36)
- VDPWR stripe: x 510.48, w 1.60 (Metal4, y 5 … 320.36)
- VGND stripe: x 547.88, w 1.60 (Metal4, y 5 … 320.36)
- VDPWR stripe: x 550.48, w 1.60 (Metal4, y 5 … 320.36)
- VGND stripe: x 587.88, w 1.60 (Metal4, y 5 … 320.36)
- VDPWR stripe: x 590.48, w 1.60 (Metal4, y 5 … 320.36)
- VGND stripe: x 627.88, w 1.60 (Metal4, y 5 … 320.36)
- VDPWR stripe: x 630.48, w 1.60 (Metal4, y 5 … 320.36)
- VGND stripe: x 667.88, w 1.60 (Metal4, y 5 … 320.36)
- VDPWR stripe: x 670.48, w 1.60 (Metal4, y 5 … 320.36)
- decap VAPWR 1: x 445.58, y 76.00, 247.42 × 52.40
- decap VAPWR 2: x 77.00, y 104.00, 79.93 × 43.00
- decap VAPWR 3: x 404.64, y 120.60, 25.76 × 74.40
- decap VAPWR 4: x 668.00, y 3.00, 25.00 × 70.00
- decap VAPWR 5: x 0.00, y 3.00, 11.00 × 157.00
- decap VAPWR 6: x 340.00, y 313.84, 90.40 × 8.16
- decap VAPWR 7: x 212.31, y 76.00, 60.69 × 12.00
- decap VAPWR 8: x 160.00, y 138.02, 27.00 × 23.88
- decap VAPWR 9: x 213.00, y 91.00, 60.00 × 8.00
- decap VAPWR 10: x 77.00, y 150.00, 38.40 × 10.00
- decap VDPWR 1: x 155.00, y 3.00, 9.93 × 70.00

## Supply crossings (VAPWR ↔ VDPWR)

- ls tx: vco.core.ls (VAPWR) → xtxd.ls (VDPWR)
- ck: vco.core.ck (VAPWR) → xmac.ck (VDPWR)
- rx_en: xmac.rx_en (VDPWR) → rx.bias.en (VAPWR)
- code: ui_in[2] (VDPWR) → xbits.in (VAPWR)
- q_i: rx.lim_i.q (VAPWR) → uo_out[4] (VDPWR)
- q_q: rx.lim_q.q (VAPWR) → uo_out[5] (VDPWR)
- dbg_sel[0]: xmac.dbg_sel[0] (VDPWR) → xdbg_bbi.ctrl (VAPWR)
- dbg_sel[1]: xmac.dbg_sel[1] (VDPWR) → xdbg_bbq.ctrl (VAPWR)
- dbg_sel[2]: xmac.dbg_sel[2] (VDPWR) → xdbg_nb.ctrl (VAPWR)
- dbg_sel[3]: xmac.dbg_sel[3] (VDPWR) → xdbg_vctrl.ctrl (VAPWR)
- the 37 DAC lines: tx_fine (VDPWR) → mdac (VAPWR)
