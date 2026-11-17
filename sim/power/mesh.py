"""Resistor mesh of each supply net of the tile, with TT's Metal5 straps and power switches, as sparse matrices.

Port of ook-asic-radio's sim/power/mesh.py (sky130) to GF180 and to a direct numpy / scipy solve. KLayout traces
each supply net from its Metal4 stripe labels (Metal1-Metal4, Via1-Via3, contacts), each metal is rasterized on a
P um grid, neighbouring cells of a layer are joined by G = coverage / Rsheet, and the cells of two layers by
(cuts in the cell) / Rcut. Contacts are not resistors here: a cell with a contact on the net is where the block's
devices draw their current (the probe / sink points).

TT's part (tt-multiplexer 885086c, ol2/tt_top/odb_route.py ModulePowerStrapper, py/tt/elements.py, layout.py):
- the switches sit west of the tile (VDPWR switch outermost, then the VAPWR switch next to the tile);
- each switch's output feeds two Metal5 straps across the tile, a narrow one (8.75 um) at y_mid +/- 5.5 um and a
  wide one (19.75 um) at y_mid -/+ 82.32 um; a Via4 array lands wherever a strap crosses its own net's Metal4 pin;
- VGND comes from the chip's Metal5 grid, 8.75 um stripes at y_mid +/- 41.16 and +/- 123.48 um (by analogy with
  the sky130 tile, where it was read from the GDS: assumed for GF).
Which switch gets which pair (pin order, N / FS orientation) is not known: case A = VDPWR narrow above y_mid
(168.18) and wide below (80.36), VAPWR narrow at 157.18 and wide at 245.00; case B swaps the two.

    python3 sim/power/mesh.py [P]     (default 0.5 um) -> build/power/mesh_p<P>/<net>.npz
Env for the mutation tests and what-ifs: MUT=<tag> with MUT_CUT='x0,y0,x1,y1;...' (boxes removed from Metal1-4 of
every supply net), MUT_NARROW='x_left:keep_um' (that Metal4 stripe cut to keep_um width), MUT_RS=k (sheet R x k).
"""
import json
import os
import sys

import numpy as np
import klayout.db as db

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
GDS = os.path.join(ROOT, 'gds', 'tt_um_mattvenn_gf433_vco.gds')
META = os.path.join(ROOT, 'build', 'tile', 'meta.json')
P = float(sys.argv[1]) if len(sys.argv) > 1 else 0.5
TAG = os.environ.get('MUT', '')
OUT = os.path.join(ROOT, 'build', 'power', f'mesh_p{P:g}' + (f'_{TAG}' if TAG else ''))
DBU = 0.001
RS_K = float(os.environ.get('MUT_RS', '1'))
# sheet R (ohm/sq) and per-cut R (ohm), cut size (um): gf180mcuD tech LEF (gf180mcu_fd_sc_mcu7t5v0__nom.tlef,
# same as magic gf180mcuD.tech): Metal1-4 0.090, Metal5 0.060 (magic 0.040), Via1-4 4.5 ohm, 0.26 um cut
LAY = [('m1', (34, 0), 0.090), ('m2', (36, 0), 0.090), ('m3', (42, 0), 0.090), ('m4', (46, 0), 0.090)]
CUT = [('v1', (35, 0), 4.5, 0.26), ('v2', (38, 0), 4.5, 0.26), ('v3', (40, 0), 4.5, 0.26)]
CO = ('co', (33, 0))
TEXT = (46, 10)
NETS = ('VDPWR', 'VAPWR', 'VGND')
RS5, RV4, V4_CUT, V4_PITCH, V4_ENC = 0.060, 4.5, 0.26, 0.62, 0.12   # Metal5 / Via4 (LEF: array spacing 0.36)
YMID, PITCH5, W_N, W_W = 162.68, 82.32, 8.75, 19.75


