#!/usr/bin/env python3
"""Layout of the receiver top level rx_top: the block cells, the supply decap, power and routing, gf180mcuD.

    python3 layout/gen/rx_top.py [--out build/rx_layout/gen/rx_top] [--gds layout/rx_top.gds]

Circuit: sim/rx/rx_top.py (= xschem/rx_top.sch). The block cells come from their generators (layout/gen/rx_*.py,
built in-process), the decap DC (12 x 10/10 um nfet gate caps, gate VDD) is a small cell made here (rx_decap).

Floorplan (x right, y up; signal flows up, I and Q side by side above the front end):
  row C   lim_i | lim_q                         comparators: the noisy end, q_i / q_q leave through the top edge
  row B   bb_i  | bb_q                          the baseband arms (their cap band at the bottom faces the LO buffers)
  row A   LNA (bias and decap above it) | mixer column | rx_lsq
          mixer column, bottom to top: mix_q, lobuf_q, mix_i, lobuf_i. The LNA's Q outputs leave its bottom band and
          its I outputs its top band, so each mixer sits level with its LNA stage 2 and the two RF routes are short
          and alike. Each LO buffer sits right on its mixer (lo / lob straight down on M3), and takes its LO input
          from the right, away from the LNA: lsq from rx_lsq next to it, ls from the cell's right edge.
  Why not the handoff's proposal (I and Q as two rows, signal flowing left to right): the baseband arm is
  146 x 143 um, so two such rows would be 290 um tall with the mixers and limiters (36 and 67 um tall) leaving most
  of them empty; stacking the arms side by side wastes less (see docs/rx_layout.md).
Power: a VDD / VSS bus pair (M2, 2.5 um) below row A, in each gap between rows and above row C; M3 straps
(2.5 um) on the left side of every block column from bus to bus; an M2 stub from the strap of each net into every
rail of that net at the block's left edge. One VDD and one VSS for the whole receiver (its own pins).
Signals: a maze router on M2 (horizontal) / M3 (vertical) at the 0.68 um track pitch in the gaps between blocks;
each block pin reaches the grid through a short stub. No Metal4 / Metal5.
Pins: VDD, VSS (M2, bottom buses), inp, inn (left edge), ls, en, aq (right edge), q_i, q_q (top edge).
"""
import argparse
import heapq
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import rx_lib as R  # noqa: E402
from ring_core import Cell  # noqa: E402

P = 680                  # routing grid pitch (nm): 380 wires, 300 space
HW = 190
CLR = HW + 300           # node to obstacle clearance
GV, GH = 12000, 18000    # gaps between blocks in a row / between rows
STACK = 6000             # gap between blocks stacked in one column of row A
LGAP = 2000              # mixer top to its LO buffer
BUSW, STRAPW = 2500, 2500
M = 12000                # margin around the core (outer straps, buses, port stubs)


# ---- block cells ---------------------------------------------------------------------------------------------------
def decap_cell():
    """rx_decap: the receiver supply decap (rx_top's DC: 12 x 10/10 um nfet gate caps, gate VDD, S/D/B VSS),
    drawn as 2 bands of 5 fingers of 12 um (the same 1200 um2 of gate: netgen adds parallel widths)."""
    d = R.dev(R.sim_cells()['rx_top'], 'DC')
    assert d['nets'] == ['VSS', 'VDD', 'VSS', 'VSS'] and abs(d['w'] * d['m'] - 120) < 1e-6
    wf, nf = 12.0, 5
    seq = ['VSS'] + ['VDD', 'VSS'] * nf
    cell = Cell('rx_decap')
    bands = [R.Band(f'dc{k}', [('DC', [], [R.mos(wf, d['l'], seq, 'VSS')])], search=False) for k in range(2)]
    metas, bb = R.stack(cell, bands, [{}, {}])
    return cell, dict(bbox=bb, bands=metas)


