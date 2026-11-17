#!/usr/bin/env python3
"""Pinout check: info.yaml <-> the tile's LVS source <-> the tx_fine macro (RTL, LEF, GL netlist).

PINOUT below is the one statement of what each Tiny Tapeout (TT) pin does. The script checks:
- info.yaml's pinout labels are exactly the PINOUT labels (and analog_pins / uses_vapwr / top_module agree);
- in the LVS source (lvs/tt_um_mattvenn_gf433_vco.spice, LVS-matched to the GDS) each TT pin's net has exactly
  the block ports PINOUT lists (no more, no fewer), unused inputs and ena are unconnected, unused outputs are tied
  low, and uio_oe[i] is tied high exactly on the uio pins PINOUT marks 'out';
- the nets between the macro and the analog blocks (INTERNAL): ck, rx_en, dbg_sel[3:0], the 37 DAC lines and the
  code inverters, with the macro's supplies on VDPWR / VGND;
- the macro's pins are the same in the RTL (src/tx_fine.v), the LEF, the GL netlist (nl.v) and the LVS
  source's tx_fine subcircuit, with the LEF directions equal to the RTL's.

    python3 tools/check_pinout.py                  the check (exit 1 on any error)
    python3 tools/check_pinout.py --verilog OUT    also write the TT-level wrapper for test/ (written even when
                                                   the check fails; --no-fail then exits 0)
    python3 tools/check_pinout.py --spice F --info F   check other copies (the mutation tests use this)

docs/verification_digital.md, "Pinout check".
"""
import argparse
import os
import re
import sys

import yaml

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
TOP = 'tt_um_mattvenn_gf433_vco'
SPICE = os.path.join(REPO, f'lvs/{TOP}.spice')
INFO = os.path.join(REPO, 'info.yaml')
RTL = os.path.join(REPO, 'src/tx_fine.v')
LEF = os.path.join(REPO, 'macro/tx_fine/lef/tx_fine.lef')
NL = os.path.join(REPO, 'macro/tx_fine/nl/tx_fine.nl.v')
MAC = 'xxmac'          # the tx_fine instance in the LVS source
DBG = [('xxdbg_bbi', 'baseband I'), ('xxdbg_bbq', 'baseband Q'), ('xxdbg_nb', 'bias nb'), ('xxdbg_vctrl', 'vctrl')]

# TT pin -> (info.yaml label, [(instance, port), ...] on that pin's net). 'TIE0' / 'TIE1': tied low / high by a
# tie cell. ('VGND',) as the only end: the pin is shorted to VGND on chip.
PINOUT = {
    **{f'ui_in[{i}]': (f'code bit {i}', [('xvco_core', f'bit{i}'), ('xxbits', f'in{i}')]) for i in range(5)},
    'ui_in[5]': ('TX enable p (out_p, ua[3])', [('xxtxd', 'en_p'), ('xxant_tx', 'a0')]),
    'ui_in[6]': ('TX enable n (out_n, ua[2])', [('xxtxd', 'en_n'), ('xxant_tx', 'a1')]),
    'ui_in[7]': ('FSK data (2-FSK: +/- the FSK_DEV register)', [(MAC, 'fsk')]),

    'uo_out[0]': ('ck: f / 4 (gated, off after reset: CTRL.CK_EN)', [(MAC, 'ck_o')]),
    'uo_out[1]': ('f / 16 (27 MHz)', [(MAC, 'div16')]),
    'uo_out[2]': ('f / 64 (6.8 MHz)', [(MAC, 'div64')]),
    'uo_out[3]': ('f / 1024 (424 kHz)', [(MAC, 'div1024')]),
    'uo_out[4]': ('RX q_i: in-phase limiter output (CTRL.RX_EN)', [('xrx_lim_i', 'q')]),
    'uo_out[5]': ('RX q_q: quadrature limiter output', [('xrx_lim_q', 'q')]),
    'uo_out[6]': ('', 'TIE0'),
    'uo_out[7]': ('', 'TIE0'),

    'uio_in[0]': ('SPI SCLK (in)', [(MAC, 'sclk')]),
    'uio_in[1]': ('SPI MOSI (in)', [(MAC, 'mosi')]),
    'uio_in[2]': ('SPI CS_n (in)', [(MAC, 'cs_n')]),
    'uio_out[3]': ('SPI MISO (out)', [(MAC, 'miso')]),

    'ua[0]': ('debug mux (DBG_SEL, one at a time): [0] RX baseband I, [1] RX baseband Q, [2] RX bias nb, '
              '[3] vctrl (also the bench override of the fine leg; 200 kOhm to GND on chip)',
              [(inst, 'bus') for inst, _ in DBG]),
    'ua[1]': ('on-chip ground sense (VGND): the Kelvin reference for readings on ua[0]; do not drive', ('VGND',)),
    'ua[2]': ('TX out_n: 433 MHz dipole arm (antiphase to ua[3])', [('xxtxd', 'out_n')]),
    'ua[3]': ('TX out_p: 433 MHz dipole arm', [('xxtxd', 'out_p')]),
    'ua[4]': ('RX in_p: 433 MHz receive dipole arm', [('xrx_lna', 'inp')]),
    'ua[5]': ('RX in_n: 433 MHz receive dipole arm', [('xrx_lna', 'inn')]),
    'clk': (None, [(MAC, 'clk')]),
    'rst_n': (None, [(MAC, 'rst_n')]),
    'ena': (None, []),            # not used: the design runs whenever it is powered
    'ua[6]': (None, []), 'ua[7]': (None, []),   # analog_pins = 6: no pads
}
# uio: direction per pin; the 'in' pins' uio_out are tied low, uio_oe[i] = 1 exactly on the 'out' pins
UIO_DIR = ['in', 'in', 'in', 'out', 'unused', 'unused', 'unused', 'unused']
UIO_LABEL = {i: '' for i in range(4, 8)}
for i in range(8):
    if f'uio_in[{i}]' not in PINOUT:
        PINOUT[f'uio_in[{i}]'] = (UIO_LABEL.get(i), [])
    if f'uio_out[{i}]' not in PINOUT:
        PINOUT[f'uio_out[{i}]'] = (None, 'TIE0')
    PINOUT[f'uio_oe[{i}]'] = (None, 'TIE1' if UIO_DIR[i] == 'out' else 'TIE0')
