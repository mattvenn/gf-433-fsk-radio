"""The tile's connectivity, one source for the tile generator (layout/gen/tile.py) and its LVS source
(lvs/make_source.py): every signal net as a list of (instance, pin) ends, the TT pins as ('PIN', name), and every
instance's supply pins mapped onto VAPWR / VDPWR / VGND (docs/handoff_tile_layout.md, "Decisions").

Instance names are the floorplan's (layout/floorplan/floorplan.json `blocks[].inst`). Pin names are the cells'
own port labels. Nets inside a block are not listed.
"""

# supplies per instance: {cell supply pin: tile net}
VA = {'VDD': 'VAPWR', 'VSS': 'VGND'}
VD = {'VDD': 'VDPWR', 'VSS': 'VGND'}
SUPPLY = {
    'vco.core': {'VDD': 'VAPWR', 'VDD_LS': 'VAPWR', 'VSS': 'VGND'},
    'vco.ref': VA, 'vco.decap': {'VDD_LS': 'VAPWR', 'VSS': 'VGND'},
    'xmdac': VA, 'xvpd': {'b': 'VGND'}, 'xbits': VA,
    'xtxd': VD, 'xmac': VD, 'xties': VD,
    'xant_tx': VA, 'xant_rx': VA, 'xant_dbg': VA,
    'xdbg_bbi': VA, 'xdbg_bbq': VA, 'xdbg_nb': VA, 'xdbg_vctrl': VA,
    'rx.lna': VA, 'rx.bias': VA, 'rx.lsq': dict(VA, qenb='VGND'),   # qenb tied to VSS (open review item)
    'rx.lobuf_i': VA, 'rx.lobuf_q': VA, 'rx.mix_i': VA, 'rx.mix_q': VA,
    'rx.bb_i': VA, 'rx.bb_q': VA, 'rx.lim_i': VA, 'rx.lim_q': VA, 'rx.decap': VA,
}

# the macro's TT-pin connections and its DAC lines
MAC_TT = {'clk': 'clk', 'rst_n': 'rst_n', 'sclk': 'uio_in[0]', 'mosi': 'uio_in[1]', 'cs_n': 'uio_in[2]',
          'miso': 'uio_out[3]', 'fsk': 'ui_in[7]', 'ck_o': 'uo_out[0]', 'div16': 'uo_out[1]',
          'div64': 'uo_out[2]', 'div1024': 'uo_out[3]'}


def dac_pairs():
    """(macro pin, mdac pin) for the 37 DAC control lines: dac_tn[i] -> ns(i+1), dac_bn[b] -> nb(b), dac_sdn -> nsd."""
    return ([(f'dac_tn[{i}]', f'ns{i + 1}') for i in range(31)] + [(f'dac_bn[{b}]', f'nb{b}') for b in range(5)]
            + [('dac_sdn', 'nsd')])


# TT outputs held constant: uio_oe[3] = 1 (MISO drives), every other unused output 0
TIE_HI = ['uio_oe[3]']
TIE_LO = ([f'uo_out[{i}]' for i in (6, 7)] + [f'uio_out[{i}]' for i in (0, 1, 2, 4, 5, 6, 7)]
          + [f'uio_oe[{i}]' for i in (0, 1, 2, 4, 5, 6, 7)])

DBG = [('xdbg_bbi', 'oi_p', 0), ('xdbg_bbq', 'oq_p', 1), ('xdbg_nb', 'nb', 2), ('xdbg_vctrl', 'vctrl', 3)]


