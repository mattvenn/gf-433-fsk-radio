#!/usr/bin/env python3
"""The Tiny Tapeout tile from the agreed floorplan: top cell tt_um_mattvenn_gf433_vco on the 2x2 VAPWR template.

    python3 layout/gen/tile.py [--partial] [--no-png]

Reads layout/floorplan/floorplan.json (placements, stripes, decap rectangles) and layout/gen/tile_nets.py (the
connectivity), writes gds/tt_um_mattvenn_gf433_vco.gds, lef/tt_um_mattvenn_gf433_vco.lef and build/tile/meta.json.
Assembly with KLayout on the GDS layers (as layout/gen/tt_wrapper.py, which stays as the reference for the old
tile): every block GDS is copied in unchanged, its sub-cells renamed with the block's name so no two blocks share a
cell name (the standard cells are shared).

Placement: floorplan.json `transform`: t = DCplxTrans(1, rot, mirror, 0, 0); bb = cell.dbbox().transformed(t);
the block goes in with DCplxTrans(1, rot, mirror, x - bb.left, y - bb.bottom).
Power: Metal4 stripes (VAPWR / VDPWR / VGND, y 5 ... 320.36) with via3 arrays wherever a stripe crosses Metal3 of
its own net inside a block (found by connectivity, M1-M3, from the block's own supply labels); blocks no stripe
reaches get supply wires from the router.
Signals: layout/gen/tile_route.py (M2 / M3 in the gaps between blocks, M4 vertical over the blocks that allow it:
not the receiver, the ring, the reference or the macro). No Metal5.
"""
import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
import tile_nets as TN  # noqa: E402
import tile_route as TR  # noqa: E402
from tile_route import P, HW, CLR  # noqa: E402

TOP = 'tt_um_mattvenn_gf433_vco'
SC = 'gf180mcu_fd_sc_mcu7t5v0__'
DEF = Path('/foss/designs/tt-support-tools/tech/gf180mcuD/def/analog/tt_analog_2x2_pgvaa.def')
OUT = REPO / 'build' / 'tile'
FP = REPO / 'layout/floorplan/floorplan.json'

LY = dict(bnd=(0, 0), m1=(34, 0), v1=(35, 0), m2=(36, 0), v2=(38, 0), m3=(42, 0), v3=(40, 0), m4=(46, 0),
          m4t=(46, 10), m2t=(36, 10), m3t=(42, 10), nwell=(21, 0), comp=(22, 0), pplus=(31, 0), nplus=(32, 0))
LNUM = {'m1': 34, 'm2': 36, 'm3': 42, 'm4': 46}
CUT, PAD, PITCH = 260, 380, 660
STRIPE_Y = (5000, 320360)
ROW_H = 3920
DCAP_W, DCAP_L, DCAP_NF = 6.0, 4.0, 2   # decap_u fingers (um): 0.2 pF per unit
# decap_u's rail strips (its own y; x insets from the unit's ends), bridged across abutted units:
# (layer, (inset left, inset right), (y0, y1)) for the VDD rail's n-well, n+ tap COMP / implant, the VSS p+ tap
DCAP_BRIDGE = [('nwell', (150, 150), (11395, 12795)), ('comp', (300, 300), (11905, 12285)),
               ('nplus', (140, 140), (11745, 12445)), ('comp', (300, 300), (-1390, -1010)),
               ('pplus', (280, 280), (-1410, -990))]
TIE_ROW_Y = 313600              # DEF ROW_79 (FS)
TIE_RISE = 322500               # tie outputs: M3 up to here (above the stripes' ends), via3, Metal4 into the pin

# floorplan cell -> (gds, top cell). Cells made here: bits_inv, the decap fill, the tie row.
CELLS = {
    'ring_core_v3 + lsdiv': ('layout/vco_core.gds', 'vco_core'),
    'cgm_ref': ('layout/cgm_ref.gds', 'cgm_ref'),
    'decap_ls': ('layout/decap_ls.gds', 'decap_ls'),
    'dbg_tg': ('layout/dbg_tg.gds', 'dbg_tg'),
    'mdac': ('layout/mdac.gds', 'mdac'),
    'vctrl_pd': ('layout/vctrl_pd.gds', 'vctrl_pd'),
    'tx_drv': ('layout/tx_drv.gds', 'tx_drv'),
    'tx_fine': ('macro/tx_fine/gds/tx_fine.gds', 'tx_fine'),
    'rx_lna': ('layout/rx_lna.gds', 'rx_lna'), 'rx_bias': ('layout/rx_bias.gds', 'rx_bias'),
    'rx_lsq_hdr': ('layout/rx_lsq_hdr.gds', 'rx_lsq_hdr'), 'rx_lobuf': ('layout/rx_lobuf.gds', 'rx_lobuf'),
    'rx_mix': ('layout/rx_mix.gds', 'rx_mix'), 'rx_bb': ('layout/rx_bb.gds', 'rx_bb'),
    'rx_lim': ('layout/rx_lim.gds', 'rx_lim'), 'rx_decap': ('layout/rx_top.gds', 'rx_decap'),
}
MAC_LEF = REPO / 'macro/tx_fine/lef/tx_fine.lef'
# blocks Metal4 may not cross (signal routes): the receiver, the ring + lsdiv, the reference, the macro
NO_M4 = ('rx.', 'vco.core', 'vco.ref', 'xmac')
# blocks the tile adds beyond the floorplan: antenna-diode rows on the long wires into small gates (KLayout ANT.16 /
# ANT.4): the TX enables (next to tx_drv's pins) and the receiver's enb (between the bias and the pull-down)
EXTRA = [dict(inst='xant_tx', cell='ant_row2', x=240.0, y=77.4, rot=0, mirror=False, orient='R0'),
         dict(inst='xant_rx', cell='ant_row1', x=406.0, y=121.0, rot=0, mirror=False, orient='R0'),
         dict(inst='xant_dbg', cell='ant_row4', x=447.0, y=127.0, rot=0, mirror=False, orient='R0')]