UIO_OE = sum(1 << i for i, d in enumerate(UIO_DIR) if d == 'out')   # uio_oe value (test/ checks it in sim)

# nets between the macro and the analog blocks: net -> exact ends ('exact') or ends that must be among them
INTERNAL = {
    'ck': ('exact', [('xvco_core', 'ck'), (MAC, 'ck')]),
    'rx_en': ('exact', [(MAC, 'rx_en'), ('xrx_bias', 'en'), ('xrx_lobuf_i', 'en'), ('xrx_lobuf_q', 'en')]),
    **{f'dbg_sel[{k}]': ('exact', [(MAC, f'dbg_sel[{k}]'), (inst, 'ctrl'), ('xxant_dbg', f'a{k}')])
       for k, (inst, _) in enumerate(DBG)},
    # the debug switches' other side: the source each one puts on ua[0]
    'oi_p': ('has', [('xrx_bb_i', 'outp'), ('xxdbg_bbi', 'mod')]),
    'oq_p': ('has', [('xrx_bb_q', 'outp'), ('xxdbg_bbq', 'mod')]),
    'nb': ('has', [('xrx_bias', 'nb'), ('xxdbg_nb', 'mod')]),
    'vctrl': ('exact', [('xvco_core', 'vctrl'), ('xxvpd', 'a'), ('xxdbg_vctrl', 'mod')]),
    **{f'dac_tn[{i}]': ('exact', [(MAC, f'dac_tn[{i}]'), ('xxmdac', f'ns{i + 1}')]) for i in range(31)},
    **{f'dac_bn[{b}]': ('exact', [(MAC, f'dac_bn[{b}]'), ('xxmdac', f'nb{b}')]) for b in range(5)},
    'dac_sdn': ('exact', [(MAC, 'dac_sdn'), ('xxmdac', 'nsd')]),
    **{f'bitb{i}': ('exact', [('xxbits', f'out{i}'), ('xvco_core', f'bitb{i}')]) for i in range(5)},
}
MAC_SUPPLY = {'VDD': 'VDPWR', 'VSS': 'VGND'}


