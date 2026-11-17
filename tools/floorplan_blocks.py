"""Write layout/floorplan/blocks.json for the floorplan page: every block's bbox (um, origin moved to the bbox's
lower-left corner), its pin labels, and its Metal4 shapes as merged boxes (a full-height Metal4 power stripe can't
cross them).

    python3 tools/floorplan_blocks.py          (needs the klayout module: pip install klayout)

Blocks: the tile's blocks (vco_top, mdac, vctrl_pd, tx_drv, the digital macro tx_fine), the receiver as one block
(rx_top) and as its cells (rx_lna, rx_bias, rx_lsq, rx_lobuf, rx_mix, rx_bb, rx_lim, and rx_decap, which exists only
inside rx_top.gds). rx_top also gets `inst`: where each cell sits inside it, so the page can show the receiver's
cells as rx_top has them, or the LNA zone inside the rx_top block.

gf180mcuD layers: Metal1 34, Metal2 36, Metal3 42, Metal4 46; labels are text on datatype 10. Only the top cell's
own labels count (not the subcells'). A name labelled twice keeps the first label found on the lowest metal; the
receiver cells' power labels (VDD / VSS) are kept but the page draws them grey.
"""
import json
import os

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
LAYERS = {34: 'Metal1', 36: 'Metal2', 42: 'Metal3', 46: 'Metal4'}
LABEL_DT = 10
M4 = (46, 0)
GDS = {
    'vco_top': 'layout/vco_top.gds', 'mdac': 'layout/mdac.gds', 'vctrl_pd': 'layout/vctrl_pd.gds',
    'tx_drv': 'layout/tx_drv.gds', 'tx_fine': 'macro/tx_fine/gds/tx_fine.gds', 'rx_top': 'layout/rx_top.gds',
    'rx_lna': 'layout/rx_lna.gds', 'rx_bias': 'layout/rx_bias.gds', 'rx_lsq': 'layout/rx_lsq.gds',
    'rx_lobuf': 'layout/rx_lobuf.gds', 'rx_mix': 'layout/rx_mix.gds', 'rx_bb': 'layout/rx_bb.gds',
    'rx_lim': 'layout/rx_lim.gds', 'rx_decap': ('layout/rx_top.gds', 'rx_decap'),
}
# the tile's own cells (docs/handoff_tile_layout.md step 2): vco_top split into the ring + lsdiv unit, cgm_ref and the
# VDD_LS decap; the debug switch. Read when their GDS exists.
for _k, _g in (('vco_core', 'layout/vco_core.gds'), ('cgm_ref', 'layout/cgm_ref.gds'), ('decap_ls', 'layout/decap_ls.gds'),
               ('dbg_tg', 'layout/dbg_tg.gds')):
    if os.path.exists(os.path.join(ROOT, _g)):
        GDS[_k] = _g
# Tiny Tapeout's 5 V analog switch (github.com/TinyTapeout/tt-multiplexer, asw/gf180mcuD/tt_asw_5v0), for the debug
# mux: read from a clone next to this repo (TT_MUX=<path> to point elsewhere); skipped when it is not there.
TT_MUX = os.environ.get('TT_MUX', os.path.join(ROOT, '..', 'tt-multiplexer'))
ASW = os.path.join(TT_MUX, 'asw', 'gf180mcuD', 'tt_asw_5v0', 'gds', 'tt_asw_5v0.gds')


def block(path, cellname=None):
    import klayout.db as kdb
    ly = kdb.Layout()
    ly.read(os.path.join(ROOT, path))
    top = ly.cell(cellname) if cellname else ly.top_cell()
    b = top.dbbox()
    pins = {}
    for ln in sorted(LAYERS):
        li = ly.find_layer(ln, LABEL_DT)
        if li is None:
            continue
        for sh in top.shapes(li).each():
            if sh.is_text() and sh.text_string not in pins:
                p = sh.text_dpos
                pins[sh.text_string] = {'layer': LAYERS[ln], 'x': round(p.x - b.left, 2), 'y': round(p.y - b.bottom, 2)}
    m4 = []
    li = ly.find_layer(*M4)
    if li is not None:
        s = ly.dbu
        reg = kdb.Region(top.begin_shapes_rec(li)).merged()
        m4 = sorted([round(r.left * s - b.left, 2), round(r.bottom * s - b.bottom, 2), round(r.width() * s, 2),
                     round(r.height() * s, 2)] for r in (p.bbox() for p in reg.each()))
    out = {'w': round(b.width(), 3), 'h': round(b.height(), 3), 'origin': [round(b.left, 3), round(b.bottom, 3)], 'pins': pins,
           'm4': m4, 'gds': path}
    if cellname is None and top.name == 'rx_top':
        out['inst'] = []
        for i in top.each_inst():
            ib = i.dbbox()
            out['inst'].append({'cell': i.cell.name, 'x': round(ib.left - b.left, 2), 'y': round(ib.bottom - b.bottom, 2),
                                'w': round(ib.width(), 3), 'h': round(ib.height(), 3), 'trans': str(i.dcplx_trans)})
    return out


def main():
    out = {}
    for k, g in GDS.items():
        out[k] = block(*g) if isinstance(g, tuple) else block(g)
    if os.path.exists(ASW):
        a = block(os.path.relpath(ASW, ROOT))
        # its pins from the LEF (the GDS labels are on its subcells): mod / bus Metal4, ctrl Metal3, all on the top half
        a['pins'] = {'mod': {'layer': 'Metal4', 'x': 20.16, 'y': 28.75}, 'bus': {'layer': 'Metal4', 'x': 20.16, 'y': 14.25},
                     'ctrl': {'layer': 'Metal3', 'x': 3.79, 'y': 29.75}}
        a['straps'] = [{'net': 'VDPWR', 'x': 1.5, 'w': 0.8}, {'net': 'VGND', 'x': 2.6, 'w': 0.8}, {'net': 'VAPWR', 'x': 3.7, 'w': 0.8}]
        a['gds'] = 'tt-multiplexer: asw/gf180mcuD/tt_asw_5v0/gds/tt_asw_5v0.gds'
        out['tt_asw_5v0'] = a
    # the digital macro's Metal4 power straps (the only Metal4 a tile stripe may run on over the macro)
    t = out['tx_fine']
    # (from its LEF: which strap is which net; the GDS boxes don't say)
    import re
    lef = open(os.path.join(ROOT, 'macro/tx_fine/lef/tx_fine.lef')).read()
    t['straps'] = []
    for net in ('VDD', 'VSS'):
        body = re.search(rf'PIN {net}(.*?)END {net}', lef, re.S).group(1)
        for r in re.findall(r'LAYER Metal4 ;\s*RECT (\S+) (\S+) (\S+) (\S+)', body):
            x0, y0, x1, y1 = map(float, r)
            if y1 - y0 > 0.6 * t['h']:
                t['straps'].append({'net': net, 'x': round(x0, 2), 'w': round(x1 - x0, 2)})
    t['straps'].sort(key=lambda d: d['x'])
    d = os.path.join(ROOT, 'layout', 'floorplan')
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, 'blocks.json'), 'w') as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    for k, v in out.items():
        print(f"{k:9s} {v['w']:6.2f} x {v['h']:6.2f}  m4 {len(v['m4']):3d}  {' '.join(sorted(v['pins']))[:110]}")
    print('tx_fine straps:', t['straps'])


if __name__ == '__main__':
    main()
