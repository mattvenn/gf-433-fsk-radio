# Floorplan: block positions and pin positions

Generated from the floorplan page's variant **B - Matt's edit, tidied: pins moved on 13 blocks** by `layout/floorplan/page/pinreport.js`; the placements are also in `floorplan.json` next to this file. Receiver: placed as its cells (the brief for an rx_top re-layout).

- Coordinates in µm, tile origin at its lower-left. **Placement**: lower-left of the placed (transformed) bbox, and the GDS orientation (KLayout `DCplxTrans(1, rot, mirror, …)`, mirror about x first).
- **Pins**: in each block's *own* frame (its bbox lower-left = 0, 0, before the orientation), grouped by the block's own edge; the tile direction each edge faces after placement is in brackets. "est." = not in the GDS yet (vco_top a2, tx_fine rx_en).

## Checks

| rule | status | value |
|---|---|---|
| 1. RX input far from the macro and clocks | pass | 210 µm |
| 2. LO wires short and matched | pass | a2 10 µm |
| 3. LNA at ua[4] / ua[5] | pass | 3 µm |
| 4. TX driver at ua[2] / ua[3] | pass | 0 µm |
| 5. Supply domains | warn | 47 crossings |
| 6. No digital or LO wire over the RX | pass | 4 round, +58 µm |
| 7. Short fine-tune bus | pass | 6 µm |
| 8. Macro near the top edge | pass | 12.6 µm |
| 9. Fit and spacing | warn | 1 tight |
| 10. Power stripes | pass | 14 clear |
| 11. VCO bias wires (vco_top split) | warn | 108 µm |
| 12. Debug mux next to its sources | pass | 5 µm |
| D. Decap VAPWR | info | ≈ 68.5 pF |
| D. Decap VDPWR | info | ≈ 1.7 pF |

## vco.core (ring_core_v3 + lsdiv, VAPWR)

- Size: 110.58 × 69.76 (GDS)
- Placement: x 272.01, y 125.51, MX (rot 0, mirror true)

- Pins moved: 7 (marked; a re-layout)