# ---------------------------------------------------------------- parsers
def parse_spice(path):
    """-> (subckts {name: [ports]}, top instances [(inst, cell, [nets])], top ports)."""
    lines = []
    for raw in open(path):
        raw = raw.rstrip('\n')
        if raw.startswith('+') and lines:
            lines[-1] += ' ' + raw[1:]
        else:
            lines.append(raw)
    subckts, insts, cur, top_ports = {}, [], None, None
    for ln in lines:
        t = ln.split()
        if not t or t[0].startswith('*'):
            continue
        k = t[0].lower()
        if k == '.subckt':
            cur = t[1]
            subckts[cur] = [p for p in t[2:] if '=' not in p]
            if cur == TOP:
                top_ports = subckts[cur]
        elif k == '.ends':
            cur = None
        elif cur == TOP:
            toks = [x for x in t if '=' not in x]
            if k[0] == 'x':
                insts.append((t[0], toks[-1], toks[1:-1]))
            else:                                   # R / C / V ... : two nodes, then the value / model
                insts.append((t[0], t[0][0].upper(), toks[1:3]))
    return subckts, insts, top_ports


def net_ends(subckts, insts):
    """{net: [(inst, port)]}; primitive elements get ports '1', '2'."""
    ends = {}
    for inst, cell, nets in insts:
        ports = subckts.get(cell, [str(i + 1) for i in range(len(nets))])
        if len(ports) != len(nets):
            raise SystemExit(f'{inst}: {len(nets)} nets for {cell}\'s {len(ports)} ports')
        for p, n in zip(ports, nets):
            ends.setdefault(n, []).append((inst, p))
    return ends


def bits(name, msb=None, lsb=None):
    if msb is None:
        return [name]
    step = -1 if msb >= lsb else 1
    return [f'{name}[{i}]' for i in range(msb, lsb + step, step)]


def rtl_ports(path, module='tx_fine'):
    """{bit: 'input' | 'output'} from an ANSI or non-ANSI module header."""
    src = re.sub(r'//.*', '', open(path).read())
    src = re.sub(r'/\*.*?\*/', '', src, flags=re.S)
    m = re.search(r'\bmodule\s+' + module + r'\b(.*?)\bendmodule', src, re.S)
    body = re.sub(r'\bfunction\b.*?\bendfunction\b', '', m.group(1), flags=re.S)
    body = re.sub(r'\btask\b.*?\bendtask\b', '', body, flags=re.S)
    out = {}
    for d, w, names in re.findall(r'\b(input|output|inout)\s+(?:wire|reg)?\s*(\[\s*\d+\s*:\s*\d+\s*\])?\s*'
                                  r'([A-Za-z_][\w\s,]*?)(?=[;)]|\b(?:input|output|inout)\b)', body):
        msb = lsb = None
        if w:
            msb, lsb = map(int, re.findall(r'\d+', w))
        for n in [x.strip() for x in names.split(',') if x.strip()]:
            for b in bits(n, msb, lsb):
                out[b] = d
    return out


def lef_pins(path):
    pins, cur = {}, None
    for ln in open(path):
        t = ln.split()
        if len(t) >= 2 and t[0] == 'PIN':
            cur = t[1]
        elif cur and t[:1] == ['DIRECTION']:
            pins[cur] = t[1].lower()
        elif cur and t[:1] == ['END'] and len(t) > 1 and t[1] == cur:
            cur = None
    return pins


