#!/usr/bin/env python3
"""Make a planted-bug copy of the netlist, for the eqy self-test (run.sh).
Usage: plant.py <bug> nl.v > bug.v
Each bug is one exact text edit on macro/tx_fine/nl/tx_fine.nl.v (run r250c); it must match exactly once, so a
re-harden that renames the instances makes this stop with an error until the edits are updated."""
import sys

BUGS = {
    # the SD clock gate's enable (g_sd.en): its oai21 driver becomes an aoi21
    'sd_gate_en': ('gf180mcu_fd_sc_mcu7t5v0__oai21_1 _0610_ (',
                   'gf180mcu_fd_sc_mcu7t5v0__aoi21_1 _0610_ ('),
    # the DAC decode: eff_int[3] loads eff_q[10] instead of eff_q[11]
    'eff_bit': ('_1159_ (.D(\\eff_q[11] ),', '_1159_ (.D(\\eff_q[10] ),'),
    # a reset value: eff_q[17] (set, the word 512 after reset) becomes a reset-to-0 flop
    'rst_val': ('dffsnq_1 _1192_ (.D(\\eff[17] ),\n    .SETN(net58),',
                'dffrnq_1 _1192_ (.D(\\eff[17] ),\n    .RN(net58),'),
    # clocking: a DAC-line flop (dac_tn) on the eff_q gated clock instead of the decode's
    'clk_swap': ('_1120_ (.D(_0014_),\n    .RN(net61),\n    .CLK(clknet_2_1__leaf_clk_dec),',
                 '_1120_ (.D(_0014_),\n    .RN(net61),\n    .CLK(clknet_1_1__leaf_clk_eff),'),
    # the ripple divider: stage 6 on the rising edge of stage 5 instead of the falling edge
    'ripple_edge': ('dffnrnq_1 _1108_ (.D(_0051_),\n    .RN(\\r_ck[1] ),\n    .CLKN(',
                    'dffrnq_1 _1108_ (.D(_0051_),\n    .RN(\\r_ck[1] ),\n    .CLK('),
}

bug, path = sys.argv[1], sys.argv[2]
old, new = BUGS[bug]
txt = open(path).read()
if txt.count(old) != 1:
    sys.exit(f'plant.py: {bug}: the edit matches {txt.count(old)} times in {path}')
sys.stdout.write(txt.replace(old, new))
