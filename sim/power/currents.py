"""Block supply currents (average, mA) for the IR-drop and EM analysis, from the measured / simulated results.

Each block's current is the worst corner's average at 27 C, 3.3 V, taken from:
- ring (VAPWR, vco.core / xmdac / vco.ref): sim/top/tile_results.md Table III, I(VAPWR) 0.69 mA at tt code 9, 0.84 mA
  at fs code 10 (the corner with the highest 433.92 MHz current); 1.07 mA at tt code 31 (the top of the range) is
  the 'ring_max' variant. Split: the ring's current returns to VGND through the DAC (xmdac), the level shifter / divider
  through the core (about 0.22 mA: P(VDD_LS) 0.72 mW, sim/tx/results/top.md), the reference about 0.05 mA (assumed).
- RX (VAPWR): sim/top/tile_results.md section 3, 7.65 mA with the ring (6.96 mA for the receiver). Split by
  docs/rx_design.md: LNA 4.89 mA tt / 5.06 mA sf (Table "LNA"), LO path 1.16 mA tt (lobuf_i, lobuf_q, lsq, Table II),
  baseband + limiter 0.371 mA per arm (Table IV), rx_bias the remainder (about 0.17 mA).
- TX driver (VDPWR): sim/top/tile_results.md Table IV, 12.49 mA avg / 12.83 mA rms tt, 14.58 / 15.01 mA ff (worst).
- tx_fine macro (VDPWR): 0.6 mA DC (docs/tx_fine_tune.md, digital supply coupling model).
"""

RING = {  # (VAPWR, VGND)
    'vco.core': (0.79, 0.24), 'xmdac': (0.0, 0.55), 'vco.ref': (0.05, 0.05),
}
RX = {
    'rx.lna': (5.06, 5.06), 'rx.lobuf_i': (0.45, 0.45), 'rx.lobuf_q': (0.45, 0.45), 'rx.lsqh': (0.26, 0.26),
    'rx.bb_i': (0.22, 0.22), 'rx.bb_q': (0.22, 0.22), 'rx.lim_i': (0.15, 0.15), 'rx.lim_q': (0.15, 0.15),
    'rx.bias': (0.17, 0.17),
}
TX = {'xtxd': 14.58}       # VDPWR and VGND
MAC = {'xmac': 0.6}        # VDPWR and VGND


def mode(name, ring_scale=1.0):
    """{net: {block: mA}} for a mode: ring (+ macro, always on), rx, tx, all."""
    cur = {'VAPWR': {}, 'VDPWR': {}, 'VGND': {}}

    def add(net, b, i):
        if i:
            cur[net][b] = cur[net].get(b, 0.0) + i
    for b, (ia, ig) in RING.items():
        add('VAPWR', b, ia * ring_scale)
        add('VGND', b, ig * ring_scale)
    for b, i in MAC.items():
        add('VDPWR', b, i)
        add('VGND', b, i)
    if name in ('rx', 'all'):
        for b, (ia, ig) in RX.items():
            add('VAPWR', b, ia)
            add('VGND', b, ig)
    if name in ('tx', 'all'):
        for b, i in TX.items():
            add('VDPWR', b, i)
            add('VGND', b, i)
    return cur


MODES = ('ring', 'rx', 'tx', 'all')