def main():
    meta = json.load(open(META))
    ly = db.Layout()
    ly.read(GDS)
    top = ly.top_cell()
    l2n = db.LayoutToNetlist(db.RecursiveShapeIterator(ly, top, []))
    L = {n: l2n.make_layer(ly.layer(*d), n) for n, d, _ in LAY}
    C = {n: l2n.make_layer(ly.layer(*d), n) for n, d, _, _ in CUT}
    C['co'] = l2n.make_layer(ly.layer(*CO[1]), 'co')
    # mutations: boxes cut out of Metal1-4, a stripe narrowed
    cut = db.Region()
    for b in filter(None, os.environ.get('MUT_CUT', '').split(';')):
        x0, y0, x1, y1 = map(float, b.split(','))
        cut.insert(db.DBox(x0, y0, x1, y1).to_itype(DBU))
    if os.environ.get('MUT_NARROW'):
        xl, keep = map(float, os.environ['MUT_NARROW'].split(':'))
        w = [s[2] for s in meta['stripes'] if abs(s[1] - xl) < 0.01][0]
        cut.insert(db.DBox(xl + keep, 5.0, xl + w + 0.01, 320.36).to_itype(DBU))
    if not cut.is_empty():
        for n in L:
            L[n] = L[n] - cut
            l2n.register(L[n], n + '_mut')
    l2n.connect(l2n.make_text_layer(ly.layer(*TEXT), 'm4t'), L['m4'])
    seq = ['co', 'm1', 'v1', 'm2', 'v2', 'm3', 'v3', 'm4']
    allL = {**L, **C}
    for n in seq:
        l2n.connect(allL[n])
    for a, b in zip(seq, seq[1:]):
        l2n.connect(allL[a], allL[b])
    l2n.extract_netlist()
    circ = l2n.netlist().circuit_by_name(top.name)
    bb = top.dbbox()
    nx, ny = int(bb.width() / P) + 2, int(bb.height() / P) + 2
    px = int(round(P / DBU))
    org = db.Point(0, 0)

    def raster(reg):
        if reg.is_empty():
            return np.zeros((ny, nx))
        a = reg.rasterize(org, db.Vector(px, px), db.Vector(px, px), nx, ny)
        return np.array(a, dtype=float) * (DBU * DBU) / (P * P)

    os.makedirs(OUT, exist_ok=True)
    stripes = meta['stripes']
    for netname in NETS:
        nets = [n for n in circ.each_net() if netname in n.expanded_name().split(',')]
        assert len(nets) >= 1, netname
        # a net can come out as several (islands with their own label): keep each label's net
        cov = []
        for n_, _, _ in LAY:
            r = db.Region()
            for net in nets:
                r += l2n.shapes_of_net(net, L[n_], True)
            cov.append(raster(r.merged()))
        cuts = []
        for n_, _, _, _ in CUT:
            r = db.Region()
            for net in nets:
                r += l2n.shapes_of_net(net, C[n_], True)
            cuts.append(raster(r.merged()) * (P * P) / (0.26 * 0.26))
        r = db.Region()
        for net in nets:
            r += l2n.shapes_of_net(net, C['co'], True)
        co = raster(r.merged()) * (P * P) / (0.22 * 0.22)
        live = [c > 0.02 for c in cov]
        # node numbering: layer k cell (iy, ix) -> id
        ids = []
        nn = 0
        for k in range(len(LAY)):
            a = -np.ones((ny, nx), dtype=np.int64)
            m = live[k]
            a[m] = np.arange(nn, nn + int(m.sum()))
            nn += int(m.sum())
            ids.append(a)
        I, J, G, kind = [], [], [], []
        for k, (ln, _, rs) in enumerate(LAY):
            c, m = cov[k], live[k]
            for dy, dx in ((0, 1), (1, 0)):
                a = m[:ny - dy, :nx - dx] & m[dy:, dx:]
                ys, xs = np.nonzero(a)
                g = np.minimum(c[ys, xs], c[ys + dy, xs + dx]) / (rs * RS_K)
                I.append(ids[k][ys, xs]); J.append(ids[k][ys + dy, xs + dx]); G.append(g)
                kind.append(np.full(len(g), k))
        for k, (cn, _, rc, cs) in enumerate(CUT):
            a = (cuts[k] > 0) & live[k] & live[k + 1]
            ys, xs = np.nonzero(a)
            g = cuts[k][ys, xs] / rc        # fractional cut count: a cut split over cells sums to one cut
            I.append(ids[k][ys, xs]); J.append(ids[k + 1][ys, xs]); G.append(g)
            kind.append(np.full(len(g), 10 + k))
        # Metal5: per strap, one node per Metal4 pin it crosses (pin = a tile stripe of this net), joined by
        # Metal5 R; Via4 arrays spread over the Metal4 cells of the crossing
        pins = [(s[1], s[2]) for s in stripes if s[0] == netname]
        m5 = []          # (strap name, y, w, [node ids], [x])
        extra = []       # Metal5 / via4 edges as (a, b, g, kind)
        node_xy = {}

        def straps(case):
            if netname == 'VGND':
                return [('gnd%d' % i, YMID + d, W_N) for i, d in enumerate((-1.5 * PITCH5, -0.5 * PITCH5,
                                                                             0.5 * PITCH5, 1.5 * PITCH5))]
            up = (netname == 'VDPWR') == (case == 'A')
            s = 1 if up else -1
            return [('n', YMID + s * 5.5, W_N), ('w', YMID - s * PITCH5, W_W)]

        out = {}
        for case in ('A', 'B'):
            nid = nn
            E = []
            straps_c = []
            for nm, yc, w in straps(case):
                y0, y1 = yc - w / 2, yc + w / 2
                iy0, iy1 = int(np.ceil(y0 / P)), int(np.floor(y1 / P))
                nodes, xs_ = [], []
                for xl, wp in pins:
                    ix0, ix1 = int(np.floor(xl / P)), int(np.ceil((xl + wp) / P))
                    sub = ids[3][iy0:iy1, ix0:ix1]
                    cells = sub[sub >= 0]
                    if len(cells) == 0:
                        continue
                    ncx = max(1, int((wp - 2 * V4_ENC + 0.36) // V4_PITCH))
                    ncy = max(1, int((w - 2 * V4_ENC + 0.36) // V4_PITCH))
                    gv = ncx * ncy / RV4
                    for cid in cells:
                        E.append((nid, int(cid), gv / len(cells), 20))
                    nodes.append(nid); xs_.append(xl + wp / 2)
                    nid += 1
                for a_, b_, xa, xb in zip(nodes, nodes[1:], xs_, xs_[1:]):
                    E.append((a_, b_, w / (RS5 * (xb - xa)), 21))
                straps_c.append((nm, yc, w, nodes, xs_))
            out[case] = (straps_c, E, nid)
        np.savez_compressed(os.path.join(OUT, f'{netname}.npz'),
                            I=np.concatenate(I), J=np.concatenate(J), G=np.concatenate(G), K=np.concatenate(kind),
                            ids=np.stack(ids), cov=np.stack(cov), co=co, nn=nn, P=P, nx=nx, ny=ny)
        json.dump({c: {'straps': [[nm, yc, w, nodes, xs_] for nm, yc, w, nodes, xs_ in v[0]],
                       'E': v[1], 'n': v[2]} for c, v in out.items()},
                  open(os.path.join(OUT, f'{netname}_m5.json'), 'w'))
        print(f'{netname}: {len(nets)} labelled net(s), {nn} mesh nodes, {sum(len(x) for x in G)} R, '
              f'Metal5 landings A {[len(s[3]) for s in out["A"][0]]}', flush=True)


main()