def blocks():
    """{name: (cells, meta)} of every block generator, built in-process."""
    out = {}
    for b in ('rx_bias', 'rx_lna', 'rx_lsq', 'rx_lobuf', 'rx_mix', 'rx_bb', 'rx_lim'):
        out[b] = R.load_gen(b).build()
    c, m = decap_cell()
    out['rx_decap'] = ([c], m)
    return out


def pins_of(name, meta):
    """[(net, x, y, side)] of a block's pins on its outer edges (block coordinates); side left/right (M2) or
    top/bottom (M3)."""
    bb = meta['bbox']
    out = []
    if name == 'rx_lsq':
        out.append(('aq', bb[2], R.LL.A0_Y, 'right'))
        out.append(('lsq', meta['ls_x'], bb[3], 'top'))
        out.append(('qenb', meta['xq'], bb[3], 'top'))
        return out
    for band in meta['bands']:
        for net, lst in band['pins'].items():
            for x, y, edge in lst:
                if edge == 'left' and x == bb[0]:
                    out.append((net, x, y, 'left'))
                elif edge == 'right' and x == bb[2]:
                    out.append((net, x, y, 'right'))
                elif y == bb[3]:
                    out.append((net, x, y, 'top'))
                elif y == bb[1]:
                    out.append((net, x, y, 'bottom'))
    return sorted(set(out))


def rails_of(name, meta):
    """[(net, y0, y1, xstart)] of a block's VDD / VSS rails (block coordinates); xstart = where the rail's M2
    begins (0 for rx_lib bands, 300 for lsdiv's)."""
    out = []
    if name == 'rx_lsq':
        Y = meta['lsdiv']['Y']
        out += [('VSS', Y['vss_b'], Y['vss_t'], 300), ('VSS', Y['vss2_b'], Y['vss2_t'], 300)]
        for net, (y0, y1), skip in meta['band']['rails']:
            if net == 'VDD':
                out.append(('VDD', y0, y1, 0))
        return out
    seen = set()
    for band in meta['bands']:
        for net, (y0, y1), skip in band['rails']:
            if (y0, y1) not in seen:
                seen.add((y0, y1))
                out.append((net, y0, y1, 0))
    return out