def parse_def(path):
    t = Path(path).read_text()
    dbu = int(re.search(r'UNITS DISTANCE MICRONS (\d+)', t).group(1))
    die = [int(v) for v in re.search(r'DIEAREA \( (\S+) (\S+) \) \( (\S+) (\S+) \)', t).groups()]
    conv = (lambda v: v * 1000 // dbu)
    pins = {}
    for m in re.finditer(r'- (\S+) \+ NET \S+ \+ DIRECTION (\w+) \+ USE (\w+)\s+\+ PORT\s+\+ LAYER (\w+) '
                         r'\( (\S+) (\S+) \) \( (\S+) (\S+) \)\s+\+ PLACED \( (\S+) (\S+) \) (\w+)', t):
        name, d, use, layer, a, b, c, e, x, y, o = m.groups()
        a, b, c, e, x, y = (int(v) for v in (a, b, c, e, x, y))
        pins[name] = dict(dir=d, use=use, layer=layer, rect=(conv(x + a), conv(y + b), conv(x + c), conv(y + e)))
    return dict(w=conv(die[2]), h=conv(die[3]), pins=pins)


def lef_pins(path):
    """{pin: (layer, (x0, y0, x1, y1) nm)}, {net: [Metal4 rects]} from a LEF."""
    t = Path(path).read_text()
    pins, power = {}, {}
    for m in re.finditer(r'PIN (\S+)(.*?)END \1', t, re.S):
        name, body = m.groups()
        rects = [(l, tuple(int(round(float(v) * 1000)) for v in r)) for l, *r in
                 re.findall(r'LAYER (\S+) ;\s*RECT (\S+) (\S+) (\S+) (\S+)', body)]
        if name in ('VDD', 'VSS'):
            power[name] = [rc for l, rc in rects if l == 'Metal4']
        else:
            pins[name] = rects[0]
    return pins, power


class NoAccess(Exception):
    pass


class Tile:
    def __init__(self, partial=False):
        import klayout.db as db
        self.db = db
        self.fp = json.loads(Path(FP).read_text())
        self.T = parse_def(DEF)
        self.W, self.H = self.T['w'], self.T['h']
        assert (self.W, self.H) == (693280, 325360), (self.W, self.H)
        self.ly = db.Layout()
        self.ly.dbu = 0.001
        self.top = self.ly.create_cell(TOP)
        self.L = {k: self.ly.layer(*v) for k, v in LY.items()}
        self.partial = partial
        self.log = dict(missing=[], blocks={}, stripes=[], via3={}, nets={}, unrouted=[])
        self.decap_nets = []
        self.inst = {}            # inst -> dict(cell, trans, bbox (nm, tile), pins {name: (layer, x, y, side)})
        OUT.mkdir(parents=True, exist_ok=True)

    # ---- drawing helpers ----
    def r(self, layer, x1, y1, x2, y2, cell=None):
        db = self.db
        x1, x2 = sorted((int(round(x1)), int(round(x2))))
        y1, y2 = sorted((int(round(y1)), int(round(y2))))
        assert x2 > x1 and y2 > y1, (layer, x1, y1, x2, y2)
        (cell or self.top).shapes(self.L[layer]).insert(db.Box(x1, y1, x2, y2))

    def via_array(self, n, xa, xb, ya, yb, margin=200, cell=None):
        nx = max(1, (xb - xa - 2 * margin - CUT) // PITCH + 1)
        ny = max(1, (yb - ya - 2 * margin - CUT) // PITCH + 1)
        x0 = (xa + xb) // 2 - (nx - 1) * PITCH // 2
        y0 = (ya + yb) // 2 - (ny - 1) * PITCH // 2
        x0 -= x0 % 5
        y0 -= y0 % 5
        for i in range(nx):
            for j in range(ny):
                self.r(f'v{n}', x0 + i * PITCH - CUT // 2, y0 + j * PITCH - CUT // 2,
                       x0 + i * PITCH + CUT // 2, y0 + j * PITCH + CUT // 2, cell)
        return nx * ny

    def via_fill(self, n, reg, enc=60):
        """via<n> cuts on a 0.66 um grid (global, so neighbouring landings never clash) wherever a cut plus `enc` of
        metal fits inside reg (a Region: the landing area on both metals)."""
        db = self.db
        inner = reg.sized(-(CUT // 2 + enc)).merged()
        k = 0
        for poly in inner.each():
            bb = poly.bbox()
            pr = db.Region(poly)
            x = bb.left - bb.left % PITCH
            while x <= bb.right:
                y = bb.bottom - bb.bottom % PITCH
                while y <= bb.top:
                    if not pr.interacting(db.Region(db.Box(x - 1, y - 1, x + 1, y + 1))).is_empty() and \
                            (db.Region(db.Box(x - 1, y - 1, x + 1, y + 1)) - pr).is_empty():
                        self.r(f'v{n}', x - CUT // 2, y - CUT // 2, x + CUT // 2, y + CUT // 2)
                        k += 1
                    y += PITCH
                x += PITCH
        return k

    def label(self, layer, text, x, y, cell=None):
        db = self.db
        (cell or self.top).shapes(self.L[layer]).insert(db.Text(text, db.Trans(db.Vector(int(x), int(y)))))

    # ---- blocks ----
    def load_cell(self, gds, name):
        """Copy cell `name` of `gds` into the tile layout (sub-cells renamed <name>__<sub>, standard cells shared)."""
        db = self.db
        if self.ly.has_cell(name):
            return self.ly.cell(name)
        src = db.Layout()
        src.read(str(REPO / gds))
        top = src.cell(name)
        assert top is not None, (gds, name)
        keep = set([top.cell_index()]) | set(top.called_cells())
        for c in list(src.each_cell()):
            if c.cell_index() not in keep:
                continue
            if c.cell_index() != top.cell_index() and not c.name.startswith('gf180mcu_'):
                c.name = f'{name}__{c.name}'
        tmp = OUT / 'cells' / f'{name}.gds'
        tmp.parent.mkdir(parents=True, exist_ok=True)
        opt = db.SaveLayoutOptions()
        opt.add_cell(top.cell_index())
        src.write(str(tmp), opt)
        lo = db.LoadLayoutOptions()
        lo.cell_conflict_resolution = db.LoadLayoutOptions.SkipNewCell
        self.ly.read(str(tmp), lo)
        c = self.ly.cell(name)
        assert c is not None
        return c

    def cell_pins(self, cell):
        """{label: (layer, x, y)} of the cell's own port labels (datatype 10, else 0), nm, cell coordinates."""
        pins = {}
        for dt in (10, 0):
            for ln, lname in ((34, 'm1'), (36, 'm2'), (42, 'm3'), (46, 'm4')):
                li = self.ly.find_layer(ln, dt)
                if li is None:
                    continue
                for sh in cell.shapes(li).each():
                    if sh.is_text():
                        p = sh.text.trans.disp
                        if dt == 0 and sh.text_string in pins:
                            continue
                        pins.setdefault(sh.text_string, [])
                        if (lname, p.x, p.y) not in pins[sh.text_string]:
                            pins[sh.text_string].append((lname, p.x, p.y))
        return pins

    def place_blocks(self):
        db = self.db
        mac_pins, mac_pow = lef_pins(MAC_LEF)
        for b in self.fp['blocks'] + EXTRA:
            inst = b['inst'] if b['inst'] not in ('deca', 'decd') else f"{b['inst']}{b['part']}"
            if b['inst'] in ('deca', 'decd'):
                continue
            if b['cell'] == 'bits_inv':
                gds, name = None, 'bits_inv'
                cell = self.bits_cell()
            elif b['cell'].startswith('ant_row'):
                gds, name = None, b['cell']
                cell = self.ant_cell(int(b['cell'][7:]))
            else:
                gds, name = CELLS[b['cell']]
            if gds is not None:
                if not (REPO / gds).exists():
                    self.log['missing'].append(inst)
                    if self.partial:
                        continue
                    raise SystemExit(f'{inst}: {gds} missing')
                cell = self.load_cell(gds, name)
            t = db.DCplxTrans(1, b['rot'], b['mirror'], 0, 0)
            bb = cell.dbbox().transformed(t)
            snap = lambda v: round(v * 200) / 200                   # the 5 nm manufacturing grid
            tr = db.DCplxTrans(1, b['rot'], b['mirror'], snap(b['x'] - bb.left), snap(b['y'] - bb.bottom))
            itr = db.ICplxTrans(tr.to_itrans(self.ly.dbu)) if hasattr(tr, 'to_itrans') else None
            self.top.insert(db.DCellInstArray(cell.cell_index(), tr))
            pb = cell.dbbox().transformed(tr)
            box = tuple(int(round(v * 1000)) for v in (pb.left, pb.bottom, pb.right, pb.top))
            if name == 'tx_fine':
                raw = {p: (l.lower().replace('etal', ''), (r[0] + r[2]) / 2, (r[1] + r[3]) / 2)
                       for p, (l, r) in mac_pins.items()}
                raw = {p: [('m' + l[-1], x, y)] for p, (l, x, y) in raw.items()}
            else:
                raw = self.cell_pins(cell)
            pins, alls = {}, {}
            for p, lst in raw.items():
                for (l, x, y) in lst:
                    q = tr * db.DPoint(x / 1000, y / 1000)
                    X, Y = int(round(q.x * 1000)), int(round(q.y * 1000))
                    d = {'left': X - box[0], 'right': box[2] - X, 'bottom': Y - box[1], 'top': box[3] - Y}
                    side = min(d, key=d.get)
                    alls.setdefault(p, []).append((l, X, Y, side, d[side]))
                pins[p] = min(alls[p], key=lambda t: t[4])           # the one on the edge by default
            self.inst[inst] = dict(cell=name, tr=tr, box=box, pins=pins, alls=alls, b=b, cellobj=cell)
            self.log['blocks'][inst] = dict(cell=name, box=[v / 1000 for v in box])
        if 'xmac' in self.inst:
            self.inst['xmac']['power'] = mac_pow

    # ---- power ----
    def supply_m3(self, inst):
        """{cell supply net: Region of its Metal3 (tile coordinates, nm)} for one placed block, by connectivity
        (M1-M3, vias, port labels) inside the block."""
        db = self.db
        I = self.inst[inst]
        cell = I['cellobj']
        if 'm3pow' not in I:
            l2n = db.LayoutToNetlist(db.RecursiveShapeIterator(self.ly, cell, []))
            L = {n: l2n.make_layer(self.ly.layer(*LY[n]), n) for n in ('m1', 'v1', 'm2', 'v2', 'm3')}
            for a, b in (('m1', 'v1'), ('v1', 'm2'), ('m2', 'v2'), ('v2', 'm3')):
                l2n.connect(L[a], L[b])
            for m, ln in (('m1', 34), ('m2', 36), ('m3', 42)):
                l2n.connect(L[m])
                for dt in (10, 0):
                    t = l2n.make_text_layer(self.ly.layer(ln, dt), f't{ln}_{dt}')
                    l2n.connect(L[m], t)
            l2n.extract_netlist()
            ckt = l2n.netlist().circuit_by_name(cell.name)
            out = {}
            sup = TN.SUPPLY.get(inst, {})
            for net in ckt.each_net():
                for part in (net.name or '').split(','):      # metal-joined labels give 'VDD,tgh'
                    if part in sup:
                        reg = l2n.shapes_of_net(net, L['m3'], True)
                        out.setdefault(part, db.Region()).insert(reg)
            itr = I['tr'].to_itrans(self.ly.dbu) if False else db.ICplxTrans(I['tr'], self.ly.dbu)
            I['m3pow'] = {k: v.transformed(itr).merged() for k, v in out.items()}
        return I['m3pow']

    def stripes(self):
        """The stripe list [(net, x0, w)] (nm): the floorplan's VAPWR / VGND pairs, the macro's Metal4 straps
        extended to full height (the only lanes over the macro), and a VDPWR stripe over tx_drv."""
        S = []
        mac = self.inst['xmac']['box'] if 'xmac' in self.inst else (0, 0, 0, 0)
        for st in self.fp['straps']:              # the floorplan's, except over the macro (its straps, below)
            x0, w = int(round(st['x'] * 1000)), int(round(st['w'] * 1000))
            if not (mac[0] - 1000 < x0 + w and x0 < mac[2] + 1000):
                S.append((st['net'], x0, w))
        if 'xmac' in self.inst:
            I = self.inst['xmac']
            db = self.db
            itr = db.ICplxTrans(I['tr'], self.ly.dbu)
            for net, tnet in (('VDD', 'VDPWR'), ('VSS', 'VGND')):
                for rc in I['power'][net]:
                    b = db.Box(*rc).transformed(itr)
                    S.append((tnet, b.left, b.width()))
        return S

    def plan_stripes(self, base):
        """Extra stripes for every block supply no stripe in `base` lands on: one stripe over a piece of that
        supply's Metal3 (vertical rails of the turned blocks: right over the rail; horizontal rails: anywhere along
        them), clear of the other stripes (1 um) and of the macro's x range. Returns [(net, x0, w)]."""
        db = self.db
        S = list(base)
        mac = self.inst['xmac']['box'] if 'xmac' in self.inst else None

        def clear(x0, w):
            if mac and x0 < mac[2] + 1000 and mac[0] - 1000 < x0 + w:
                return False
            if x0 < 1000 or x0 + w > self.W - 1000:
                return False
            return all(x0 + w + 1000 <= a or a + b + 1000 <= x0 for _, a, b in S)

        def lands(net, x0, w):
            lane = db.Region(db.Box(x0 + 60, STRIPE_Y[0], x0 + w - 60, STRIPE_Y[1]))
            out = set()
            for inst, I in self.inst.items():
                if inst == 'xmac' or not (I['box'][0] < x0 + w and x0 < I['box'][2]):
                    continue
                for cnet, reg in self.supply_m3(inst).items():
                    if TN.SUPPLY[inst][cnet] == net:
                        for poly in (reg & lane).each():
                            bb = poly.bbox()
                            if bb.width() >= CUT + 240 and bb.height() >= CUT + 240:
                                out.add((inst, cnet))
            return out
        have = set()
        for net, x0, w in S:
            have |= lands(net, x0, w)
        need = [(inst, cnet) for inst in self.inst if inst != 'xmac'
                for cnet in self.supply_m3(inst) if (inst, cnet) not in have]
        extra = []
        for inst, cnet in need:
            if (inst, cnet) in have:
                continue
            net = TN.SUPPLY[inst][cnet]
            best = None
            for poly in self.supply_m3(inst)[cnet].each():
                bb = poly.bbox()
                if bb.height() < 2200:
                    continue
                if bb.width() >= 2200:
                    w = min(2000, (bb.width() - 200) // 10 * 10)
                    for x0 in range(bb.left + 100, bb.right - 100 - w + 1, 340):
                        x0 -= x0 % 10
                        if clear(x0, w):
                            score = len(lands(net, x0, w))
                            if best is None or score > best[0]:
                                best = (score, x0, w)
                            break
            if best is None:
                continue
            _, x0, w = best
            S.append((net, x0, w))
            extra.append((net, x0, w))
            have |= lands(net, x0, w)
        self.log['stripes_added'] = [(n, x / 1000, w / 1000) for n, x, w in extra]
        return extra

    def power(self, extra=()):
        db = self.db
        S = self.stripes() + list(extra)
        (OUT / 'stripes.json').write_text(json.dumps([dict(net=n, x=x / 1000, w=w / 1000) for n, x, w in
                                                      sorted(S, key=lambda t: t[1])]))
        S.sort(key=lambda s: s[1])
        for a, b in zip(S, S[1:]):
            assert b[1] - (a[1] + a[2]) >= 1000, ('stripes too close', a, b)
        self.S = S
        self.stripe_on = {}                      # stripe x0 -> the blocks it lands on
        if 'xmac' in self.inst:
            for n, x0, w in S:
                if self.inst['xmac']['box'][0] <= x0 <= self.inst['xmac']['box'][2]:
                    self.stripe_on.setdefault(x0, set()).add('xmac')
        landed = {}
        for net, x0, w in S:
            self.r('m4', x0, STRIPE_Y[0], x0 + w, STRIPE_Y[1])
            self.r('m4t', x0, STRIPE_Y[0], x0 + w, STRIPE_Y[1])
            self.label('m4t', net, x0 + w // 2, (STRIPE_Y[0] + STRIPE_Y[1]) // 2)
            lane = db.Region(db.Box(x0 + 60, STRIPE_Y[0], x0 + w - 60, STRIPE_Y[1]))
            nv = 0
            for inst, I in self.inst.items():
                if inst == 'xmac' or not (I['box'][0] < x0 + w and x0 < I['box'][2]):
                    continue
                for cnet, reg in self.supply_m3(inst).items():
                    if TN.SUPPLY[inst][cnet] != net:
                        continue
                    land = (reg & lane).merged()
                    k = self.via_fill(3, land)
                    nv += k
                    if k:
                        cuts = self.log.setdefault('landing_cuts', {})
                        cuts[f'{inst}.{cnet}'] = cuts.get(f'{inst}.{cnet}', 0) + k
                        landed.setdefault(inst, set()).add(cnet)
                        self.stripe_on.setdefault(x0, set()).add(inst)
            self.log['stripes'].append((net, x0 / 1000, w / 1000, nv))
        self.landed = landed
        miss = {inst: sorted(set(TN.SUPPLY.get(inst, {})) - landed.get(inst, set()))
                for inst in self.inst if inst != 'xmac'}
        self.log['supply_unlanded'] = {k: v for k, v in miss.items() if v}
        return self.log['supply_unlanded']

    # ---- standard cells: the tie row ----
    def std(self, n):
        """A standard cell, copied from the PDK's GDS once (the macro may already have brought it in)."""
        db = self.db
        name = SC + n
        if self.ly.has_cell(name):
            return self.ly.cell(name)
        if not hasattr(self, '_sclib'):
            import os
            self._sclib = db.Layout()
            pdk = Path(os.environ.get('PDK_ROOT', '/foss/pdks')) / 'gf180mcuD'
            self._sclib.read(str(pdk / 'libs.ref/gf180mcu_fd_sc_mcu7t5v0/gds/gf180mcu_fd_sc_mcu7t5v0.gds'))
        src = self._sclib.cell(name)
        dst = self.ly.create_cell(name)
        dst.copy_tree(src)
        for li in self.ly.layer_indexes():
            if (self.ly.get_info(li).layer, self.ly.get_info(li).datatype) == (63, 63):
                dst.shapes(li).clear()
        return dst

    def put(self, n, x, y, flip=False, cell=None):
        db = self.db
        c = self.std(n)
        tr = db.Trans(db.Trans.M0, db.Vector(int(x), int(y) + ROW_H)) if flip else db.Trans(db.Vector(int(x), int(y)))
        (cell or self.top).insert(db.CellInstArray(c.cell_index(), tr))

    def via_stack(self, x, y, top=3, cell=None):
        """via1 ... via<top> stacked at (x, y) with 0.38 pads (M1 pad included)."""
        for k in range(1, top + 1):
            lo, hi = ('m1', 'm2', 'm3', 'm4')[k - 1], ('m1', 'm2', 'm3', 'm4')[k]
            self.r(lo, x - PAD // 2, y - PAD // 2, x + PAD // 2, y + PAD // 2, cell)
            self.r(hi, x - PAD // 2, y - PAD // 2, x + PAD // 2, y + PAD // 2, cell)
            self.r(f'v{k}', x - CUT // 2, y - CUT // 2, x + CUT // 2, y + CUT // 2, cell)

    def ties(self):
        """uio_oe[3] = 1 (tieh), every other unused output 0 (tiel): one cell under each pin in DEF row 79
        (FS, y 313.6: VDD rail at the bottom, VSS at the top, both inside the stripes' span), in 7.28 um slots
        (cell + filltie + fill_4 + fill_2 + fill_1); a driven pin in the run gets a fill_4. Each output rises on M3
        above the stripes' ends (y 322.5) and drops on Metal4 into its pin. Rails: VAPWR / VGND through via
        stacks under the first VAPWR and VGND stripes over the row (the outputs are static)."""
        tied = TN.TIE_LO + TN.TIE_HI
        px = lambda n: (self.T['pins'][n]['rect'][0] + self.T['pins'][n]['rect'][2]) // 2
        tops = sorted((n for n in self.T['pins'] if self.T['pins'][n]['rect'][1] > self.H // 2), key=px)
        run = [n for n in tops if px(min(tied, key=px)) <= px(n) <= px(max(tied, key=px))]
        xs = [px(n) for n in run]
        assert all(b - a == 7280 for a, b in zip(xs, xs[1:])), xs
        yr = TIE_ROW_Y
        x = xs[0] - 1410 - 1120
        self.put('filltie', x, yr, flip=True)
        x0 = x
        x += 1120
        obst = {1: [], 2: [], 0: []}
        for n in run:
            assert x == px(n) - 1410
            if n in tied:
                high = n in TN.TIE_HI
                self.put('tieh' if high else 'tiel', x, yr, flip=True)
                yz = yr + ROW_H - (3080 if high else 840)
                xp = px(n)
                self.via_stack(xp, yz, top=2)
                self.r('m3', xp - PAD // 2, yz - PAD // 2, xp + PAD // 2, TIE_RISE + PAD // 2)
                self.r('v3', xp - CUT // 2, TIE_RISE - CUT // 2, xp + CUT // 2, TIE_RISE + CUT // 2)
                self.r('m4', xp - PAD // 2, TIE_RISE - PAD // 2, xp + PAD // 2, self.T['pins'][n]['rect'][3])
                obst[0].append((xp - PAD // 2, yz - PAD // 2, xp + PAD // 2, yz + PAD // 2))
                obst[1].append((xp - PAD // 2, yz - PAD // 2, xp + PAD // 2, TIE_RISE + PAD // 2))
                obst[2].append((xp - PAD // 2, TIE_RISE - PAD // 2, xp + PAD // 2, self.H))
            else:
                self.put('fill_4', x, yr, flip=True)
            x += 2240
            for f, wf in (('filltie', 1120), ('fill_4', 2240), ('fill_2', 1120), ('fill_1', 560)):
                self.put(f, x, yr, flip=True)
                x += wf
        x1 = x
        # rails -> the first VAPWR and VGND stripes over the row
        done = set()
        risers = [px(n) for n in run if n in tied]
        for net, sx, w in self.S:
            if net in done or net not in ('VAPWR', 'VGND') or not (x0 < sx and sx + w < x1):
                continue
            # the via stack sits on the stripe, clear of every tie output's M3 riser (0.8 um centre to centre)
            xs_ = [x for x in range(sx + 300, sx + w - 300 + 1, 10) if all(abs(x - r) >= 800 for r in risers)]
            if not xs_:
                continue
            xv = xs_[len(xs_) // 2]
            yv = yr if net == 'VAPWR' else yr + ROW_H
            self.via_stack(xv, yv, top=3)
            for l in (0, 1):
                obst[l].append((xv - PAD // 2, yv - PAD // 2, xv + PAD // 2, yv + PAD // 2))
            done.add(net)
        assert done == {'VAPWR', 'VGND'}, done
        # the row itself (M1 only): routes may cross it on M2 / M3, but keep the router off its via pads
        self.extra_obst = obst
        self.log['ties'] = dict(row_y=yr / 1000, x=[x0 / 1000, x1 / 1000], n=len(tied))

    # ---- the coarse-code inverters ----
    def bits_cell(self):
        """bits_inv: bitb_i = not ui_in[i] (five inv_1), with an antenna diode on each input (the ui_in lines are
        long). Row A (N, y 0): filltie, then per bit inv_1 + filltie; row B (FS, y 3.92): filltie, then per bit
        fill_1 x 4, antenna (its I pin under the in riser), filltie at the end. Pins on the top
        edge (M2 risers), in the vco_core east edge's order once placed R90 (bitb_i below bit_i): out<i> at
        x_i + 0.28 (from ZN at x_i + 1.4, y 2.95), in<i> at x_i + 2.52 (to I at x_i + 0.84, y 1.7; the antenna's I
        on it at y 6.02). Rails: M1 (the cells) + an M3 strap on each, via stacks at both ends; VDD / VSS on M3."""
        if self.ly.has_cell('bits_inv'):
            return self.ly.cell('bits_inv')
        c = self.ly.create_cell('bits_inv')
        self.put('filltie', 0, 0, cell=c)
        self.put('filltie', 0, ROW_H, flip=True, cell=c)
        xs = []
        x = 1120
        for i in range(5):
            xs.append(x)
            self.put('inv_1', x, 0, cell=c)
            self.put('filltie', x + 2240, 0, cell=c)
            for k in range(4):
                self.put('fill_1', x + 560 * k, ROW_H, flip=True, cell=c)
            self.put('antenna', x + 2240, ROW_H, flip=True, cell=c)
            x += 3360
        self.put('filltie', x, 0, cell=c)
        self.put('filltie', x, ROW_H, flip=True, cell=c)
        x += 1120
        W, H = x, 2 * ROW_H
        for i, xi in enumerate(xs):
            xout, xin = xi + 280, xi + 2520
            self.r('m2', xout - HW, 2950 - HW, xout + HW, H, cell=c)
            self.r('m2', xout - HW, 2950 - HW, xi + 1400 + HW, 2950 + HW, cell=c)
            self.r('v1', xi + 1400 - CUT // 2, 2950 - CUT // 2, xi + 1400 + CUT // 2, 2950 + CUT // 2, cell=c)
            self.r('m2', xin - HW, 1700 - HW, xin + HW, H, cell=c)
            self.r('m2', xi + 840 - HW, 1700 - HW, xin + HW, 1700 + HW, cell=c)
            self.r('v1', xi + 840 - CUT // 2, 1700 - CUT // 2, xi + 840 + CUT // 2, 1700 + CUT // 2, cell=c)
            self.r('v1', xin - CUT // 2, 6020 - CUT // 2, xin + CUT // 2, 6020 + CUT // 2, cell=c)
            self.label('m2t', f'in{i}', xin, H - 100, cell=c)
            self.label('m2t', f'out{i}', xout, H - 100, cell=c)
        for net, y in (('VSS', 0), ('VDD', ROW_H), ('VSS', 2 * ROW_H)):
            self.r('m3', 0, y - 600, W, y + 600, cell=c)
            for xe in (560, W - 560):
                for k, (lo, hi) in enumerate((('m1', 'm2'), ('m2', 'm3')), 1):
                    self.r(hi, xe - PAD // 2, y - PAD // 2, xe + PAD // 2, y + PAD // 2, cell=c)
                    self.r(f'v{k}', xe - CUT // 2, y - CUT // 2, xe + CUT // 2, y + CUT // 2, cell=c)
            self.label('m3t', net, 300, y, cell=c)            # at the rail's end: on the cell edge
        self.r('bnd', 0, -600, W, H + 600, cell=c)
        return c

    # ---- antenna diodes (KLayout ANT.16 / ANT.4 on the long tile wires into small gates) ----
    def ant_cell(self, n):
        """ant_row<n>: one row (N): filltie, then n x (antenna + fill_2), filltie. Pins a<k> on the top edge (M2
        risers from each antenna's I at x + 0.28, y 1.96); rails M1 + an M3 strap each, VDD / VSS labels at the
        left end."""
        name = f'ant_row{n}'
        if self.ly.has_cell(name):
            return self.ly.cell(name)
        c = self.ly.create_cell(name)
        self.put('filltie', 0, 0, cell=c)
        x = 1120
        for k in range(n):
            self.put('antenna', x, 0, cell=c)
            self.put('fill_2', x + 1120, 0, cell=c)
            xa = x + 280
            self.r('m2', xa - HW, 1960 - HW, xa + HW, ROW_H + 1200, cell=c)
            self.r('v1', xa - CUT // 2, 1960 - CUT // 2, xa + CUT // 2, 1960 + CUT // 2, cell=c)
            self.label('m2t', f'a{k}', xa, ROW_H + 1100, cell=c)
            x += 2240
        self.put('filltie', x, 0, cell=c)
        W = x + 1120
        for net, y in (('VSS', 0), ('VDD', ROW_H)):
            self.r('m3', 0, y - 600, W, y + 600, cell=c)
            for xe in (560, W - 560):
                for k, (lo, hi) in enumerate((('m1', 'm2'), ('m2', 'm3')), 1):
                    self.r(hi, xe - PAD // 2, y - PAD // 2, xe + PAD // 2, y + PAD // 2, cell=c)
                    self.r(f'v{k}', xe - CUT // 2, y - CUT // 2, xe + CUT // 2, y + CUT // 2, cell=c)
            self.label('m3t', net, 300, y, cell=c)
        self.r('bnd', 0, -600, W, ROW_H + 1200, cell=c)
        return c

    # ---- signal routing ----
    def grid_setup(self):
        G = TR.Grid(self.W, self.H)
        for inst, I in self.inst.items():
            x0, y0, x1, y1 = I['box']
            for l in (0, 1):
                G.block(l, x0, y0, x1, y1, clr=CLR + 100)
            if inst.startswith('rx.'):
                i0, i1 = G.span(x0, x1, CLR + 100)
                j0, j1 = G.span(y0, y1, CLR + 100)
                G.m4mask[max(i0, 0):i1 + 1, max(j0, 0):j1 + 1] = True
            elif inst.startswith(NO_M4) or inst in NO_M4:
                G.block(2, x0, y0, x1, y1, clr=CLR + (2000 if inst == 'xmac' else 100))
        for net, x0, w in self.S:
            G.block(2, x0, STRIPE_Y[0], x0 + w, STRIPE_Y[1])
        for name, p in self.T['pins'].items():
            G.block(2, *p['rect'])
        for l, rects in getattr(self, 'extra_obst', {}).items():
            for rc in rects:
                G.block(l, *rc)
        self.G = G
        self.stubs = []                     # (layer, rect, net id) drawn outside the routes
        return G

    def claim(self, nid, shapes, inside=None, node=None):
        """Pin stubs: check the shapes (layer, x0, y0, x1, y1) keep 0.28 um from every other net's stubs (exact
        geometry), stay off grid obstacles outside `inside` (the pin's own block, whose own metal the stub runs over)
        and that `node` is free; then mark the grid nodes within a wire's reach of the shapes: this net's where free,
        nobody's where another net's stub reaches too."""
        G = self.G
        lidx = {'m2': 0, 'm3': 1, 'm4': 2}
        for (ly_, a, b, c, d) in shapes:
            for (sh2, n2) in self.stubs:
                if n2 != nid and sh2[0] == ly_ and not (c + 280 <= sh2[1] or sh2[3] + 280 <= a or d + 280 <= sh2[2]
                                                        or sh2[4] + 280 <= b):
                    return False
        if node is not None and G.own[node] not in (0, nid):
            return False
        foot = []
        for (ly_, a, b, c, d) in shapes:
            if ly_ not in lidx:
                continue
            l = lidx[ly_]
            i0, i1 = G.span(a, c, CLR - 1)
            j0, j1 = G.span(b, d, CLR - 1)
            for i in range(max(i0, 0), min(i1, G.nx - 1) + 1):
                for j in range(max(j0, 0), min(j1, G.ny - 1) + 1):
                    ins = inside and inside[0] - CLR - 100 <= G.X(i) <= inside[2] + CLR + 100 and \
                        inside[1] - CLR - 100 <= G.Y(j) <= inside[3] + CLR + 100
                    o = G.own[l, i, j]
                    if o == -1 and not ins:
                        return False
                    foot.append((l, i, j))
        for n in foot:
            o = G.own[n]
            if o == 0:
                G.own[n] = nid
            elif o > 0 and o != nid:
                G.own[n] = -1
        if node is not None:
            G.own[node] = nid
        return True

    def access(self, nid, inst, pin, toward=None):
        """A stub from a block pin out of the block's halo onto the grid; returns the grid node. A pin with
        several edge labels (the shared I / Q cells) uses the one nearest `toward` (the net's other ends)."""
        G = self.G
        I = self.inst[inst]
        cands = [c for c in I['alls'].get(pin, [I['pins'][pin]]) if c[4] <= 1500] or [I['pins'][pin]]
        if toward is not None and len(cands) > 1:
            cands.sort(key=lambda c: abs(c[1] - toward[0]) + abs(c[2] - toward[1]))
        l, X, Y, side, depth = cands[0]
        box = I['box']
        halo = CLR + 100
        for k in range(12):
            if side in ('left', 'right'):
                if side == 'right':
                    i = -(-(box[2] + halo) // P) + k
                else:
                    i = (box[0] - halo) // P - k
                j = int(round(Y / P))
                xg, yg = G.X(i), G.Y(j)
                sh = [(l, min(X, xg) - HW, Y - HW, max(X, xg) + HW, Y + HW)]
                if l == 'm2':
                    sh += [('m2', xg - HW, Y - HW, xg + HW, Y + HW), ('v2', xg - 130, Y - 130, xg + 130, Y + 130),
                           ('m3', xg - HW, Y - HW, xg + HW, Y + HW)]
                sh.append(('m3', xg - HW, min(Y, yg) - HW, xg + HW, max(Y, yg) + HW))
                node = (1, i, j)
            else:
                if side == 'top':
                    j = -(-(box[3] + halo) // P) + k
                else:
                    j = (box[1] - halo) // P - k
                i = int(round(X / P))
                xg, yg = G.X(i), G.Y(j)
                sh = [(l, X - HW, min(Y, yg) - HW, X + HW, max(Y, yg) + HW)]
                if l == 'm3':
                    sh += [('m3', X - HW, yg - HW, X + HW, yg + HW), ('v2', X - 130, yg - 130, X + 130, yg + 130),
                           ('m2', X - HW, yg - HW, X + HW, yg + HW)]
                sh.append(('m2', min(X, xg) - HW, yg - HW, max(X, xg) + HW, yg + HW))
                node = (0, i, j)
            if not (0 < node[1] < G.nx - 1 and 0 < node[2] < G.ny - 1):
                break
            if self.claim(nid, sh, inside=box, node=node):
                self.stubs += [(s_, nid) for s_ in sh]
                return node
        raise NoAccess(f'{inst}.{pin}: no pin access ({side}, {X / 1000:.2f}, {Y / 1000:.2f})')

    def tt_terminal(self, nid, name):
        """Terminal nodes for a TT pin: a digital pin (top edge) gets an M4 drop to grid row 476 and a jog onto
        the grid; an analog pad (bottom edge) offers every M4 node on row 2 above it."""
        G = self.G
        x0, y0, x1, y1 = self.T['pins'][name]['rect']
        xc = (x0 + x1) // 2
        if y0 > self.H // 2:
            j = 476
            i = int(round(xc / P))
            sh = [('m4', xc - HW, G.Y(j) - HW, xc + HW, y1), ('m4', min(xc, G.X(i)) - HW, G.Y(j) - HW,
                                                                max(xc, G.X(i)) + HW, G.Y(j) + HW)]
            assert self.claim(nid, sh, inside=(x0, y0, x1, y1)), name
            self.stubs += [(s_, nid) for s_ in sh]
            return {(2, i, j)}
        out = set()
        for i in range(G.nx):
            if x0 + HW <= G.X(i) <= x1 - HW:
                out.add((2, i, 2))
                G.own[2, i, 1:3] = nid
        sh = [('m4', x0, y0, x1, G.Y(2) + HW)]
        self.stubs += [(s_, nid) for s_ in sh]
        return out

    def route_nets(self, nets, order, unl=None):
        """Route every net (multi-terminal: each further terminal to the tree so far). nets: {name: ends}."""
        G = self.G
        ids = {n: k + 1 for k, n in enumerate(nets)}
        self.ids = ids
        terms = {}
        for n, ends in nets.items():
            terms[n] = []
            pts = []
            for inst, pin in ends:
                if inst == 'PIN':
                    r_ = self.T['pins'][pin]['rect']
                    pts.append(((r_[0] + r_[2]) // 2, (r_[1] + r_[3]) // 2))
                elif inst in self.inst:
                    pts.append(self.inst[inst]['pins'][pin][1:3])
            for k, (inst, pin) in enumerate(ends):
                if inst == 'PIN':
                    terms[n].append(self.tt_terminal(ids[n], pin))
                else:
                    o = [q for kk, q in enumerate(pts) if kk != k] or pts
                    c = (sum(q[0] for q in o) // len(o), sum(q[1] for q in o) // len(o))
                    try:
                        terms[n].append({self.access(ids[n], inst, pin, toward=c)})
                    except NoAccess as e:
                        print(e, flush=True)
                        self.log['unrouted'].append(f'{n} (access {inst}.{pin})')
        self.paths = paths = {}
        if unl:                                 # the blocks' own supply wires first: short and local
            self.log['supply_routes'] = self.supply_routes(unl)
        self.shield_nodes = {}                  # net -> [(l, i, j)] reserved beside it for its VGND shield
        sid0 = len(ids) + 1000
        for n in order:
            nid = ids[n]
            T = terms[n]
            if len(T) < len(nets[n]):
                continue                        # a pin without access (logged)
            G.pen = None
            if n in TN.KEEP_AWAY:               # an aggressor: pay to come within 3 tracks of the guarded wires
                G.pen = np.zeros(G.own.shape, dtype=np.int32)
                for v in TN.KEEP_AWAY[n]:
                    for p_ in paths.get(v, []):
                        for (l, i, j) in p_:
                            G.pen[:, max(0, i - 3):i + 4, max(0, j - 3):j + 4] = 20
            tree = set(T[0])
            rest = T[1:]
            paths[n] = []
            while rest:
                rest.sort(key=lambda s: min(abs(a[1] - b[1]) + abs(a[2] - b[2]) for a in s for b in list(tree)[:200]))
                src = rest.pop(0)
                path = G.route(src, tree, nid, m4mask_ok=n in TN.RX_M4_OK,
                               allow=(True, True, n not in TN.NO_M4_NETS))
                if path is None:
                    self.log['unrouted'].append(n)
                    print('unrouted', n, 'from', [(q[0], G.X(q[1]) / 1000, G.Y(q[2]) / 1000) for q in list(src)[:2]],
                          'to a tree of', len(tree), 'nodes near', [(q[0], G.X(q[1]) / 1000, G.Y(q[2]) / 1000)
                                                                    for q in list(tree)[:2]], flush=True)
                    break
                paths[n].append(path)
                tree |= set(path)
                for nd in path:
                    G.own[nd] = nid
            if n in TN.SHIELDED and paths[n]:
                # the free nodes beside the wire on its own layer become its shield (VGND, joined later)
                sid = sid0 + len(self.shield_nodes)
                sh_ = []
                for p_ in paths[n]:
                    for (l, i, j) in p_:
                        for (a_, b_) in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                            q = (l, i + a_, j + b_)
                            if 0 < q[1] < G.nx - 1 and 0 < q[2] < G.ny - 1 and G.own[q] == 0 and \
                                    not (l == 2 and G.m4mask[q[1], q[2]]):
                                G.own[q] = sid
                                sh_.append(q)
                self.shield_nodes[n] = (sid, sh_)
        G.pen = None
        self.paths = paths
        return paths

    def shields(self):
        """Draw each guarded net's shield nodes as wires (connected runs per layer, at least 3 nodes), each run
        wired to VGND: an M3 node under a VGND stripe (via3), by the router. Runs that can't reach VGND are left
        out (their nodes freed)."""
        G = self.G
        gnd = set()
        for n2, sx, w in self.S:
            if n2 == 'VGND':
                for i in range(G.nx):
                    if sx + 2 * HW <= G.X(i) <= sx + w - 2 * HW:
                        for j in range(G.ny):
                            if STRIPE_Y[0] + 500 < G.Y(j) < STRIPE_Y[1] - 500:
                                gnd.add((1, i, j))
        out = {}
        for n, (sid, nodes) in self.shield_nodes.items():
            left = set(nodes)
            runs = []
            while left:                        # connected components on one layer
                s0 = left.pop()
                comp, todo = {s0}, [s0]
                while todo:
                    l, i, j = todo.pop()
                    for q in ((l, i + 1, j), (l, i - 1, j), (l, i, j + 1), (l, i, j - 1)):
                        if q in left:
                            left.discard(q); comp.add(q); todo.append(q)
                runs.append(comp)
            kept, length = 0, 0
            for comp in runs:
                if len(comp) < 3:
                    for q in comp:
                        G.own[q] = 0
                    continue
                dst = {q for q in gnd if G.own[q] == 0}
                path = G.route(comp, dst, sid, allow=(True, True, False)) if dst else None
                if path is None:
                    for q in comp:
                        G.own[q] = 0
                    continue
                for nd in path:
                    G.own[nd] = sid
                e = path[-1]
                x, y = G.X(e[1]), G.Y(e[2])
                self.r('v3', x - CUT // 2, y - CUT // 2, x + CUT // 2, y + CUT // 2)
                for sh in TR.path_shapes(path):
                    self.r(*sh)
                lay = TR.LAYERS
                for (l, i, j) in comp:          # the run itself: node pads joined to their neighbours in the run
                    x, y = G.X(i), G.Y(j)
                    self.r(lay[l], x - HW, y - HW, x + HW, y + HW)
                    for q in ((l, i + 1, j), (l, i, j + 1)):
                        if q in comp:
                            self.r(lay[l], x - HW, y - HW, G.X(q[1]) + HW, G.Y(q[2]) + HW)
                kept += 1
                length += len(comp) * P / 1000
            out[n] = dict(runs=kept, of=len(runs), um=round(length, 1))
        self.log['shields'] = out
        return out


    def supply_routes(self, unlanded):
        """Each block supply no stripe lands on: a wire from its supply label to the nearest free Metal3 node under a
        stripe of its tile net, and a via3 there (small blocks: the debug switches, the code inverters, a decap)."""
        G = self.G
        out = {}
        for inst, cnets in unlanded.items():
            for cnet in cnets:
                net = TN.SUPPLY[inst][cnet]
                name = f'pwr:{inst}.{cnet}'
                nid = max(self.ids.values()) + 1
                self.ids[name] = nid
                x0, y0, x1, y1 = self.inst[inst]['box']
                cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
                try:
                    src = self.access(nid, inst, cnet)
                except NoAccess as e:
                    print(e, flush=True)
                    self.log['unrouted'].append(name)
                    continue
                dst = set()
                for n2, sx, w in self.S:
                    if n2 != net or abs(sx - cx) > 200000:
                        continue
                    for i in range(G.nx):
                        if sx + 2 * HW <= G.X(i) <= sx + w - 2 * HW:
                            for j in range(G.ny):
                                if abs(G.Y(j) - cy) < 200000 and G.own[1, i, j] == 0 and STRIPE_Y[0] + 500 < G.Y(j) \
                                        < STRIPE_Y[1] - 500:
                                    dst.add((1, i, j))
                path = G.route({src}, dst, nid, allow=(True, True, False)) if dst else None
                if path is None:
                    self.log['unrouted'].append(name)
                    print('unrouted', name, flush=True)
                    continue
                for nd in path:
                    G.own[nd] = nid
                e = path[-1]
                x, y = G.X(e[1]), G.Y(e[2])
                self.stubs.append((('v3', x - CUT // 2, y - CUT // 2, x + CUT // 2, y + CUT // 2), nid))
                self.paths[name] = [path]
                out[name] = len(path)
        return out

    def join_stripes(self):
        """Inside the tile, the stripes of one net meet only through the blocks they land on (on chip, TT's Metal5
        grid joins them all). For LVS each net must be one net in the tile: the groups of stripes that share no
        block are joined by a thin router wire between free Metal3 nodes under them (via3 at each end)."""
        G = self.G
        out = {}
        for net in ('VAPWR', 'VDPWR', 'VGND'):
            st = [(x0, w) for n, x0, w in self.S if n == net]
            if len(st) < 2:
                continue
            # union-find over the stripes: two are joined if they land on a common block
            par = {x0: x0 for x0, _ in st}

            def f(a):
                while par[a] != a:
                    a = par[a]
                return a
            for i, (a, _) in enumerate(st):
                for b, _ in st[i + 1:]:
                    if self.stripe_on.get(a, set()) & self.stripe_on.get(b, set()):
                        par[f(a)] = f(b)
            groups = {}
            for x0, w in st:
                groups.setdefault(f(x0), []).append((x0, w))
            if len(groups) < 2 or net == 'VGND':        # VGND: the substrate joins its taps (extracted)
                continue
            name = f'join:{net}'
            nid = max(self.ids.values()) + 1
            self.ids[name] = nid

            def nodes(lst):
                q = set()
                for x0, w in lst:
                    for i in range(G.nx):
                        if x0 + 2 * HW <= G.X(i) <= x0 + w - 2 * HW:
                            for j in range(G.ny):
                                if STRIPE_Y[0] + 500 < G.Y(j) < STRIPE_Y[1] - 500 and G.own[1, i, j] == 0:
                                    q.add((1, i, j))
                return q
            gl = sorted(groups.values(), key=lambda l: l[0][0])
            tree = nodes(gl[0])
            paths = []
            for lst in gl[1:]:
                src = nodes(lst)
                path = G.route(src, tree, nid, allow=(True, True, False))
                if path is None:
                    self.log['unrouted'].append(name)
                    break
                for nd in path:
                    G.own[nd] = nid
                for e in (path[0], path[-1]):
                    x, y = G.X(e[1]), G.Y(e[2])
                    self.stubs.append((('v3', x - CUT // 2, y - CUT // 2, x + CUT // 2, y + CUT // 2), nid))
                    self.stubs.append((('m3', x - HW, y - HW, x + HW, y + HW), nid))
                tree |= set(path) | src
                paths.append(path)
            self.paths[name] = paths
            out[net] = dict(groups=len(gl), length_um=round(sum(len(p) for p in paths) * P / 1000, 1))
        self.log['stripe_joins'] = out
        return out

    def draw_routes(self):
        # a route via2 / via3 near a via of its own stub (the stub's via sits at the pin's off-grid x or y) would
        # overlap it (V2.1 / V2.2a): it is left out and both metals are bridged to the stub's via instead
        sv = {}
        for (sh, nid) in self.stubs:
            if sh[0] in ('v2', 'v3'):
                sv.setdefault((nid, sh[0]), []).append(((sh[1] + sh[3]) // 2, (sh[2] + sh[4]) // 2))
        self.log['vias_merged'] = 0
        for n, ps in self.paths.items():
            L = 0
            nid = self.ids[n]
            for path in ps:
                for sh in TR.path_shapes(path):
                    if sh[0] in ('v2', 'v3'):
                        x, y = (sh[1] + sh[3]) // 2, (sh[2] + sh[4]) // 2
                        # (only a via in line with the stub's: the patch is then a straight strip along the stub;
                        # a diagonal one would sweep over a neighbouring pin's stub)
                        near = [q for q in sv.get((nid, sh[0]), []) if abs(q[0] - x) < 700 and abs(q[1] - y) < 700
                                and (abs(q[0] - x) < 10 or abs(q[1] - y) < 10)]
                        if near:
                            qx, qy = near[0]
                            lo, hi = {'v2': ('m2', 'm3'), 'v3': ('m3', 'm4')}[sh[0]]
                            for lay in (lo, hi):
                                self.r(lay, min(x, qx) - HW, min(y, qy) - HW, max(x, qx) + HW, max(y, qy) + HW)
                            self.log['vias_merged'] += 1
                            continue
                    self.r(*sh)
                L += len(path) * P / 1000
            self.log['nets'][n] = round(L, 1)
        for (sh, nid) in self.stubs:
            if sh[0] in LY:
                self.r(*sh)

    # ---- special wiring ----
    def dac_lines(self):
        """The 37 DAC control lines across the gap between the macro's west edge (pins M3) and mdac's east edge
        (pins M2): M2 from mdac to a jog column, via2, M3 jog to the macro pin's y, M3 into the pin. The jog column of
        each line is found by a backtracking search so all shapes keep 0.28 um (M2.2a / M3.2a) apart."""
        db = self.db
        M, D = self.inst['xmac'], self.inst['xmdac']
        xm = M['box'][0]
        xd = D['box'][2]
        assert 4000 <= xm - xd, ('the mdac / macro gap is too small for the jogs', xm - xd)
        cols = list(range(xd + 700, xm - 600, 340))
        lines = []
        for mp, dp in TN.dac_pairs():
            ym = M['pins'][mp][2]
            yd = D['pins'][dp][2]
            lines.append((mp, dp, ym - ym % 5, yd - yd % 5))
        lines.sort(key=lambda t: t[3])

        def shapes(ym, yd, xj):
            return [('m2', xd - 300, yd - HW, xj + HW, yd + HW),
                    ('m3', xj - HW, min(ym, yd) - HW, xj + HW, max(ym, yd) + HW),
                    ('m3', xj - HW, ym - HW, xm + 400, ym + HW)]

        def clash(a, b):
            return a[0] == b[0] and not (a[3] + 280 <= b[1] or b[3] + 280 <= a[1] or a[4] + 280 <= b[2]
                                         or b[4] + 280 <= a[2])
        # backtracking over the lines in y order: each line only meets its neighbours within ~2 um
        choice = [None] * len(lines)

        def solve(k):
            if k == len(lines):
                return True
            mp, dp, ym, yd = lines[k]
            near = [m for m in range(k) if abs(lines[m][3] - yd) < 3000 or abs(lines[m][2] - ym) < 3000]
            for xj in cols:
                sh = shapes(ym, yd, xj)
                if all(not clash(a, b) for m in near for a in sh for b in shapes(lines[m][2], lines[m][3],
                                                                                   choice[m])):
                    choice[k] = xj
                    if solve(k + 1):
                        return True
            choice[k] = None
            return False
        sys.setrecursionlimit(10000)
        if not solve(0):
            raise SystemExit('DAC lines: no jog assignment')
        out = {}
        for (mp, dp, ym, yd), xj in zip(lines, choice):
            for q in shapes(ym, yd, xj):
                self.r(*q)
            self.r('m2', xj - HW, yd - HW, xj + HW, yd + HW)
            self.r('v2', xj - 130, yd - 130, xj + 130, yd + 130)
            out[mp] = dict(mdac=dp, jog_x=xj / 1000, dy=(ym - yd) / 1000)
        self.log['dac_lines'] = out
        # keep the router out of the gap where the lines run
        ys = [y for _, _, a, b in lines for y in (a, b)]
        self.G.block(0, xd, min(ys) - 1000, xm, max(ys) + 1000)
        self.G.block(1, xd, min(ys) - 1000, xm, max(ys) + 1000)
        return out

    def tx_outputs(self):
        """tx_drv's outputs straight onto their pads (12.6 mA): the out bars' Metal3 at the block's pad edge, a
        Metal4 plate from the pad up over it and a via3 array between (the bars' widths: 6.74 / 8 um)."""
        db = self.db
        I = self.inst['xtxd']
        I.setdefault('m3sig', None)
        l2n = db.LayoutToNetlist(db.RecursiveShapeIterator(self.ly, I['cellobj'], []))
        L = {n: l2n.make_layer(self.ly.layer(*LY[n]), n) for n in ('m1', 'v1', 'm2', 'v2', 'm3')}
        for a, b in (('m1', 'v1'), ('v1', 'm2'), ('m2', 'v2'), ('v2', 'm3')):
            l2n.connect(L[a], L[b])
        for m, ln in (('m1', 34), ('m2', 36), ('m3', 42)):
            l2n.connect(L[m])
            t = l2n.make_text_layer(self.ly.layer(ln, 10), f't{ln}')
            l2n.connect(L[m], t)
        l2n.extract_netlist()
        ckt = l2n.netlist().circuit_by_name(I['cellobj'].name)
        itr = db.ICplxTrans(I['tr'], self.ly.dbu)
        out = {}
        obst = []
        for pin, pad in (('out_p', 'ua[3]'), ('out_n', 'ua[2]')):
            net = [n for n in ckt.each_net() if pin in (n.name or '').split(',')]
            assert len(net) == 1, pin
            reg = l2n.shapes_of_net(net[0], L['m3'], True).transformed(itr).merged()
            px0, py0, px1, py1 = self.T['pins'][pad]['rect']
            win = db.Region(db.Box(px0 - 4000, I['box'][1], px1 + 4000, I['box'][1] + 6000))
            land = (reg & win).merged()
            assert not land.is_empty(), (pin, 'no M3 at the pad edge')
            bb = land.bbox()
            x0, x1 = min(bb.left, px0), max(bb.right, px1)
            self.r('m4', x0, 0, x1, bb.top)
            obst.append((x0, 0, x1, bb.top))
            nv = self.via_fill(3, land, enc=120)
            out[pin] = dict(pad=pad, via3=nv, m4=[v / 1000 for v in (x0, 0, x1, bb.top)])
        self.extra_obst.setdefault(2, []).extend(obst)
        self.log['tx_outputs'] = out
        return out

    # ---- decap fill ----
    def decap_unit(self):
        """decap_u: one rx_lib band, two nfet_03v3 gate-cap fingers DCAP_W / DCAP_L (gate VDD, S/D/B VSS), VSS rail
        at the bottom, VDD at the top (M1 + M2 + M3 each). Made with magic through rx_lib.write."""
        import rx_lib as R
        from ring_core import Cell
        if self.ly.has_cell('decap_u'):
            return self.dcu
        seq = ['VSS'] + ['VDD', 'VSS'] * DCAP_NF
        cell = Cell('decap_u')
        b = R.Band('dc', [('DC', [], [R.mos(DCAP_W, DCAP_L, seq, 'VSS')])], search=False)
        metas, bb = R.stack(cell, [b], [{}])
        gds = OUT / 'decap_u.gds'
        R.write([cell], 'decap_u', gds, OUT / 'decap_u')
        rails = {net: (y0, y1) for net, (y0, y1), _ in metas[0]['rails']}
        c = self.load_cell(str(gds.relative_to(REPO)), 'decap_u')
        bx = c.bbox()
        self.dcu = dict(cell=c, w=bx.width(), h=bx.height(), y0=bx.bottom, rails=rails)
        return self.dcu

    def decap(self):
        """Fill the floorplan's decap rectangles with decap_u rows (every second row mirrored, sharing the rail),
        after routing: a unit goes only where its footprint touches no route, stub or block; a run of abutting
        units is kept only if a stripe of its supply and a VGND stripe cross its rails (via3 there). A rectangle's
        supply is the floorplan's, except where only VDPWR stripes cross it (under the macro): VDPWR there."""
        db = self.db
        U = self.decap_unit()
        G = self.G
        (vb, vt), (gb, gt) = U['rails']['VDD'], U['rails']['VSS']
        out = []
        tot = 0
        for b in self.fp['blocks']:
            if b['inst'] not in ('deca', 'decd'):
                continue
            x0, y0 = int(b['x'] * 1000), int(b['y'] * 1000)
            x1, y1 = x0 + int(b['w'] * 1000), y0 + int(b['h'] * 1000)
            nets = {n for n, sx, w in self.S if x0 < sx and sx + w < x1}
            sup = b['supply'] if b['supply'] in nets else ('VDPWR' if 'VDPWR' in nets else b['supply'])
            if 'VGND' not in nets or sup not in nets:
                out.append(dict(rect=[v / 1000 for v in (x0, y0, x1, y1)], units=0, why='no stripe pair crosses it'))
                continue
            k = 0
            n_units = 0
            oy = y0 - U['y0']                   # row 0 upright, its bottom on the rectangle's
            while True:
                flip = k % 2 == 1
                if k:                           # share the previous row's top rail (VDD after an upright row)
                    oy = oy + vb + vt if flip else oy - gt - gb
                yb = oy + U['y0'] if not flip else oy - U['y0'] - U['h']
                if yb + U['h'] > y1:
                    break
                run = []
                xs = list(range(x0 - x0 % 5, x1 - U['w'] + 1, U['w']))
                rows = []
                for x in xs:
                    fx0, fy0, fx1, fy1 = x - 600, yb - 600, x + U['w'] + 600, yb + U['h'] + 600
                    i0, i1 = G.span(fx0, fx1, 0)
                    j0, j1 = G.span(fy0, fy1, 0)
                    busy = bool(np.any(G.own[0:2, max(i0, 0):i1 + 1, max(j0, 0):j1 + 1] != 0))
                    if not busy:
                        run.append(x)
                    elif run:
                        rows.append(run)
                        run = []
                if run:
                    rows.append(run)
                for run in rows:
                    rx0, rx1 = run[0], run[-1] + U['w']
                    land = {}
                    for net, sx, w in self.S:
                        if rx0 + 300 <= sx and sx + w <= rx1 - 300 and net in (sup, 'VGND'):
                            land.setdefault(net, []).append((sx, w))
                    if sup not in land or 'VGND' not in land:
                        continue
                    # abutted units: bridge the n-well and the tap strips across the joins (NW.2a, NP.2)
                    for lay, (a0, a1), (yl0, yl1) in DCAP_BRIDGE:
                        ya, yb2 = sorted((oy - yl0, oy - yl1) if flip else (oy + yl0, oy + yl1))
                        self.r(lay, rx0 + a0, ya, rx1 - a1, yb2)
                    for x in run:
                        tr = db.Trans(db.Trans.M0, db.Vector(x, oy)) if flip else db.Trans(db.Vector(x, oy))
                        self.top.insert(db.CellInstArray(U['cell'].cell_index(), tr))
                        G.block(0, x, yb, x + U['w'], yb + U['h'], clr=0)
                        G.block(1, x, yb, x + U['w'], yb + U['h'], clr=0)
                        n_units += 1
                    for net, lst in land.items():
                        ra, rb_ = U['rails']['VDD' if net == sup else 'VSS']
                        ya, yb2 = sorted((oy - ra, oy - rb_) if flip else (oy + ra, oy + rb_))
                        for sx, w in lst:
                            self.via_array(3, sx, sx + w, ya, yb2, margin=150)
                    self.decap_nets.append((sup, len(run)))
                k += 1
            tot += n_units
            out.append(dict(rect=[v / 1000 for v in (x0, y0, x1, y1)], supply=sup, units=n_units))
        cu = 2 * DCAP_NF * DCAP_W * DCAP_L * 4.07e-3 / 2      # pF per unit (nfet_03v3 gate C incl. overlap)
        self.log['decap'] = dict(regions=out, units=tot, pF=round(tot * cu, 1))
        self.log['decap_runs'] = self.decap_nets
        return out

    # ---- template pins ----
    def tt_pins(self):
        for name, p in self.T['pins'].items():
            assert p['layer'] == 'Metal4'
            self.r('m4', *p['rect'])
            self.r('m4t', *p['rect'])
            self.label('m4t', name, (p['rect'][0] + p['rect'][2]) // 2, (p['rect'][1] + p['rect'][3]) // 2)

    def supply_pins(self):
        """tile_nets.SUPPLY_PINS: a Metal4 strap from the TT pin up into the supply stripe that starts above it."""
        out = {}
        for pin, net in TN.SUPPLY_PINS.items():
            px0, py0, px1, py1 = self.T['pins'][pin]['rect']
            over = [(sx, w) for n2, sx, w in self.S if n2 == net and sx < px1 and sx + w > px0]
            assert over, f'{pin}: no {net} stripe above it'
            sx, w = over[0]
            x0, x1 = max(px0, sx), min(px1, sx + w)
            assert x1 - x0 >= 1000, (pin, x0, x1)
            self.r('m4', x0, py0, x1, STRIPE_Y[0] + 500)
            self.extra_obst.setdefault(2, []).append((x0, py0, x1, STRIPE_Y[0] + 500))
            out[pin] = dict(net=net, m4=[v / 1000 for v in (x0, py0, x1, STRIPE_Y[0] + 500)])
        self.log['supply_pins'] = out
        return out

    def write_lef(self, path):
        """The tile LEF: the template's pins (Metal4), every stripe as a VDPWR / VAPWR / VGND port, obstructions on
        Metal1-3 over the whole tile and on Metal4 for every drawn Metal4 shape that is not a pin or a stripe."""
        db = self.db
        f = lambda v: f"{v / 1000:.3f}"
        W, H = self.W, self.H
        out = ["VERSION 5.7 ;", "  NOWIREEXTENSIONATPIN ON ;", '  DIVIDERCHAR "/" ;', '  BUSBITCHARS "[]" ;',
               f"MACRO {TOP}", "  CLASS BLOCK ;", f"  FOREIGN {TOP} ;", "  ORIGIN 0.000 0.000 ;",
               f"  SIZE {f(W)} BY {f(H)} ;"]
        for name in sorted(self.T['pins']):
            p = self.T['pins'][name]
            out += [f"  PIN {name}", f"    DIRECTION {p['dir']} ;", "    USE SIGNAL ;", "    PORT",
                    "      LAYER Metal4 ;", "        RECT " + " ".join(f(v) for v in p['rect']) + " ;",
                    "    END", f"  END {name}"]
        for net, use in (("VDPWR", "POWER"), ("VAPWR", "POWER"), ("VGND", "GROUND")):
            out += [f"  PIN {net}", "    DIRECTION INOUT ;", f"    USE {use} ;"]
            for n, x0, w in self.S:
                if n == net:
                    out += ["    PORT", "      LAYER Metal4 ;",
                            f"        RECT {f(x0)} {f(STRIPE_Y[0])} {f(x0 + w)} {f(STRIPE_Y[1])} ;", "    END"]
            out.append(f"  END {net}")
        out += ["  OBS"] + sum([[f"    LAYER Metal{k} ;", f"      RECT 0.000 0.000 {f(W)} {f(H)} ;"]
                                for k in (1, 2, 3)], [])
        m4 = db.Region(self.top.begin_shapes_rec(self.L['m4'])).merged()
        pins = db.Region()
        for p in self.T['pins'].values():
            pins.insert(db.Box(*p['rect']))
        for n, x0, w in self.S:
            pins.insert(db.Box(x0, STRIPE_Y[0], x0 + w, STRIPE_Y[1]))
        rest = (m4 - pins.sized(300)).merged()
        if not rest.is_empty():
            out.append("    LAYER Metal4 ;")
            for poly in rest.each():
                b = poly.bbox()
                out.append(f"      RECT {f(b.left)} {f(b.bottom)} {f(b.right)} {f(b.top)} ;")
        out += ["  END", f"END {TOP}", "END LIBRARY", ""]
        Path(path).write_text("\n".join(out))

    def write(self, gds):
        self.ly.write(str(gds))


def build(partial, order=None, quiet=False):
    """One full build (placement, power, ties, routing, decap) with the given net order. Returns the Tile."""
    say = (lambda *a: None) if quiet else print
    t = Tile(partial=partial)
    t.r('bnd', 0, 0, t.W, t.H)
    t.place_blocks()
    t.tt_pins()
    unl = t.power(t.plan_stripes(t.stripes()))
    say('unlanded supplies (wired by the router):', unl)
    say('stripes added:', t.log['stripes_added'])
    t.ties()
    t.supply_pins()
    if 'xtxd' in t.inst:
        t.tx_outputs()
    t.grid_setup()
    if 'xmac' in t.inst and 'xmdac' in t.inst:
        t.dac_lines()
    allnets = TN.nets()
    special = set(m for m, _ in TN.dac_pairs()) | {'tx_outp', 'tx_outn'}
    nets = {n: e for n, e in allnets.items() if n not in special
            and all(i == 'PIN' or (i in t.inst and p in t.inst[i]['alls']) for i, p in e)}
    t.log['skipped'] = sorted(set(allnets) - set(nets) - special)
    if order is None:
        first = ['ls', 'lsq', 'vq', 'vg', 'vbnf', 'vctrl', 'ck', 'ri_p', 'ri_n', 'rq_p', 'rq_n', 'lo_i', 'lob_i',
                 'lo_q', 'lob_q', 'rx_inp', 'rx_inn', 'bi_p', 'bi_n', 'bq_p', 'bq_n', 'oi_p', 'oi_n', 'oq_p', 'oq_n']
        order = [n for n in first if n in nets] + sorted((n for n in nets if n not in first),
                                                         key=lambda n: len(nets[n]))
    order = [n for n in order if n in nets]
    t.order = order
    t.route_nets(nets, order, unl)
    t.join_stripes()
    t.shields()
    # one point per block end of every net (layer, x, y um, inst.pin), for the extraction's net labels
    # (layout/gen/pex_tile.sh): only the top cell's labels name nets after flatten -dotoplabels
    t.log['net_points'] = {n: [(t.inst[i]['pins'][p][0], t.inst[i]['pins'][p][1] / 1000,
                                t.inst[i]['pins'][p][2] / 1000, f'{i}.{p}')
                               for i, p in e if i != 'PIN' and i in t.inst and p in t.inst[i]['pins']]
                           for n, e in allnets.items()}
    # probes inside vco_core (its plain labels, not ports): the ring's a0 (lsdiv's tap) and a2 (the Q level
    # shifter's tap), so the extracted tile's testbench can measure the ring there
    if 'vco.core' in t.inst:
        for n in ('a2', 'a0'):
            if n in t.inst['vco.core']['pins'] and n not in t.log['net_points']:
                l, x, y = t.inst['vco.core']['pins'][n][:3]
                t.log['net_points'][n] = [(l, x / 1000, y / 1000, f'vco.core.{n} (probe)')]
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--partial', action='store_true', help='skip blocks whose GDS is missing (development)')
    ap.add_argument('--no-png', action='store_true')
    ap.add_argument('--fp', default=None, help='floorplan.json to read (default layout/floorplan/floorplan.json)')
    ap.add_argument('--tries', type=int, default=10, help='rip-up rounds: failed nets move to the front')
    a = ap.parse_args()
    global FP
    if a.fp:
        FP = Path(a.fp)
    import time
    t0 = time.time()
    order = None
    for k in range(a.tries):
        t = build(a.partial, order, quiet=k > 0)
        bad = [u.split(' ')[0] for u in t.log['unrouted']]
        print(f'round {k + 1}: unrouted {t.log["unrouted"]}  ({time.time() - t0:.0f} s)', flush=True)
        if not bad:
            break
        order = [n for n in bad if n in t.order] + [n for n in t.order if n not in bad]
    t.log['rounds'] = k + 1
    print('skipped (missing ends):', t.log['skipped'])
    t.draw_routes()
    t.decap()
    print('decap:', t.log['decap'])
    gds = OUT / f'{TOP}_dev.gds' if a.partial else REPO / 'gds' / f'{TOP}.gds'
    lef = OUT / f'{TOP}_dev.lef' if a.partial else REPO / 'lef' / f'{TOP}.lef'
    t.write(gds)
    t.write_lef(lef)
    # DCF.1a (no 20 x 20 um without COMP): dummy COMP squares in the free areas (layout/gen/rx_fill.py)
    import rx_fill
    t.log['fill_squares'] = rx_fill.fill(str(gds), TOP, margin=1.0)
    (OUT / 'meta.json').write_text(json.dumps(t.log, indent=1, default=str))
    if t.log['unrouted']:
        print('UNROUTED:', t.log['unrouted'])


if __name__ == '__main__':
    main()