# ---------------------------------------------------------------- checks
def check(spice=SPICE, info=INFO):
    errs, notes = [], []
    subckts, insts, top_ports = parse_spice(spice)
    ends = net_ends(subckts, insts)
    cell_of = {i: c for i, c, _ in insts}
    srt = lambda e: sorted(e)  # noqa: E731

    # ---- info.yaml
    y = yaml.safe_load(open(info))
    pin_yaml = y['pinout']
    for tt, (label, _) in PINOUT.items():
        if label is None:
            continue
        m = re.match(r'(ui_in|uo_out|uio_in|uio_out|ua)\[(\d)\]', tt)
        key = {'ui_in': 'ui', 'uo_out': 'uo', 'uio_in': 'uio', 'uio_out': 'uio', 'ua': 'ua'}[m.group(1)] \
            + f'[{m.group(2)}]'
        if (pin_yaml.get(key) or '') != label:
            errs.append(f'info.yaml {key}: "{pin_yaml.get(key)}", PINOUT says "{label}"')
    used_ua = [i for i in range(8) if PINOUT[f'ua[{i}]'][1]]
    if y['project'].get('analog_pins') != max(used_ua) + 1:
        errs.append(f'info.yaml analog_pins = {y["project"].get("analog_pins")}, PINOUT uses ua[0..{max(used_ua)}]')
    if y['project'].get('top_module') != TOP:
        errs.append(f'info.yaml top_module = {y["project"].get("top_module")}')
    if not y['project'].get('uses_vapwr') and 'VAPWR' in ends:
        errs.append('info.yaml uses_vapwr is false but the tile uses VAPWR')

    # ---- TT pins in the LVS source
    for tt, (_, want) in PINOUT.items():
        if tt not in top_ports:
            errs.append(f'{tt}: not a port of {TOP} in the LVS source')
            continue
        got = srt(ends.get(tt, []))
        if want in ('TIE0', 'TIE1'):
            ties = [(i, cell_of[i]) for i, p in got if 'tie' in cell_of[i]]
            v = {('tieh' in c) for _, c in ties}
            ok = len(got) == 1 and len(ties) == 1 and v == {want == 'TIE1'}
            if not ok:
                errs.append(f'{tt}: expected tied {want[-1]}, LVS source has {got} ({[c for _, c in ties]})')
            continue
        if want == ('VGND',):
            shorts = [i for i, p in got if cell_of[i] in ('R', 'V') or len(subckts.get(cell_of[i], [])) == 2]
            gnd = [i for i in shorts if any(i == j for j, _ in ends.get('VGND', []))]
            if not got:
                errs.append(f'{tt}: PINOUT says it is the on-chip VGND sense, but the LVS source leaves it '
                            f'unconnected (lvs/make_source.py / layout/gen/tile_nets.py need the short to VGND)')
            elif not gnd:
                errs.append(f'{tt}: expected a short to VGND, LVS source has {got}')
            else:
                notes.append(f'{tt}: shorted to VGND by {gnd} ({[cell_of[i] for i in gnd]})')
            continue
        if got != srt(want):
            errs.append(f'{tt}: LVS source has {got}, PINOUT expects {srt(want)}')

    # ---- macro <-> analog nets
    for net, (mode, want) in INTERNAL.items():
        got = srt(ends.get(net, []))
        if mode == 'exact' and got != srt(want):
            errs.append(f'net {net}: LVS source has {got}, expected {srt(want)}')
        if mode == 'has' and not set(want) <= set(got):
            errs.append(f'net {net}: missing {sorted(set(want) - set(got))} (has {got})')
    for p, n in MAC_SUPPLY.items():
        if (MAC, p) not in ends.get(n, []):
            errs.append(f'{MAC}.{p} is not on {n}')
    # every macro signal port is accounted for by PINOUT or INTERNAL
    mac_nets = {p: n for n, es in ends.items() for i, p in es if i == MAC}
    known = {e for _, w in PINOUT.values() if isinstance(w, list) for e in w} \
        | {e for _, w in INTERNAL.values() for e in w}
    for p, n in sorted(mac_nets.items()):
        if p not in MAC_SUPPLY and (MAC, p) not in known:
            errs.append(f'{MAC}.{p} on net {n}: not described by PINOUT / INTERNAL')

    # ---- the macro's pins: RTL, LEF, GL netlist, LVS subcircuit
    rtl = rtl_ports(RTL)
    lef = lef_pins(LEF)
    nl = rtl_ports(NL)
    sub = [p for p in subckts.get('tx_fine', []) if p not in MAC_SUPPLY]
    lef_sig = {p: d for p, d in lef.items() if p not in MAC_SUPPLY}
    for name, s in (('LEF', set(lef_sig)), ('GL netlist', set(nl)), ('LVS tx_fine subckt', set(sub))):
        if s != set(rtl):
            errs.append(f'tx_fine pins: {name} differs from the RTL: only in {name} {sorted(s - set(rtl))}, '
                        f'only in RTL {sorted(set(rtl) - s)}')
    for p, d in rtl.items():
        if p in lef_sig and lef_sig[p] != d:
            errs.append(f'tx_fine {p}: RTL {d}, LEF {lef_sig[p]}')
        if p in nl and nl[p] != d:
            errs.append(f'tx_fine {p}: RTL {d}, GL netlist {nl[p]}')
    if set(lef) - set(lef_sig) != set(MAC_SUPPLY):
        errs.append(f'tx_fine LEF supply pins {sorted(set(lef) - set(lef_sig))}, expected {sorted(MAC_SUPPLY)}')
    notes.append(f'tx_fine: {len(rtl)} signal pins, the same in RTL, LEF, GL netlist and LVS subcircuit'
                 if not any(e.startswith('tx_fine') for e in errs) else 'tx_fine: pin lists differ')
    return errs, notes, (subckts, insts, top_ports, ends)