# ---- the maze router -----------------------------------------------------------------------------------------------
class Grid:
    def __init__(self, x0, y0, x1, y1):
        self.x0, self.y0 = x0 // P * P, y0 // P * P
        self.nx, self.ny = (x1 - self.x0) // P + 1, (y1 - self.y0) // P + 1
        self.own = {}                 # (l, i, j) -> owner (-1 obstacle, k net id)

    def X(self, i):
        return self.x0 + i * P

    def Yc(self, j):
        return self.y0 + j * P

    def ij(self, x, y):
        return round((x - self.x0) / P), round((y - self.y0) / P)

    def block(self, l, x0, y0, x1, y1, owner=-1, clr=CLR):
        i0 = max(0, -(-(x0 - clr - self.x0) // P))
        i1 = min(self.nx - 1, (x1 + clr - self.x0) // P)
        j0 = max(0, -(-(y0 - clr - self.y0) // P))
        j1 = min(self.ny - 1, (y1 + clr - self.y0) // P)
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                if owner == -1 or (l, i, j) not in self.own:
                    self.own[(l, i, j)] = owner

    def free(self, n, net):
        o = self.own.get(n)
        return o is None or o == net

    def route(self, srcs, dsts, net):
        """A* from any of srcs to any of dsts (sets of (l, i, j)); M2 (l 0) prefers x, M3 (l 1) prefers y."""
        dl = list(dsts)
        h = lambda n: min(abs(n[1] - d[1]) + abs(n[2] - d[2]) for d in dl[:64])
        pq = [(h(s), 0, s) for s in srcs]
        heapq.heapify(pq)
        prev = {s: None for s in srcs}
        cost = {s: 0 for s in srcs}
        while pq:
            f, g, n = heapq.heappop(pq)
            if n in dsts:
                path = []
                while n is not None:
                    path.append(n)
                    n = prev[n]
                return path[::-1]
            if g > cost.get(n, 1 << 60):
                continue
            l, i, j = n
            for (nl, ni, nj, c) in ((l, i + 1, j, 1 if l == 0 else 3), (l, i - 1, j, 1 if l == 0 else 3),
                                    (l, i, j + 1, 1 if l == 1 else 3), (l, i, j - 1, 1 if l == 1 else 3),
                                    (1 - l, i, j, 4)):
                if not (0 <= ni < self.nx and 0 <= nj < self.ny):
                    continue
                m = (nl, ni, nj)
                if not self.free(m, net):
                    continue
                if nl != l and not self.free((l, i, j), net):
                    continue
                g2 = g + c
                if g2 < cost.get(m, 1 << 60):
                    cost[m] = g2
                    prev[m] = n
                    heapq.heappush(pq, (g2 + h(m), g2, m))
        return None


# ---- build ---------------------------------------------------------------------------------------------------------
def build():
    B = blocks()
    meta = {k: v[1] for k, v in B.items()}
    bb = {k: m['bbox'] for k, m in meta.items()}
    W = lambda k: bb[k][2] - bb[k][0]
    H = lambda k: bb[k][3] - bb[k][1]
    mix_dx = meta['rx_lobuf']['mix_dx']
    # ---- placement: (cell, x, y) of each instance's bbox lower-left; every origin on the routing grid (the
    # blocks' tracks and exits are on it in their own coordinates, layout/gen/rx_lib.py), rx_lsq's offset so that
    # its aq and lsq pins land on it ----
    def at(c, x, y, rx=0, ry=0, ax=True, ay=True):
        ox, oy = x - bb[c][0], y - bb[c][1]
        if ax:
            ox += (rx - ox) % P
        if ay:
            oy += (ry - oy) % P
        return (c, ox + bb[c][0], oy + bb[c][1])
    place = {}
    place['lna'] = at('rx_lna', 0, 0)
    place['b'] = at('rx_bias', 0, place['lna'][2] + H('rx_lna') + STACK)
    place['dc'] = at('rx_decap', W('rx_bias') + 16000, place['b'][2])
    xc = place['lna'][1] + W('rx_lna') + GV                   # mixer column (the LO buffers' left edge)
    lna_oq = [y for (n, x, y, s) in pins_of('rx_lna', meta['rx_lna']) if n == 'oqp'][0] - bb['rx_lna'][1]
    mix_rf = [y for (n, x, y, s) in pins_of('rx_mix', meta['rx_mix']) if n == 'rfp'][0] - bb['rx_mix'][1]
    yq = max(0, lna_oq - mix_rf)
    place['lo_bq'] = at('rx_lobuf', xc, yq + H('rx_mix') + LGAP, ax=False)
    place['mq'] = at('rx_mix', xc + mix_dx, place['lo_bq'][2] - LGAP - H('rx_mix'), ax=False)
    assert place['lo_bq'][2] - (place['mq'][2] + H('rx_mix')) >= 1500
    place['mi'] = at('rx_mix', xc + mix_dx, place['lo_bq'][2] + H('rx_lobuf') + 4000, ax=False)
    place['lo_bi'] = at('rx_lobuf', xc, place['mi'][2] + H('rx_mix') + LGAP, ax=False)
    assert place['lo_bi'][2] - (place['mi'][2] + H('rx_mix')) >= 1500
    lsq = meta['rx_lsq']
    place['lo_lq'] = at('rx_lsq', xc + W('rx_lobuf') + GV, 0, rx=-lsq['ls_x'] % P, ry=-R.LL.A0_Y % P)
    topA = max(y + H(c) for (c, x, y) in place.values())
    yB = topA + GH
    place['bbi'] = at('rx_bb', 0, yB)
    place['bbq'] = at('rx_bb', W('rx_bb') + GV, yB)
    yC = max(place[n][2] for n in ('bbi', 'bbq')) + H('rx_bb') + GH
    place['li'] = at('rx_lim', 0, yC)
    place['lq'] = at('rx_lim', W('rx_lim') + GV, yC)
    topC = max(place[n][2] for n in ('li', 'lq')) + H('rx_lim')
    width = max(x + W(c) for (c, x, y) in place.values())
    top = Cell('rx_top')
    for name, (c, x, y) in place.items():
        top.inst(c, x - bb[c][0], y - bb[c][1], name)
    core = (0, 0, width, topC)
    # ---- power: buses, straps, stubs ----
    yB, yC = place['bbi'][2], place['li'][2]
    rows = [(-M, 0), (topA, yB), (yB + H('rx_bb'), yC), (topC, topC + M)]    # gaps (y_lo, y_hi)
    bus = {}                                                  # gap index -> {net: (y0, y1)}
    for k, (ylo, yhi) in enumerate(rows):
        if k < len(rows) - 1:                                 # bus pair at the top of the gap
            yv1 = yhi - 1000
            yv0 = yv1 - BUSW
            ys1 = yv0 - 600
            ys0 = ys1 - BUSW
        else:                                                 # above row C: at the bottom of the gap
            ys0 = ylo + 1000
            ys1 = ys0 + BUSW
            yv0 = ys1 + 600
            yv1 = yv0 + BUSW
        bus[k] = dict(VSS=(ys0, ys1), VDD=(yv0, yv1))
        for net, (y0, y1) in bus[k].items():
            top.r('m2', -M + 1000, y0, width + M - 1000, y1)
    for net in ('VDD', 'VSS'):
        y0, y1 = bus[0][net]
        top.label(net, 'm2', -M + 3000, (y0 + y1) // 2, port=True)
    # strap columns: (x of the column's left edge, gap below, gap above, [instances])
    cols = [(0, 0, 1, ['lna', 'b']), (place['dc'][1], None, 1, ['dc']),
            (place['lo_bq'][1], 0, 1, ['mq', 'lo_bq', 'mi', 'lo_bi']),
            (place['lo_lq'][1], 0, 1, ['lo_lq']), (0, 1, 2, ['bbi']), (place['bbq'][1], 1, 2, ['bbq']),
            (0, 2, 3, ['li']), (place['lq'][1], 2, 3, ['lq'])]
    obst = []                                                 # (layer, rect) for the router
    for k, d in bus.items():
        for net, (y0, y1) in d.items():
            obst.append(('m2', (-M + 1000, y0, width + M - 1000, y1)))
    for (xl, glo, ghi, insts) in cols:
        sx = dict(VDD=(xl - 1000 - STRAPW, xl - 1000), VSS=(xl - 2000 - 2 * STRAPW, xl - 2000 - STRAPW))
        ylo = bus[glo]['VSS'][0] if glo is not None else min(place[n][2] for n in insts) - 500
        yhi = bus[ghi]['VDD'][1]
        for net, (a, b2) in sx.items():
            top.r('m3', a, ylo, b2, yhi)
            obst.append(('m3', (a, ylo, b2, yhi)))
            for g in (glo, ghi):
                if g is None:
                    continue
                y0, y1 = bus[g][net]
                x = a + 300
                while x + 300 <= b2:
                    yy = y0 + 300
                    while yy + 300 <= y1:
                        top.r('v2', x, yy, x + 280, yy + 280)
                        yy += 700
                    x += 700
        for n in insts:
            c, x, y = place[n]
            ox, oy = x - bb[c][0], y - bb[c][1]
            for net, r0, r1, xs in rails_of(c, meta[c]):
                ya, yb2 = oy + r0 + 600, oy + r1 - 600
                a, b2 = sx[net]
                top.r('m2', a, ya, ox + xs + 600, yb2)
                obst.append(('m2', (a, ya, ox + xs + 600, yb2)))
                x = a + 300
                while x + 300 <= b2:
                    top.r('v2', x, (ya + yb2) // 2 - 140, x + 280, (ya + yb2) // 2 + 140)
                    x += 700
    # ---- signal nets: block pins (global) ----
    gp = {}                                                   # (inst, pin) -> (x, y, side)
    for n, (c, x, y) in place.items():
        ox, oy = x - bb[c][0], y - bb[c][1]
        for (net, px, py, side) in pins_of(c, meta[c]):
            gp[(n, net)] = (ox + px, oy + py, side)
    nets = {
        'ri_p': [('lna', 'oip'), ('mi', 'rfp')], 'ri_n': [('lna', 'oin'), ('mi', 'rfn')],
        'rq_p': [('lna', 'oqp'), ('mq', 'rfp')], 'rq_n': [('lna', 'oqn'), ('mq', 'rfn')],
        'lsq': [('lo_lq', 'lsq'), ('lo_bq', 'in')],
        'bi_p': [('mi', 'bbp'), ('bbi', 'inp')], 'bi_n': [('mi', 'bbn'), ('bbi', 'inn')],
        'bq_p': [('mq', 'bbp'), ('bbq', 'inp')], 'bq_n': [('mq', 'bbn'), ('bbq', 'inn')],
        'oi_p': [('bbi', 'outp'), ('li', 'inp')], 'oi_n': [('bbi', 'outn'), ('li', 'inn')],
        'oq_p': [('bbq', 'outp'), ('lq', 'inp')], 'oq_n': [('bbq', 'outn'), ('lq', 'inn')],
        'nb': [('b', 'nb'), ('lna', 'nb'), ('bbi', 'nb'), ('bbq', 'nb'), ('li', 'nb'), ('lq', 'nb')],
        'enb': [('b', 'enb'), ('lna', 'enb'), ('bbi', 'enb'), ('bbq', 'enb'), ('li', 'enb'), ('lq', 'enb')],
        'en': [('b', 'en'), ('lo_bi', 'en'), ('lo_bq', 'en'), ('PORT', 'en')],
        'inp': [('lna', 'inp'), ('PORT', 'inp')], 'inn': [('lna', 'inn'), ('PORT', 'inn')],
        'ls': [('lo_bi', 'in'), ('PORT', 'ls')], 'aq': [('lo_lq', 'aq'), ('PORT', 'aq')],
        'q_i': [('li', 'q'), ('PORT', 'q_i')], 'q_q': [('lq', 'q'), ('PORT', 'q_q')],
    }
    # ports on the cell boundary: (side, coordinate along it)
    x_lo, x_hi, y_lo, y_hi = -M, width + M, -M, topC + M
    ports = {'inp': ('left', gp[('lna', 'inp')][1]), 'inn': ('left', gp[('lna', 'inn')][1]),
             'ls': ('right', gp[('lo_bi', 'in')][1]), 'en': ('right', gp[('lo_bi', 'en')][1]),
             'aq': ('right', gp[('lo_lq', 'aq')][1]),
             'q_i': ('top', gp[('li', 'q')][0]), 'q_q': ('top', gp[('lq', 'q')][0])}
    # the lo / lob jumpers (mixer top to its LO buffer's bottom, same x by construction) and qenb -> VSS bus
    for m_, lb in (('mi', 'lo_bi'), ('mq', 'lo_bq')):
        for p in ('lo', 'lob'):
            xm, ym, _ = gp[(m_, p)]
            xb, yb_, _ = gp[(lb, p)]
            assert xm == xb, (m_, p, xm, xb)
            top.r('m3', xm - 190, ym - 200, xm + 190, yb_ + 200)
            top.label({'mi': 'lo_i', 'mq': 'lo_q'}[m_].replace('lo', p), 'm3', xm, R.snap((ym + yb_) / 2))
    xq, yq_, _ = gp[('lo_lq', 'qenb')]
    vy0, vy1 = bus[1]['VSS']
    top.r('m3', xq - 190, yq_ - 200, xq + 190, vy1)
    top.r('v2', xq - 140, (vy0 + vy1) // 2 - 140, xq + 140, (vy0 + vy1) // 2 + 140)
    ids = {net: k + 1 for k, net in enumerate(nets)}

    def attempt(order):
        """Route every net in `order` on a fresh grid. Returns (G, pinlist, trees, stub shapes, failed net)."""
        G = Grid(x_lo, y_lo, x_hi, y_hi)
        for n, (c, x, y) in place.items():
            G.block(0, x, y, x + W(c), y + H(c), clr=CLR + 300)
            G.block(1, x, y, x + W(c), y + H(c), clr=CLR + 300)
        for l, (a, b0, c0, d0) in obst:
            G.block(0 if l == 'm2' else 1, a, b0, c0, d0)
        G.block(1, xq - 190, yq_, xq + 190, vy1)
        acc = []

        def pin_access(net, x, y, side):
            """A straight stub from an on-grid pin out of its block's halo to the first free grid node. Left / right
            pins (M2) end on M3 (a via up at the stub's end, no M2 beyond it): the route never joins a gate's M2 stub
            on M2, so a long M2 run can't become that gate's antenna. The M3 nodes above and below that end must be
            free too, so pins on neighbouring tracks end in different columns."""
            nid = ids[net]
            i0, j0 = G.ij(x, y)
            if side in ('top', 'bottom'):
                assert G.X(i0) == x, (net, side, x)
                step = 1 if side == 'top' else -1
                j = G.ij(x, y + step * (CLR + 800))[1]
                while not G.free((1, i0, j), nid):
                    j += step
                for jj in range(min(j, j0), max(j, j0) + 1):
                    o = G.own.get((1, i0, jj))
                    assert o in (None, nid, -1), (net, 'stub crosses', o)
                    if o != -1:
                        G.own[(1, i0, jj)] = nid
                acc.append(('m3', x - 190, min(y, G.Yc(j)) - 190, x + 190, max(y, G.Yc(j)) + 190))
                return (1, i0, j)
            assert G.Yc(j0) == y, (net, side, y)
            step = 1 if side == 'right' else -1
            i = G.ij(x + step * (CLR + 800), y)[0]
            while not (G.free((0, i, j0), nid) and all(G.free((1, i, jj), nid) for jj in (j0 - 1, j0, j0 + 1))):
                i += step
            for ii in range(min(i, i0), max(i, i0) + 1):
                o = G.own.get((0, ii, j0))
                assert o in (None, nid, -1), (net, 'stub crosses', o)
                if o != -1:
                    G.own[(0, ii, j0)] = nid
            acc.append(('m2', min(x, G.X(i)) - 190, y - 190, max(x, G.X(i)) + 190, y + 190))
            acc.append(('v2', G.X(i) - 140, y - 140, G.X(i) + 140, y + 140))
            acc.append(('m3', G.X(i) - 190, y - 190, G.X(i) + 190, y + 190))
            G.own[(0, i + step, j0)] = -1
            G.own[(1, i, j0)] = nid
            return (1, i, j0)

        def port_node(net, side, coord):
            nid = ids[net]
            if side == 'left':
                n = (0, 1, G.ij(0, coord)[1])
            elif side == 'right':
                n = (0, G.nx - 2, G.ij(0, coord)[1])
            else:
                n = (1, G.ij(coord, 0)[0], G.ny - 2)
            G.own[n] = nid
            return n
        pinlist = {}
        for net, ps in nets.items():
            pinlist[net] = []
            for (inst, p) in ps:
                if inst == 'PORT':
                    side, coord = ports[p]
                    pinlist[net].append(('port', port_node(net, side, coord), side))
                else:
                    x, y, side = gp[(inst, p)]
                    pinlist[net].append(('pin', pin_access(net, x, y, side), side))
        trees = {}
        for net in order:
            nid = ids[net]
            pl = [p[1] for p in pinlist[net]]
            tree = {pl[0]}
            segs = []
            rest = pl[1:]
            while rest:
                rest.sort(key=lambda n: min(abs(n[1] - t[1]) + abs(n[2] - t[2]) for t in tree))
                src = rest.pop(0)
                path = G.route({src}, tree, nid)
                if path is None:
                    return G, pinlist, trees, acc, net
                segs.append(path)
                tree |= set(path)
                for n in path:
                    G.own[n] = nid
            trees[net] = segs
        return G, pinlist, trees, acc, None

    # route: the RF and LO nets first (short, straight), then the rest by number of pins; a net that fails moves
    # to the front and everything is routed again
    order = sorted(nets, key=lambda n: (0 if n.startswith(('ri', 'rq', 'lsq')) else 1, len(nets[n])))
    for k in range(len(nets)):
        G, pinlist, trees, acc, failed = attempt(order)
        if failed is None:
            break
        print(f'rx_top: {failed} unrouted, routing it earlier', flush=True)
        order.remove(failed)
        order.insert(0, failed)
    else:
        raise SystemExit(f'rx_top: unrouted net {failed}')
    for sh in acc:
        top.r(*sh)
    # emit wires
    for net, segs in trees.items():
        for path in segs:
            for a, b2 in zip(path, path[1:]):
                if a[0] != b2[0]:
                    x, y = G.X(a[1]), G.Yc(a[2])
                    top.r('m2', x - 190, y - 190, x + 190, y + 190)
                    top.r('m3', x - 190, y - 190, x + 190, y + 190)
                    top.r('v2', x - 140, y - 140, x + 140, y + 140)
                else:
                    lay = 'm2' if a[0] == 0 else 'm3'
                    xa, ya, xb, yb2 = G.X(a[1]), G.Yc(a[2]), G.X(b2[1]), G.Yc(b2[2])
                    top.r(lay, min(xa, xb) - 190, min(ya, yb2) - 190, max(xa, xb) + 190, max(ya, yb2) + 190)
        if segs:
            n0 = segs[0][0]
            top.label(net, 'm2' if n0[0] == 0 else 'm3', G.X(n0[1]), G.Yc(n0[2]))
    # port stubs to the boundary and labels
    for net, (side, coord) in ports.items():
        n = [p[1] for p in pinlist[net] if p[0] == 'port'][0]
        x, y = G.X(n[1]), G.Yc(n[2])
        if side == 'left':
            top.r('m2', x_lo, y - 190, x + 190, y + 190)
            top.label(net, 'm2', x_lo + 150, y, port=True)
        elif side == 'right':
            top.r('m2', x - 190, y - 190, x_hi, y + 190)
            top.label(net, 'm2', x_hi - 150, y, port=True)
        else:
            top.r('m3', x - 190, y - 190, x + 190, y_hi)
            top.label(net, 'm3', x, y_hi - 150, port=True)
    cells = []
    for k in ('rx_bias', 'rx_lna', 'rx_lsq', 'rx_lobuf', 'rx_mix', 'rx_bb', 'rx_lim', 'rx_decap'):
        cells += B[k][0]
    cells.append(top)
    m = dict(bbox=(x_lo, y_lo, x_hi, y_hi), core=core, place=place, bus=bus,
             blocks={k: dict(bbox=bb[k]) for k in bb}, wires={n: sum(len(p) for p in s) for n, s in trees.items()})
    return cells, m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(R.REPO / 'build' / 'rx_layout' / 'gen' / 'rx_top'))
    ap.add_argument('--gds', default=str(R.REPO / 'layout' / 'rx_top.gds'))
    a = ap.parse_args()
    cells, meta = build()
    R.save_meta(a.out, meta)
    log = R.write(cells, 'rx_top', a.gds, a.out)
    print('rx_top', R.bbox_str(meta['bbox']), 'core', R.bbox_str(meta['core']), 'magic log', log)


if __name__ == '__main__':
    main()