**N edge** (faces south in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| ls | 1.00 | 69.51 | **moved** |
| vctrl | 109.58 | 69.51 | **moved** (was E edge) |

**S edge** (faces north in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| vg | 72.58 | 0.25 | **moved** |

**W edge** (faces west in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| a2 | 0.25 | 45.48 | **moved** (was N edge) |

**E edge** (faces east in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| bit2 | 110.33 | 51.66 | **moved** (was N edge) |
| vbnf | 110.33 | 60.03 | **moved** |
| ck | 110.33 | 68.27 | **moved** (was W edge) |

## vco.ref (cgm_ref, VAPWR)

- Size: 238.75 × 69.19 (GDS)
- Placement: x 426.00, y 3.50, R0 (rot 0, mirror false)

- Pins moved: 3 (marked; a re-layout)

**N edge** (faces north in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| vctrl_l | 1.00 | 68.94 | **moved** (was W edge) |
| vbnf | 2.00 | 68.94 | **moved** (was W edge) |
| vctrl | 4.46 | 68.94 | **moved** (was E edge) |

**E edge** (faces east in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| vbn | 238.65 | 48.60 |  |

## vco.decap (decap_ls, VAPWR)

- Size: 37.23 × 59.95 (GDS)
- Placement: x 13.91, y 56.95, R270 (rot 270, mirror false)

- Pins moved: none: keeps its layout

## xdbg_bbi (dbg_tg, VAPWR)

- Size: 15.00 × 12.00 (GDS)
- Placement: x 255.00, y 160.00, R270 (rot 270, mirror false)

- Pins moved: 3 (marked; a re-layout)

**N edge** (faces east in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| ctrl | 1.00 | 11.75 | **moved** (was W edge) |
| mod | 10.25 | 11.75 | **moved** |

**E edge** (faces south in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| bus | 14.75 | 11.00 | **moved** (was S edge) |

## xdbg_bbq (dbg_tg, VAPWR)

- Size: 15.00 × 12.00 (GDS)
- Placement: x 127.00, y 150.00, R0 (rot 0, mirror false)

- Pins moved: 3 (marked; a re-layout)

**N edge** (faces north in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| mod | 7.46 | 11.75 | **moved** |

**E edge** (faces east in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| bus | 14.75 | 1.00 | **moved** (was S edge) |
| ctrl | 14.75 | 6.00 | **moved** (was W edge) |

## xdbg_nb (dbg_tg, VAPWR)

- Size: 15.00 × 12.00 (GDS)
- Placement: x 395.00, y 72.00, R0 (rot 0, mirror false)

- Pins moved: 3 (marked; a re-layout)

**N edge** (faces north in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| mod | 3.25 | 11.75 | **moved** |
| ctrl | 14.00 | 11.75 | **moved** (was W edge) |

**W edge** (faces west in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| bus | 0.25 | 1.00 | **moved** (was S edge) |

## xdbg_vctrl (dbg_tg, VAPWR)

- Size: 15.00 × 12.00 (GDS)
- Placement: x 426.00, y 73.00, R180 (rot 180, mirror false)

- Pins moved: 3 (marked; a re-layout)

**N edge** (faces south in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| mod | 12.00 | 11.75 | **moved** |

**S edge** (faces north in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| ctrl | 1.00 | 0.25 | **moved** (was W edge) |

**E edge** (faces west in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| bus | 14.75 | 11.00 | **moved** (was S edge) |

## xmdac (mdac, VAPWR)

- Size: 156.83 × 104.24 (GDS)
- Placement: x 276.08, y 197.79, MY (rot 180, mirror true)

- Pins moved: 39 (marked; a re-layout)

**S edge** (faces south in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| vbnf | 50.57 | 0.25 | **moved** (was E edge) |
| vg | 88.32 | 0.25 | **moved** (was E edge) |

**W edge** (faces east in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| ns30 | 0.25 | 4.82 | **moved** |
| ns28 | 0.25 | 8.72 | **moved** |
| ns26 | 0.25 | 9.72 | **moved** |
| ns24 | 0.25 | 13.30 | **moved** |
| ns22 | 0.25 | 14.30 | **moved** |
| ns20 | 0.25 | 17.88 | **moved** |
| ns18 | 0.25 | 18.88 | **moved** |
| ns16 | 0.25 | 22.46 | **moved** |
| ns14 | 0.25 | 23.46 | **moved** |
| ns12 | 0.25 | 27.04 | **moved** |
| ns10 | 0.25 | 28.04 | **moved** |
| ns8 | 0.25 | 31.62 | **moved** |
| ns6 | 0.25 | 32.62 | **moved** |
| ns4 | 0.25 | 36.20 | **moved** |
| ns2 | 0.25 | 37.20 | **moved** |
| nb4 | 0.25 | 40.78 | **moved** |
| nb2 | 0.25 | 41.78 | **moved** |
| nb0 | 0.25 | 45.36 | **moved** |
| nsd | 0.25 | 46.36 | **moved** |
| nb1 | 0.25 | 49.94 | **moved** |
| nb3 | 0.25 | 50.94 | **moved** |
| ns1 | 0.25 | 54.52 | **moved** |
| ns3 | 0.25 | 55.52 | **moved** |
| ns5 | 0.25 | 59.10 | **moved** |
| ns7 | 0.25 | 60.10 | **moved** |
| ns9 | 0.25 | 63.68 | **moved** |
| ns11 | 0.25 | 64.68 | **moved** |
| ns13 | 0.25 | 68.26 | **moved** |
| ns15 | 0.25 | 69.26 | **moved** |
| ns17 | 0.25 | 72.84 | **moved** |
| ns19 | 0.25 | 73.84 | **moved** |
| ns21 | 0.25 | 77.42 | **moved** |
| ns23 | 0.25 | 78.42 | **moved** |
| ns25 | 0.25 | 82.00 | **moved** |
| ns27 | 0.25 | 83.00 | **moved** |
| ns29 | 0.25 | 86.58 | **moved** |
| ns31 | 0.25 | 87.58 | **moved** |

## xvpd (vctrl_pd, VAPWR)

- Size: 32.49 × 12.00 (GDS)
- Placement: x 400.00, y 90.00, R0 (rot 0, mirror false)

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

- Size: 20.16 × 7.84 (standard cells, tt_wrapper.py)
- Placement: x 385.21, y 133.53, R90 (rot 90, mirror false)

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

- Pins moved: 5 (marked; a re-layout)

**W edge** (faces north in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| en_n | 0.25 | 87.55 | **moved** (was N edge) |
| en_p | 0.25 | 94.83 | **moved** (was N edge) |
| ls | 0.25 | 104.92 | **moved** (was N edge) |

**E edge** (faces south in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| out_p | 72.72 | 10.83 | **moved** |
| out_n | 72.72 | 54.51 | **moved** (was W edge) |

## xmac (tx_fine, VDPWR)

- Size: 250.00 × 176.80 (reshaped from 170 × 260: re-harden at this size; pin positions scaled)
- Placement: x 438.00, y 136.00, MY (rot 180, mirror true)

- Pins moved: 54 (marked; a re-layout, for the macro a new pin_order.cfg)

The 37 DAC lines (dac_sdn, dac_bn[0:4], dac_tn[0:30], in that order) **moved**: E edge of its own frame, 66.61 … 149.37 µm along it (the full list is in floorplan.json, pins_moved).

**S edge** (faces south in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| dbg_sel[3] | 247.00 | 0.25 | **moved** |
| dbg_sel[2] | 248.00 | 0.25 | **moved** |
| rx_en | 249.00 | 0.25 | **moved** (was E edge) |
| ck | 249.75 | -9.00 | **moved** |

**E edge** (faces west in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| dbg_sel[1] | 249.75 | 10.00 | **moved** (was S edge) |
| dbg_sel[0] | 249.75 | 28.00 | **moved** (was S edge) |
| ck_o | 249.75 | 165.80 | **moved** (was N edge) |
| div16 | 249.75 | 166.80 | **moved** (was N edge) |
| div64 | 249.75 | 167.80 | **moved** (was N edge) |
| div1024 | 249.75 | 168.80 | **moved** (was N edge) |
| clk | 249.75 | 169.80 | **moved** (was N edge) |
| rst_n | 249.75 | 170.80 | **moved** (was N edge) |
| sclk | 249.75 | 171.80 | **moved** (was N edge) |
| mosi | 249.75 | 172.80 | **moved** (was N edge) |
| cs_n | 249.75 | 173.80 | **moved** (was N edge) |
| miso | 249.75 | 174.80 | **moved** (was N edge) |
| fsk | 249.75 | 175.80 | **moved** (was N edge) |

## rx.lna (rx_lna, VAPWR)

- Size: 98.06 × 75.53 (GDS)
- Placement: x 76.50, y 3.00, R90 (rot 90, mirror false)

- Pins moved: 8 (marked; a re-layout)

**N edge** (faces west in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| oqp | 96.06 | 75.28 | **moved** (was E edge) |
| oqn | 97.06 | 75.28 | **moved** (was E edge) |

**S edge** (faces east in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| nb | 83.19 | 0.25 | **moved** (was E edge) |
| enb | 84.19 | 0.25 | **moved** (was E edge) |
| oip | 89.06 | 0.25 | **moved** (was E edge) |
| oin | 90.06 | 0.25 | **moved** (was E edge) |

**W edge** (faces south in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| inp | 0.25 | 17.35 | **moved** |
| inn | 0.25 | 61.03 | **moved** |

## rx.bias (rx_bias, VAPWR)

- Size: 84.19 × 24.82 (GDS)
- Placement: x 398.00, y 3.00, R90 (rot 90, mirror false)

- Pins moved: 3 (marked; a re-layout)

**N edge** (faces west in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| nb | 81.19 | 24.57 | **moved** (was E edge) |
| en | 82.19 | 24.57 | **moved** (was E edge) |
| enb | 83.19 | 24.57 | **moved** (was E edge) |

## rx.lsq (rx_lsq, VAPWR)

- Size: 40.49 × 54.75 (GDS)
- Placement: x 222.45, y 102.16, MX (rot 0, mirror true)

- Pins moved: 2 (marked; a re-layout)

**N edge** (faces south in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| qenb | 3.82 | 54.55 |  |

**W edge** (faces west in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| lsq | 0.25 | 1.00 | **moved** (was N edge) |

**E edge** (faces east in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| aq | 40.24 | 7.12 | **moved** |

## rx.lobuf_q (rx_lobuf, VAPWR)

- Size: 63.60 × 19.54 (GDS)
- Placement: x 54.34, y 96.97, MXR90 (rot 90, mirror true)

- Pins moved: 4 (marked; a re-layout)

**N edge** (faces east in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| en | 1.00 | 19.29 | **moved** (was E edge) |
| in | 58.94 | 19.29 | **moved** (was E edge) |

**S edge** (faces west in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| lo | 36.35 | 0.25 | **moved** |
| lob | 37.71 | 0.25 | **moved** |

## rx.mix_q (rx_mix, VAPWR)

- Size: 44.36 × 28.14 (GDS)
- Placement: x 23.69, y 106.12, MXR90 (rot 90, mirror true)

- Pins moved: none: keeps its layout

**N edge** (faces east in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| lo | 27.20 | 27.93 |  |
| lob | 28.56 | 27.93 |  |

**W edge** (faces south in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| rfp | 0.15 | 12.60 |  |
| rfn | 0.15 | 15.32 |  |

**E edge** (faces north in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| bbp | 44.21 | 13.28 |  |
| bbn | 44.21 | 14.64 |  |

## rx.lobuf_i (rx_lobuf, VAPWR)

- Size: 63.60 × 19.54 (GDS)
- Placement: x 190.17, y 91.49, R270 (rot 270, mirror false)

- Pins moved: none: keeps its layout

**S edge** (faces west in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| lo | 36.82 | 0.20 |  |
| lob | 38.18 | 0.20 |  |

**E edge** (faces south in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| in | 63.45 | 7.84 |  |
| en | 63.45 | 9.20 |  |

## rx.mix_i (rx_mix, VAPWR)

- Size: 44.36 × 28.14 (GDS)
- Placement: x 159.53, y 91.06, MXR90 (rot 90, mirror true)

- Pins moved: 6 (marked; a re-layout)

**N edge** (faces east in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| lob | 25.85 | 27.89 | **moved** |
| lo | 27.21 | 27.89 | **moved** |

**S edge** (faces west in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| rfp | 1.00 | 0.25 | **moved** (was W edge) |
| rfn | 2.00 | 0.25 | **moved** (was W edge) |

**E edge** (faces north in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| bbp | 44.11 | 15.69 | **moved** |
| bbn | 44.11 | 17.05 | **moved** |

## rx.bb_i (rx_bb, VAPWR)

- Size: 130.66 × 144.19 (GDS)
- Placement: x 138.50, y 164.50, R0 (rot 0, mirror false)

- Pins moved: 6 (marked; a re-layout)

**S edge** (faces south in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| inp | 35.72 | 0.25 | **moved** |
| inn | 37.08 | 0.25 | **moved** |
| outp | 128.66 | 0.25 | **moved** (was N edge) |
| outn | 129.66 | 0.25 | **moved** (was N edge) |

**E edge** (faces east in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| nb | 130.41 | 1.00 | **moved** (was S edge) |
| enb | 130.41 | 2.00 | **moved** (was S edge) |

## rx.bb_q (rx_bb, VAPWR)

- Size: 130.66 × 144.19 (GDS)
- Placement: x 4.05, y 163.09, R0 (rot 0, mirror false)

- Pins moved: 6 (marked; a re-layout)

**S edge** (faces south in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| inp | 32.92 | 0.25 | **moved** |
| inn | 34.28 | 0.25 | **moved** |

**E edge** (faces east in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| nb | 130.41 | 1.00 | **moved** (was S edge) |
| enb | 130.41 | 2.00 | **moved** (was S edge) |
| outn | 130.41 | 3.00 | **moved** (was N edge) |
| outp | 130.41 | 4.00 | **moved** (was N edge) |

## rx.lim_i (rx_lim, VAPWR)

- Size: 115.74 × 59.30 (GDS)
- Placement: x 276.27, y 3.00, MX (rot 0, mirror true)

- Pins moved: 5 (marked; a re-layout)

**S edge** (faces north in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| inp | 1.00 | 0.25 | **moved** |
| inn | 2.00 | 0.25 | **moved** |
| nb | 113.74 | 0.25 | **moved** |
| enb | 114.74 | 0.25 | **moved** |

**W edge** (faces west in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| q | 0.00 | 0.25 | **moved** (was N edge) |

## rx.lim_q (rx_lim, VAPWR)

- Size: 115.74 × 59.30 (GDS)
- Placement: x 276.01, y 64.81, MX (rot 0, mirror true)

- Pins moved: 5 (marked; a re-layout)

**S edge** (faces north in the tile; left → right, x):

| pin | x | y | |
|---|---|---|---|
| q | 1.00 | 0.25 | **moved** (was N edge) |

**W edge** (faces west in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| inp | 0.25 | 1.00 | **moved** (was S edge) |
| inn | 0.25 | 2.00 | **moved** (was S edge) |

**E edge** (faces east in the tile; bottom → top, y):

| pin | x | y | |
|---|---|---|---|
| nb | 115.49 | 37.92 | **moved** (was S edge) |
| enb | 115.49 | 38.92 | **moved** (was S edge) |

## rx.decap (rx_decap, VAPWR)

- Size: 55.74 × 40.90 (GDS)
- Placement: x 17.00, y 12.00, MX (rot 0, mirror true)

- Pins moved: none: keeps its layout

## Stripes, decap, reserved areas

- VDPWR stripe: x 662.99, w 1.60 (Metal4, y 5 … 320.36)
- VGND stripe: x 659.17, w 1.60 (Metal4, y 5 … 320.36)
- VDPWR stripe: x 604.17, w 1.60 (Metal4, y 5 … 320.36)
- VGND stripe: x 600.34, w 1.60 (Metal4, y 5 … 320.36)
- VDPWR stripe: x 545.34, w 1.60 (Metal4, y 5 … 320.36)
- VGND stripe: x 541.52, w 1.60 (Metal4, y 5 … 320.36)
- VDPWR stripe: x 486.52, w 1.60 (Metal4, y 5 … 320.36)
- VGND stripe: x 482.69, w 1.60 (Metal4, y 5 … 320.36)
- VAPWR stripe: x 201.33, w 2.00 (Metal4, y 5 … 320.36)
- VGND stripe: x 204.33, w 2.00 (Metal4, y 5 … 320.36)
- VAPWR stripe: x 66.88, w 2.00 (Metal4, y 5 … 320.36)
- VGND stripe: x 69.88, w 2.00 (Metal4, y 5 … 320.36)
- VAPWR stripe: x 351.99, w 2.00 (Metal4, y 5 … 320.36)
- VGND stripe: x 354.99, w 2.00 (Metal4, y 5 … 320.36)
- decap VAPWR 1: x 444.00, y 76.00, 249.00 × 55.00
- decap VAPWR 2: x 77.00, y 104.00, 80.00 × 43.00
- decap VAPWR 3: x 396.00, y 105.00, 37.00 × 90.00
- decap VAPWR 4: x 668.00, y 3.00, 25.00 × 70.00
- decap VAPWR 5: x 0.00, y 3.00, 11.00 × 157.00
- decap VAPWR 6: x 340.00, y 305.00, 93.00 × 17.00
- decap VAPWR 7: x 155.00, y 76.00, 118.00 × 12.00
- decap VAPWR 8: x 160.00, y 138.00, 27.00 × 24.00
- decap VAPWR 9: x 213.00, y 91.00, 60.00 × 8.00
- decap VAPWR 10: x 77.00, y 150.00, 47.00 × 10.00
- decap VDPWR 1: x 155.00, y 3.00, 10.00 × 70.00

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