# ---------------------------------------------------------------- Verilog wrapper for test/
def vname(net, top_ports):
    if net in top_ports and re.match(r'(ui_in|uo_out|uio_in|uio_out|uio_oe|ua)\[\d\]$', net):
        return net                                  # a bit of a TT port
    if net in ('clk', 'rst_n', 'ena'):
        return net
    if re.match(r'^[A-Za-z_]\w*$', net):
        return net
    return '\\' + net + ' '                         # escaped identifier: dac_tn[3] -> \dac_tn[3]


def write_verilog(out, parsed):
    """The tile as Verilog: tx_fine (RTL or GL) plus every analog block as a behavioural stub from
    test/stubs.v, wired exactly as the LVS source. Tie cells become constant assigns, decap units are dropped."""
    subckts, insts, top_ports, ends = parsed
    L = ['// GENERATED by tools/check_pinout.py --verilog from lvs/tt_um_mattvenn_gf433_vco.spice: do not edit.',
         '// The tile as Verilog for the TT-level cocotb tests (test/): tx_fine as RTL or the GL netlist, the analog',
         '// blocks as behavioural stubs (test/stubs.v), wired as the LVS source (which is LVS-matched to the GDS).',
         '`default_nettype none', '',
         f'module {TOP} (',
         '    input  wire [7:0] ui_in, output wire [7:0] uo_out,',
         '    input  wire [7:0] uio_in, output wire [7:0] uio_out, output wire [7:0] uio_oe,',
         '    inout  wire [7:0] ua,',
         '    input  wire ena, input wire clk, input wire rst_n',
         ');',
         '    wire VDPWR = 1\'b1, VAPWR = 1\'b1, VGND = 1\'b0;']
    internal = sorted({n for n in ends if n not in top_ports})
    for n in internal:
        L.append(f'    wire {vname(n, top_ports)};')
    for inst, cell, nets in insts:
        if cell.startswith('gf180mcu_fd_sc_mcu7t5v0__tie'):
            v = "1'b1" if cell.endswith('tieh') else "1'b0"
            L.append(f'    assign {vname(nets[0], top_ports)} = {v};    // {inst} ({cell[25:]})')
            continue
        if cell in ('decap_u',):
            continue
        if cell in ('R', 'V'):                      # a short (e.g. ua[1] to VGND): not modelled
            L.append(f'    // {inst}: {cell} between {nets[0]} and {nets[1]} (not modelled)')
            continue
        ports = subckts[cell]
        conn = []
        for p, n in zip(ports, nets):
            if cell == 'tx_fine' and p in MAC_SUPPLY:
                continue
            pv = p if re.match(r'^[A-Za-z_]\w*$', p) else '\\' + p + ' '
            if cell == 'tx_fine' and '[' in p:     # bus bits of the macro: connect as a concatenation below
                continue
            conn.append(f'.{pv}({vname(n, top_ports)})')
        if cell == 'tx_fine':
            pm = dict(zip(ports, nets))
            for bus, w in (('dac_tn', 31), ('dac_bn', 5), ('dbg_sel', 4)):
                conn.append(f'.{bus}({{' + ', '.join(vname(pm[f"{bus}[{i}]"], top_ports)
                                                     for i in range(w - 1, -1, -1)) + '})')
        L.append(f'    {cell} {inst} (' + ', '.join(conn) + ');')
    L.append('endmodule')
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, 'w') as f:
        f.write('\n'.join(L) + '\n')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--spice', default=SPICE)
    ap.add_argument('--info', default=INFO)
    ap.add_argument('--verilog', help='write the TT-level wrapper here')
    ap.add_argument('--no-fail', action='store_true', help='exit 0 even when the check fails')
    a = ap.parse_args()
    errs, notes, parsed = check(a.spice, a.info)
    for n in notes:
        print('  ' + n)
    for e in errs:
        print('ERROR: ' + e)
    print(f'pinout: {"OK" if not errs else "FAIL"} ({len(errs)} errors; uio_oe = 0x{UIO_OE:02x})')
    if a.verilog:
        write_verilog(a.verilog, parsed)
        print(f'wrote {a.verilog}')
    sys.exit(0 if (not errs or a.no_fail) else 1)


if __name__ == '__main__':
    main()