def nets():
    n = {
        # RF in, TX out
        'rx_inp': [('PIN', 'ua[4]'), ('rx.lna', 'inp')],
        'rx_inn': [('PIN', 'ua[5]'), ('rx.lna', 'inn')],
        'tx_outp': [('xtxd', 'out_p'), ('PIN', 'ua[3]')],
        'tx_outn': [('xtxd', 'out_n'), ('PIN', 'ua[2]')],
        # LO
        'ls': [('vco.core', 'ls'), ('xtxd', 'ls'), ('rx.lobuf_i', 'in')],
        'a2': [('vco.core', 'a2'), ('rx.lsq', 'aq')],
        'lsq': [('rx.lsq', 'lsq'), ('rx.lobuf_q', 'in')],
        # VCO bias, fine tuning
        'vg': [('xmdac', 'vg'), ('vco.core', 'vg')],
        'vbnf': [('vco.ref', 'vbnf'), ('vco.core', 'vbnf'), ('xmdac', 'vbnf')],
        'vctrl': [('vco.core', 'vctrl'), ('vco.ref', 'vctrl'), ('xvpd', 'a')],     # cgm_ref: one pin (feed-through)
        'ck': [('vco.core', 'ck'), ('xmac', 'ck')],
        # TX enables
        'en_p': [('PIN', 'ui_in[5]'), ('xtxd', 'en_p'), ('xant_tx', 'a0')],
        'en_n': [('PIN', 'ui_in[6]'), ('xtxd', 'en_n'), ('xant_tx', 'a1')],
        # receiver control and outputs
        'rx_en': [('xmac', 'rx_en'), ('rx.bias', 'en'), ('rx.lobuf_i', 'en'), ('rx.lobuf_q', 'en')],
        'q_i': [('rx.lim_i', 'q'), ('PIN', 'uo_out[4]')],
        'q_q': [('rx.lim_q', 'q'), ('PIN', 'uo_out[5]')],
        # inside the receiver (layout/gen/rx_top.py's nets)
        'ri_p': [('rx.lna', 'oip'), ('rx.mix_i', 'rfp')], 'ri_n': [('rx.lna', 'oin'), ('rx.mix_i', 'rfn')],
        'rq_p': [('rx.lna', 'oqp'), ('rx.mix_q', 'rfp')], 'rq_n': [('rx.lna', 'oqn'), ('rx.mix_q', 'rfn')],
        'lo_i': [('rx.lobuf_i', 'lo'), ('rx.mix_i', 'lo')], 'lob_i': [('rx.lobuf_i', 'lob'), ('rx.mix_i', 'lob')],
        'lo_q': [('rx.lobuf_q', 'lo'), ('rx.mix_q', 'lo')], 'lob_q': [('rx.lobuf_q', 'lob'), ('rx.mix_q', 'lob')],
        'bi_p': [('rx.mix_i', 'bbp'), ('rx.bb_i', 'inp')], 'bi_n': [('rx.mix_i', 'bbn'), ('rx.bb_i', 'inn')],
        'bq_p': [('rx.mix_q', 'bbp'), ('rx.bb_q', 'inp')], 'bq_n': [('rx.mix_q', 'bbn'), ('rx.bb_q', 'inn')],
        'oi_p': [('rx.bb_i', 'outp'), ('rx.lim_i', 'inp')], 'oi_n': [('rx.bb_i', 'outn'), ('rx.lim_i', 'inn')],
        'oq_p': [('rx.bb_q', 'outp'), ('rx.lim_q', 'inp')], 'oq_n': [('rx.bb_q', 'outn'), ('rx.lim_q', 'inn')],
        'nb': [('rx.bias', 'nb'), ('rx.lna', 'nb'), ('rx.bb_i', 'nb'), ('rx.bb_q', 'nb'), ('rx.lim_i', 'nb'),
               ('rx.lim_q', 'nb')],
        'enb': [('rx.bias', 'enb'), ('rx.lna', 'enb'), ('rx.bb_i', 'enb'), ('rx.bb_q', 'enb'), ('rx.lim_i', 'enb'),
                ('rx.lim_q', 'enb'), ('xant_rx', 'a0')],
        # debug mux
        'dbg_bus': [(inst, 'bus') for inst, _, _ in DBG] + [('PIN', 'ua[0]')],
    }
    for inst, src, k in DBG:
        n[src].append((inst, 'mod'))
        n[f'dbg_sel[{k}]'] = [('xmac', f'dbg_sel[{k}]'), (inst, 'ctrl'), ('xant_dbg', f'a{k}')]
    for mp, tp in MAC_TT.items():
        n[f'mac_{mp}'] = [('PIN', tp), ('xmac', mp)]
    for mp, dp in dac_pairs():
        n[mp] = [('xmac', mp), ('xmdac', dp)]
    # coarse code: ui_in[i] -> bit i (the ring's DAC) and the inverter input; the inverter output -> bitb i
    for i in range(5):
        n[f'bit{i}'] = [('PIN', f'ui_in[{i}]'), ('xbits', f'in{i}'), ('vco.core', f'bit{i}')]
        n[f'bitb{i}'] = [('xbits', f'out{i}'), ('vco.core', f'bitb{i}')]
    return n


TIED_VSS = {'qenb'}

# TT pins strapped straight to a supply stripe (tile.py supply_pins): the precheck's analog pin check wants
# ua[0]..ua[analog_pins - 1] all connected, so the spare ua[1] is an on-chip ground sense (a Kelvin reference for
# the readings on ua[0]) on the VGND stripe above it
SUPPLY_PINS = {'ua[1]': 'VGND'}

# nets that may run on Metal4 over the receiver's cells (rule 6 of docs/floorplan_spec.md bans clocks, digital,
# enables, LO, the debug bus and the limiter outputs there; these are the receiver's own analog nets)
RX_M4_OK = {'rx_inp', 'rx_inn', 'ri_p', 'ri_n', 'rq_p', 'rq_n', 'bi_p', 'bi_n', 'bq_p', 'bq_n', 'oi_p', 'oi_n', 'oq_p',
            'oq_n', 'nb'}
# guarded nets: VGND shield wires on the free tracks beside them (the handoff: the baseband -> limiter pairs, and
# vbnf / vctrl from cgm_ref to the ring); KEEP_AWAY: aggressors that pay to come near the guarded ones
SHIELDED = {'vbnf', 'vctrl', 'oi_p', 'oi_n', 'oq_p', 'oq_n'}
KEEP_AWAY = {'ck': ['vbnf', 'vctrl'], 'q_i': ['oi_p', 'oi_n', 'oq_p', 'oq_n'], 'q_q': ['oi_p', 'oi_n', 'oq_p', 'oq_n']}
# nets with an antenna diode (KLayout ANT.16 / ANT.4: long wires into small gates) stay off Metal4, so the diode
# protects them at every metal level the antenna rules check
NO_M4_NETS = {'enb'} | {f'dbg_sel[{k}]' for k in range(4)}
# (enb carries the receiver's antenna diode, xant_rx: it stays on M2 / M3 so the diode protects it at every metal
# level KLayout's antenna rules check)           # nets tied to VGND in the tile (no other end)


def check():
    n = nets()
    seen = {}
    for net, ends in n.items():
        for e in ends:
            assert e not in seen, (e, net, seen.get(e))
            seen[e] = net
    return n


if __name__ == '__main__':
    n = check()
    print(len(n), 'nets,', sum(len(v) for v in n.values()), 'ends')
