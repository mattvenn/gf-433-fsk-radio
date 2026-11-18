#!/usr/bin/env python3
"""LVS source netlist for the Tiny Tapeout tile: lvs/tt_um_mattvenn_gf433_vco.spice.

    python3 lvs/make_source.py [--out lvs/tt_um_mattvenn_gf433_vco.spice] [--meta build/tile/meta.json]

The tile as layout/gen/tile.py builds it (docs/tile_layout.md): every block its own subcircuit, wired by
layout/gen/tile_nets.py (the same connectivity the tile generator routes), the supplies per tile_nets.SUPPLY
(VAPWR / VDPWR / VGND). Self-contained (CI needs neither xschem nor the PDK's standard-cell netlist):
  - from xschem (xschem/gen/netlist.sh, run here; needs the image): the receiver cells rx_bias, rx_lna, rx_lsq,
    rx_lobuf, rx_mix, rx_bb, rx_lim, the debug switch dbg_tg, the reference cgm_ref, the TX driver tx_drv, the
    ring + lsdiv unit vco_core, with the LVS edits of the block checks (lsdiv's "Cc a0 net1 2e-15" removed: drawn
    as M2 / M3 fingers, parasitic C; cgm_ref's XRBW r_length snapped to the 5 nm grid);
  - the VDD_LS decap decap_ls, the receiver decap rx_decap and the tile's decap unit decap_u (nfet gate caps);
  - the medium DAC mdac (layout/gen/mdac.py lvs_source()), the vctrl pull-down vctrl_pd (layout/gen/vctrl_pd.py);
  - the digital macro tx_fine (macro/tx_fine/nl/tx_fine.pnl.v through lvs/verilog2spice.py);
  - the standard cells used (inv_1, antenna, tiel, tieh and the macro's), copied from the PDK's spice;
  - the code inverters bits_inv (five inv_1 + five antenna diodes) and the tie cells;
  - the top cell with the template's ports. The decap units are counted from build/tile/meta.json (written by
    tile.py), one instance per placed unit.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'layout/gen'))
sys.path.insert(0, str(REPO / 'lvs'))
import tile_nets as TN  # noqa: E402

TOP = 'tt_um_mattvenn_gf433_vco'
SC = 'gf180mcu_fd_sc_mcu7t5v0__'
XSCH = ['rx_bias', 'rx_lna', 'rx_lsq', 'rx_lobuf', 'rx_mix', 'rx_bb', 'rx_lim', 'dbg_tg', 'cgm_ref', 'tx_drv',
        'vco_top', 'rx_top']
# floorplan instance -> cell (subcircuit name)
CELL = {'vco.core': 'vco_core', 'vco.ref': 'cgm_ref', 'vco.decap': 'decap_ls', 'xmdac': 'mdac', 'xvpd': 'vctrl_pd',
        'xbits': 'bits_inv', 'xtxd': 'tx_drv', 'xmac': 'tx_fine', 'rx.lna': 'rx_lna', 'rx.bias': 'rx_bias',
        'rx.lsq': 'rx_lsq', 'rx.lobuf_i': 'rx_lobuf', 'rx.lobuf_q': 'rx_lobuf', 'rx.mix_i': 'rx_mix',
        'rx.mix_q': 'rx_mix', 'rx.bb_i': 'rx_bb', 'rx.bb_q': 'rx_bb', 'rx.lim_i': 'rx_lim', 'rx.lim_q': 'rx_lim',
        'rx.decap': 'rx_decap', 'xdbg_bbi': 'dbg_tg', 'xdbg_bbq': 'dbg_tg', 'xdbg_nb': 'dbg_tg',
        'xdbg_vctrl': 'dbg_tg', 'xant_tx': 'ant_row2', 'xant_rx': 'ant_row1', 'xant_dbg': 'ant_row4'}


def ports():
    p = ['VGND', 'VDPWR', 'VAPWR']
    for bus in ('ui_in', 'uo_out', 'uio_in', 'uio_out', 'uio_oe', 'ua'):
        p += [f'{bus}[{i}]' for i in range(8)]
    return p + ['ena', 'clk', 'rst_n']


def subckts(text):
    """{name: (ports, text)} of every .subckt in a netlist (continuation lines joined)."""
    text = re.sub(r'\n\+', ' ', text)
    out = {}
    for m in re.finditer(r'^\.subckt (\S+)(.*?)$(.*?)^\.ends', text, re.M | re.S | re.I):
        name, pl, body = m.group(1), m.group(2).split(), m.group(3)
        out[name] = (pl, f'.subckt {name} {" ".join(pl)}{body}.ends {name}')
    return out


def lvs_edits(name, t):
    t = re.sub(r'^Cc a0 net1 2e-15\n', '', t, flags=re.M)

    def snap(m):
        v = float(m.group(2)) * 1e-6
        return f'{m.group(1)}{round(v * 1e9 / 5) * 5 / 1000:.3f}e-6'
    t = re.sub(r'^(XRBW .* r_length=)([\d.]+)(e-6)', snap, t, flags=re.M)
    t = re.sub(r'^\*\* (sch|sym)_path:.*\n', '', t, flags=re.M)
    return t


def std_cells(pdk_root, names):
    f = Path(pdk_root) / 'gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/spice/gf180mcu_fd_sc_mcu7t5v0.spice'
    t = f.read_text()
    out = []
    for c in names:
        m = re.search(rf'^\.SUBCKT {SC}{c} .*?^\.ENDS', t, flags=re.M | re.S)
        assert m, c
        out.append(m.group(0))
    return '\n\n'.join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(REPO / 'lvs' / f'{TOP}.spice'))
    ap.add_argument('--meta', default=str(REPO / 'build/tile/meta.json'))
    a = ap.parse_args()
    pdk = os.environ.get('PDK_ROOT', '/foss/pdks')
    meta = json.loads(Path(a.meta).read_text())
    d = REPO / 'build' / 'tile' / 'xsch'
    d.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, PDK_ROOT=os.environ.get('XSCHEM_PDK_ROOT', '/foss/pdks'))
    subprocess.run(['bash', 'xschem/gen/netlist.sh', 'xschem', str(d)] + XSCH, cwd=REPO, check=True, env=env,
                   stdout=subprocess.DEVNULL)
    S = {}
    sys.path.insert(0, str(REPO / 'layout/gen'))
    import vco_core
    for c in XSCH:
        t = (d / f'{c}.spice').read_text()
        if c == 'vco_top':                       # the ring + lsdiv unit, cut from vco_top (layout/gen/vco_core.py)
            t = vco_core.lvs_source(re.sub(r'\n\+', ' ', t))
        for name, (pl, txt) in subckts(lvs_edits(c, t)).items():
            if name in S:
                assert S[name][1].split('\n')[1:] == txt.split('\n')[1:] or name == 'rx_top', \
                    f'{name}: two different definitions'
                continue
            S[name] = (pl, txt)
    # the receiver decap (rx_top's DC) as its own cell
    dc = [ln for ln in S['rx_top'][1].splitlines() if ln.startswith('XDC ')]
    assert len(dc) == 1, dc
    t = dc[0].split()
    S['rx_decap'] = (['VDD', 'VSS'], '.subckt rx_decap VDD VSS\n' + ' '.join(
        ['XDC'] + [{'VDD': 'VDD', 'VSS': 'VSS'}[n] for n in t[1:5]] + t[5:]) + '\n.ends rx_decap')
    del S['rx_top']
    # VDD_LS decap and the tile's decap unit
    sys.path.insert(0, str(REPO / 'layout/gen'))
    import tile
    S['decap_u'] = (['VDD', 'VSS'], '.subckt decap_u VDD VSS\n' + f'XDC VSS VDD VSS VSS nfet_03v3 '
                    f'L={tile.DCAP_L}u W={tile.DCAP_W}u nf=1 m={tile.DCAP_NF}\n.ends decap_u')
    S['decap_ls'] = (['VDD_LS', 'VSS'], vco_core.decap_ls_source())
    # mdac, vctrl_pd
    import mdac as mdac_lay
    dsp = REPO / 'build' / 'tile' / 'mdac_src.spice'
    dac_ports = mdac_lay.lvs_source(dsp)
    S['mdac'] = (dac_ports, dsp.read_text().strip())
    import vctrl_pd as vpd_lay
    S['vctrl_pd'] = (['a', 'b'], '.subckt vctrl_pd a b\n'
                     f'XRV a b b ppolyf_u_1k r_width=1e-6 r_length={vpd_lay.rtot() / 1000:.3f}e-6\n.ends vctrl_pd')
    # the macro
    import verilog2spice as v2s
    lib = Path(pdk) / 'gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/spice/gf180mcu_fd_sc_mcu7t5v0.spice'
    mac_ports, insts, assigns = v2s.parse(REPO / 'macro/tx_fine/nl/tx_fine.pnl.v', 'tx_fine')
    cells = v2s.lib_cells(lib)
    par = {}
    for x, y in assigns:
        par[y if x in mac_ports else x] = x if x in mac_ports else y
    fnd = lambda n: fnd(par[n]) if n in par and par[n] != n else n
    mac = ['.subckt tx_fine ' + ' '.join(mac_ports)]
    used = []
    for cell, name, pins in insts:
        pins = dict(pins)
        pins.setdefault('VNW', pins.get('VDD'))
        pins.setdefault('VPW', pins.get('VSS'))
        nm = re.sub(r'[^\w]', '_', name)
        mac.append(f'X{nm} ' + ' '.join(fnd(pins[p]) if p in pins else f'nc_{nm}_{p}' for p in cells[cell][0])
                   + f' {cell}')
        used.append(cell)
    mac.append('.ends tx_fine')
    S['tx_fine'] = (mac_ports, '\n'.join(mac))
    # the code inverters: in_i -> out_i, an antenna diode on in_i
    bp = ['VDD', 'VSS'] + [f'in{i}' for i in range(5)] + [f'out{i}' for i in range(5)]
    bl = ['.subckt bits_inv ' + ' '.join(bp)]
    for i in range(5):
        bl.append(f'xinv{i} in{i} out{i} VDD VDD VSS VSS {SC}inv_1')
        bl.append(f'xant{i} in{i} VDD VDD VSS VSS {SC}antenna')
    bl.append('.ends bits_inv')
    S['bits_inv'] = (bp, '\n'.join(bl))
    for n in (1, 2, 4):                          # antenna-diode rows (tile.py ant_cell)
        ap_ = ['VDD', 'VSS'] + [f'a{k}' for k in range(n)]
        S[f'ant_row{n}'] = (ap_, f'.subckt ant_row{n} ' + ' '.join(ap_) + '\n' + '\n'.join(
            f'xa{k} a{k} VDD VDD VSS VSS {SC}antenna' for k in range(n)) + f'\n.ends ant_row{n}')

    # ---- the top cell ----
    nets = TN.nets()
    pin_net = {}                                  # (inst, pin) -> top net
    for n, ends in nets.items():
        tt = [p for i, p in ends if i == 'PIN']
        name = tt[0] if tt else n                 # a net with a TT pin takes the pin's name
        if n in TN.TIED_VSS:
            name = 'VGND'
        for e in ends:
            if e[0] != 'PIN':
                pin_net[e] = name
    pin_net[('xvpd', 'b')] = 'VGND'
    L = [f'.subckt {TOP} ' + ' '.join(ports())]
    for inst, cell in CELL.items():
        pl = S[cell][0]
        sup = TN.SUPPLY.get(inst, {})
        conn = []
        for p in pl:
            if p in sup:
                conn.append(sup[p])
            elif (inst, p) in pin_net:
                conn.append(pin_net[(inst, p)])
            else:
                conn.append(f'nc_{inst.replace(".", "_")}_{p}'.replace('[', '_').replace(']', ''))
        L.append(f'x{inst.replace(".", "_")} ' + ' '.join(conn) + f' {cell}')
    k = 0
    for sup, n in meta.get('decap_runs', []):
        for _ in range(n):
            L.append(f'xdcu{k} {sup} VGND decap_u')
            k += 1
    for n in TN.TIE_LO + TN.TIE_HI:
        tag = re.sub(r'\W', '', n.replace('[', '_'))
        cell = 'tieh' if n in TN.TIE_HI else 'tiel'
        L.append(f'xtie_{tag} {n} VAPWR VAPWR VGND VGND {SC}{cell}')
    for pin, net in TN.SUPPLY_PINS.items():         # TT pins strapped to a supply (tile.py supply_pins); the
        L.append(f'Rshort_{re.sub(r"\W", "", pin)} {net} {pin} 0')   # extraction keeps them as 0 ohm (short resistor)
    L.append('.ends')
    sc_used = list(dict.fromkeys(['inv_1', 'tiel', 'tieh', 'antenna'] + [c[len(SC):] for c in used
                                                                       if c.startswith(SC)]))
    hdr = (f'* LVS source for {TOP} (Tiny Tapeout gf180mcuD analog 2x2, VAPWR template), generated by '
           'lvs/make_source.py\n* from layout/gen/tile_nets.py, the xschem block schematics, the macro netlist and '
           'the PDK standard cells. Do not edit by hand.\n')
    body = hdr + '\n' + '\n'.join(L) + '\n\n' + '\n\n'.join(t for _, (pl, t) in sorted(S.items())) + '\n\n' \
        + std_cells(pdk, sc_used) + '\n\n.end\n'
    Path(a.out).write_text(body)
    print(f'wrote {a.out}: {sum(1 for l in body.splitlines() if l[:1] in "XxMmCcRr")} element lines, '
          f'{k} decap units')


if __name__ == '__main__':
    main()
