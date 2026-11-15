#!/usr/bin/env python3
"""Shared layout library for the receiver cells (layout/gen/rx_*.py), gf180mcuD, 3.3 V devices.

A cell is a stack of *bands*, each in the style of layout/gen/lsdiv.py and layout/gen/tx_drv.py (whose strip() and
channel router are reused unchanged):

    VSS rail (M1 + M2 + M3, p+ tap under it)
    N row    : nfet strips (top-aligned) and poly resistors (p-substrate), terminals on the channel side (top)
    channel  : M2 tracks, one net per track interval; every terminal is an M1 stub + via1 onto its track
    P row    : pfet strips (bottom-aligned) in n-wells; pfets whose bulk is not VDD sit in their own n-well island
               with an n+ tap column (the tap is a channel terminal of the bulk net)
    VDD rail (M1 + M2 + M3, n+ tap under it, in a full-width n-well strip)

Bands stack upwards; every second band is mirrored so neighbours share a rail. VDD / VSS terminals that are not on
their own rail's side (a VDD gate in the N row, a resistor end on VDD, ...) go onto a VDD / VSS track, which an M3
tie joins to the rail. Nets leave a band on M3 (top / bottom edge, through a window in the rail's M3) or on M2
(left / right edge). Every net is labelled with its sim-netlist name so the size diff can compare the extracted
layout with sim/rx/*.py device by device.

Elements of a row (dicts):
  mos : dict(k='mos', W=um, L=um, seq=[region, gate, region, ...], bulk=net)   (W, L in um, as the netlisters)
  res : dict(k='res', model='rpp'|'hires', w=um, l=um, a=net, b=net, n=strips)   N row only; even n: both ends on
        the channel side; n=1: a at the top, b at the bottom (b must be VSS: an M1 drop to the rail)
No Metal4 / Metal5.
"""
import importlib.util
import itertools
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(HERE))
from ring_core import Cell, TPITCH  # noqa: E402

_ls = importlib.util.spec_from_file_location('lay_lsdiv', HERE / 'lsdiv.py')
LL = importlib.util.module_from_spec(_ls)
_ls.loader.exec_module(LL)
snap, um = LL.snap, LL.um

RAIL = 2400
DGAP = LL.DGAP          # same-well diffusion gap
WELLGAP = 2600          # P elements in different wells (NW.2b 1.4 um + 0.43 / 0.6 enclosures + margin)
RGAP = 1300             # resistor to anything in the N row (PRES.3 0.6 um to COMP; HRES.1: the HRES markers grow
                        # 0.4 um and need 0.4 um between them)
TAPW = 380              # n+ tap column width
M3P = 1100              # min centre distance of two M3 verticals (380 + 300 + via2 pad margin)
RPITCH = {'hires': 700, 'rpp': 1000}   # resistor strip gap. hires as lsdiv R1: 0.7 um (the HRES markers, grown
                                       # 0.4 um, merge: HRES.1), n >= 4 strips and the two terminal strips EXT longer
                                       # than the rest, so their heads (where the salicide block steps) face nothing
EXT = {'hires': 2500, 'rpp': 0}        # (SB.2)
HEAD = {'hires': 610, 'rpp': 610}      # resistor head: poly past the body
CPOS = {'hires': 315, 'rpp': 215}      # poly contact start from the body: the contact must sit 0.22-0.44 um from
                                       # the salicide block (= the body for rpp, the body + 0.1 um for hires)
MODEL = {'rpp': 'ppolyf_u', 'hires': 'ppolyf_u_1k'}
LAYER = {'ppolyf_u': 'rpp', 'ppolyf_u_1k': 'hires'}
PDK_ROOT = os.environ.get('PDK_ROOT', '/foss/pdks')
MAGICRC = f'{PDK_ROOT}/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc'


# ---- netlist parsing (sim/rx/*.py block() text) ------------------------------------------------------------------
def parse(text):
    """{subckt: dict(pins=[...], devs=[...], insts=[(name, cell, [nets])])}; a dev is dict(name, model, nets, w, l, m)
    (MOS nets d g s b; resistor nets a b sub)."""
    text = re.sub(r'\n\+', ' ', text)
    cells, cur = {}, None
    for ln in text.splitlines():
        t = ln.split()
        if not t or t[0].startswith('*'):
            continue
        if t[0].lower() == '.subckt':
            cur = dict(pins=t[2:], devs=[], insts=[])
            cells[t[1]] = cur
        elif t[0].lower() == '.ends':
            cur = None
        elif cur is not None and t[0][0] in 'Xx':
            kv = dict(x.split('=', 1) for x in t if '=' in x)
            pos = [x for x in t[1:] if '=' not in x]
            model = pos[-1]
            if model in ('nfet_03v3', 'pfet_03v3'):
                cur['devs'].append(dict(name=t[0][1:], model=model, nets=pos[:4], w=val(kv['w']), l=val(kv['l']),
                                        m=int(kv.get('m', 1))))
            elif model in ('ppolyf_u', 'ppolyf_u_1k'):
                cur['devs'].append(dict(name=t[0][1:], model=model, nets=pos[:3], w=val(kv['r_width']),
                                        l=val(kv['r_length']), m=1))
            else:
                cur['insts'].append((t[0], model, pos[:-1]))
    return cells


def val(s):
    s = s.lower()
    mult = {'u': 1e-6, 'n': 1e-9, 'p': 1e-12, 'f': 1e-15}
    if s[-1] in mult:
        return float(s[:-1]) * mult[s[-1]] * 1e6
    return float(s) * 1e6          # metres -> um


def sim_cells():
    """Every receiver subckt from sim/rx/rx_top.py block() (the sizes are taken from here, never typed in)."""
    sys.path.insert(0, str(REPO / 'sim' / 'rx'))
    import rx_top  # noqa: E402
    return parse(rx_top.block())


def flat_devs(cells, top, nets=None, path=''):
    """Devices of `top` flattened through its subcircuits; inner nets named <inst>_<net> (rx_sizes.py does the
    same), each dev with its full name <inst>_<name>."""
    c = cells[top]
    nets = nets or {p: p for p in c['pins']}
    out = []
    for d in c['devs']:
        out.append(dict(d, name=path + d['name'], nets=[nets.get(n, path + n) for n in d['nets']]))
    for inst, sub, conn in c['insts']:
        sc = cells[sub]
        out += flat_devs(cells, sub, dict(zip(sc['pins'], [nets.get(n, path + n) for n in conn])),
                         path + inst + '_')
    return out


def risers(bands, nets, xr, sep=None):
    """M3 riser x per net shared by several bands: the middle of the overlap of the nets' terminal spans (or of
    their union), nudged apart to M3P."""
    sep = sep or M3P + 200
    xs = {}
    for net in nets:
        sp = [b.span0[net] for b in bands if net in b.span0]
        lo, hi = max(a for a, b in sp), min(b for a, b in sp)
        xs[net] = snap((lo + hi) / 2) if lo <= hi else snap((min(a for a, b in sp) + max(b for a, b in sp)) / 2)
    order = sorted(xs, key=lambda n: xs[n])
    for i in range(1, len(order)):
        if xs[order[i]] - xs[order[i - 1]] < sep:
            xs[order[i]] = xs[order[i - 1]] + sep
    for n in xs:
        assert 700 <= xs[n] <= xr - 700, (n, xs[n])
    return xs


def load_gen(name):
    """A layout generator layout/gen/<name>.py as a module (sim/rx has netlisters of the same names)."""
    spec = importlib.util.spec_from_file_location('lay_' + name, HERE / f'{name}.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def dev(cell, name):
    for d in cell['devs']:
        if d['name'] == name:
            return d
    raise KeyError(name)


# ---- a y-transforming proxy so LL.strip() and the band code draw into a mirrored / shifted frame --------------------
class Frame:
    def __init__(self, cell, y0=0, flip=False):
        self.c, self.y0, self.flip = cell, y0, flip

    def Y(self, y):
        return self.y0 - y if self.flip else self.y0 + y

    def r(self, layer, x1, y1, x2, y2):
        self.c.r(layer, x1, self.Y(y1), x2, self.Y(y2))

    def label(self, text, layer, x, y, port=False):
        self.c.label(text, layer, x, self.Y(y), port)

    def via1(self, x, y):
        self.r('m1', x - 190, y - 190, x + 190, y + 190)
        self.r('m2', x - 190, y - 190, x + 190, y + 190)
        self.r('v1', x - 130, y - 130, x + 130, y + 130)

    def via2(self, x, y):
        self.r('m2', x - 190, y - 190, x + 190, y + 190)
        self.r('m3', x - 190, y - 190, x + 190, y + 190)
        self.r('v2', x - 140, y - 140, x + 140, y + 140)

    def via12(self, x, y):
        self.via1(x, y)
        self.via2(x, y)


class Null:
    def r(self, *a):
        pass

    def label(self, *a, **k):
        pass


# ---- elements ----------------------------------------------------------------------------------------------------
def mos(W, L, seq, bulk, dummy=False):
    """dummy: a poly-only dummy finger (same L, floating, no diffusion under it) 0.3 um past each end."""
    return dict(k='mos', W=W, L=L, seq=list(seq), bulk=bulk, dummy=dummy)


def res(model, w, l, a, b, n):
    return dict(k='res', model=model, w=w, l=l, a=a, b=b, n=n)


def from_dev(d, seq=None, nf=1):
    """A mos element for netlist device d drawn as nf fingers of W/nf (shared S/D: [s, g, d, g, s, ...]) or as
    the given region/gate sequence."""
    D, G, S, B = d['nets']
    if seq is None:
        seq = [S]
        for k in range(nf):
            seq += [G, D if k % 2 == 0 else S]
    return mos(d['w'] * d['m'] / (len(seq) // 2), d['l'], seq, B)


def res_geom(e):
    """Strip length Ls (nm) so that n * Ls + 2 EXT + (n - 1) * pitch = l (magic counts each bar as one pitch, the
    two terminal strips are EXT longer)."""
    w, n = um(e['w']), e['n']
    pitch = w + RPITCH[e['model']]
    ext = EXT[e['model']] if n > 1 else 0
    assert ext == 0 or n >= 4, ('hires serpentines need n >= 4', e)
    Ls = snap((um(e['l']) - (n - 1) * pitch - 2 * ext) / n)
    assert Ls >= 1000, ('resistor strip too short', e)
    return w, pitch, Ls


def res_width(e):
    w, pitch, Ls = res_geom(e)
    return e['n'] * w + (e['n'] - 1) * RPITCH[e['model']]


def res_height(e):
    """Below the top of the N row (the terminal strips' EXT and the heads stand above it, in the pad zone)."""
    w, pitch, Ls = res_geom(e)
    return Ls + (w if e['n'] > 1 else HEAD[e['model']])


def res_top(e):
    """Height of the resistor above the N row top (EXT + head)."""
    return (EXT[e['model']] if e['n'] > 1 else 0) + HEAD[e['model']]


def draw_res(c, x0, ntop, e):
    """Resistor in the N row, body top at ntop, heads (poly + contacts + M1) above it on the channel side.
    Returns (x1, terms, info)."""
    lay = e['model']
    w, pitch, Ls = res_geom(e)
    n = e['n']
    bt, bb = ntop, ntop - Ls
    ext = EXT[lay] if n > 1 else 0
    terms = []
    for i in range(n):
        xs = x0 + i * pitch
        c.r(lay, xs, bb, xs + w, bt + (ext if i in (0, n - 1) else 0))
        if i < n - 1:
            if i % 2 == 0:
                c.r(lay, xs, bb - w, xs + pitch + w, bb)
            else:
                c.r(lay, xs, bt, xs + pitch + w, bt + w)
    heads = [(0, e['a'], 'top')]
    if n == 1:
        heads.append((0, e['b'], 'bot'))
    else:
        heads.append((n - 1, e['b'], 'top'))
    H = HEAD[lay]
    for i, net, side in heads:
        xs = x0 + i * pitch
        bt = ntop + ext
        if side == 'top':
            c.r('poly', xs, bt, xs + w, bt + H)
            c.r('pc', xs + 65, bt + CPOS[lay], xs + w - 65, bt + CPOS[lay] + 230)
            c.r('m1', xs, bt + CPOS[lay] - 65, xs + w, bt + H)
            terms.append((net, xs + w // 2, bt + H, 'r'))
        else:
            c.r('poly', xs, bb - H, xs + w, bb)
            c.r('pc', xs + 65, bb - CPOS[lay] - 230, xs + w - 65, bb - CPOS[lay])
            c.r('m1', xs, bb - H, xs + w, bb - CPOS[lay] + 65)
            terms.append((net, xs + w // 2, bb - H, 'rb'))
    x1 = x0 + (n - 1) * pitch + w
    return x1, terms, dict(cb=bb - H, ct=ntop + ext + H)


DUMSP = 300                            # dummy poly to the diffusion end


def draw_elem(c, x0, row, Y, e, chan):
    """One element; returns (x1, [(net, x, y, kind)], info)."""
    if e['k'] == 'res':
        assert row == 'N'
        return draw_res(c, x0, Y['n_top'], e)
    W, L = um(e['W']), um(e['L'])
    dx = (L + DUMSP) if e.get('dummy') else 0
    yb = Y['n_top'] - W if row == 'N' else Y['p_bot']
    x1, t, g = LL.strip(c, x0 + dx, yb, W, e['seq'], L, 'n' if row == 'N' else 'p', chan)
    if dx:
        for xa in (x0, x1 + DUMSP):
            c.r('poly', xa, yb - LL.ENDCAP, xa + L, yb + W + LL.ENDCAP)
        x1 += dx
    return x1, t, g


def elem_w(e, chan):
    if e['k'] == 'res':
        return res_width(e)
    dx = (um(e['L']) + DUMSP) if e.get('dummy') else 0
    return LL.strip(Null(), 0, 0, um(e['W']), e['seq'], um(e['L']), 'n', chan)[0] + 2 * dx


# ---- a band ------------------------------------------------------------------------------------------------------
class Band:
    """cols: [(name, P elements, N elements)]. ports: nets that are cell ports or leave the band."""

    def __init__(self, name, cols, ports=(), pins=(), x0=900, search=True, nmin=0):
        self.name, self.cols, self.x0 = name, [list(c) for c in cols], x0
        self.ports = set(ports) | set(pins)   # nets that leave the band
        self.pins = set(pins)                 # cell ports among them (labelled as ports at the band edge)
        self.nmin = nmin                     # minimum N row height (nm)
        self.search = search
        cnt, gates = {}, set()
        for _, P, N in self.cols:
            for row, lst in (('P', P), ('N', N)):
                for e in lst:
                    if e['k'] == 'res':
                        for net in (e['a'], e['b']):
                            cnt[net] = cnt.get(net, 0) + 2
                        continue
                    for net in e['seq']:
                        cnt[net] = cnt.get(net, 0) + 1
                    gates |= set(e['seq'][1::2])
                    if row == 'P' and e['bulk'] != 'VDD':
                        cnt[e['bulk']] = cnt.get(e['bulk'], 0) + 2
        self.cnt = cnt
        # channel nets: every net with more than one terminal, every gate, every port; VDD / VSS where they show up
        # off their own rail's side (decided per terminal when drawing; here: whether a VDD / VSS track is needed)
        chan = {n for n in cnt if n not in ('VDD', 'VSS') and (cnt[n] > 1 or n in gates or n in self.ports)}
        for _, P, N in self.cols:
            for e in P:
                if e['k'] == 'mos' and ('VSS' in e['seq']):
                    chan.add('VSS')
                if e['k'] == 'mos' and 'VDD' in e['seq'][1::2]:
                    chan.add('VDD')
            for e in N:
                if e['k'] == 'res':
                    if 'VDD' in (e['a'], e['b']):
                        chan.add('VDD')
                    if e['n'] > 1 and 'VSS' in (e['a'], e['b']):
                        chan.add('VSS')
                    continue
                if 'VDD' in e['seq']:
                    chan.add('VDD')
                if 'VSS' in e['seq'][1::2]:
                    chan.add('VSS')
        self.chan = chan

    # -- placement (x only) --
    def placement(self, cols, offs):
        x = self.x0
        place = []
        prevb = None                         # well of the previous P element ('VDD' or an island bulk)
        prevn = None                         # kind of the previous N element (resistors keep RGAP)
        for (name, P, N), off in zip(cols, offs):
            xp, xn = x + off, x
            cp, cn, taps = [], [], []
            for e in P:
                b = e['bulk']
                if prevb is not None and b != prevb:
                    xp += WELLGAP - DGAP
                if b != 'VDD' and b != prevb:            # island start: tap column first
                    taps.append((xp, b))
                    xp += TAPW + DGAP
                cp.append(xp)
                xp += elem_w(e, self.chan) + DGAP
                prevb = b
            for e in N:
                if prevn is not None and (e['k'] == 'res' or prevn == 'res'):
                    xn += RGAP - DGAP
                cn.append(xn)
                xn += elem_w(e, self.chan) + DGAP
                prevn = e['k']
            place.append((name, P, N, cp, cn, taps))
            x = max(xp, xn) + 200
        return place, x

    def terms(self, c, place, Y):
        out = []
        for name, P, N, cp, cn, taps in place:
            for e, x0 in zip(P, cp):
                _, t, g = draw_elem(c, x0, 'P', Y, e, self.chan)
                out += [(net, xx, yy, k, 'P', g, e) for (net, xx, yy, k) in t]
            for (x0, b) in taps:
                out.append((b, x0 + TAPW // 2, Y['p_bot'] - 5, 'tap', 'P', dict(x0=x0), None))
            for e, x0 in zip(N, cn):
                _, t, g = draw_elem(c, x0, 'N', Y, e, self.chan)
                out += [(net, xx, yy, k, 'N', g, e) for (net, xx, yy, k) in t]
        return out

    def is_chan(self, t):
        net, xx, yy, kind, side, g, e = t
        if net == 'VSS':
            return (side == 'P') or kind in ('g', 'r')
        if net == 'VDD':
            return (side == 'N') or kind == 'g'
        return net in self.chan

    def stubs(self, terms):
        return [(t[0], t[1], t[4]) for t in terms if self.is_chan(t)]

    def place(self):
        Yd = dict(n_top=20000, p_bot=40000)
        cols = self.cols
        offs = []
        for i in range(len(cols)):
            name, P, N = cols[i]
            best = None
            pperm = list(itertools.permutations(P)) if (self.search and len(P) <= 3) else [P]
            nperm = list(itertools.permutations(N)) if (self.search and len(N) <= 3) else [N]
            for off in range(0, 3001, 200):
                for pp in pperm:
                    for nn in nperm:
                        bak = cols[i]
                        cols[i] = (name, list(pp), list(nn))
                        pl, _ = self.placement(cols[:i + 1], offs + [off])
                        cols[i] = bak
                        t = self.terms(Null(), pl, Yd)
                        try:
                            _, span = LL.assign_tracks(self.stubs(t), {})
                        except SystemExit:
                            continue
                        cost = sum(b - a for a, b in span.values()) + off // 2
                        if best is None or cost < best[0]:
                            best = (cost, off, list(pp), list(nn))
                if best and not self.search:
                    break
            if not best:
                raise SystemExit(f'{self.name}: no P offset / strip order for column {name}')
            offs.append(best[1])
            cols[i] = (name, best[2], best[3])
        self.offs = offs
        self.pl, self.xend = self.placement(cols, offs)
        t = self.terms(Null(), self.pl, Yd)
        span = {}
        for net, xx, side in self.stubs(t):
            a, b = span.get(net, (xx, xx))
            span[net] = (min(a, xx), max(b, xx))
        self.span0 = span                    # terminal x span per channel net (before exits / ties)
        return self.xend

    # -- vertical plan, tracks, drawing --
    def finish(self, cell, xr, y0=0, flip=False, exits=None, m3_used=(), xmin=700):
        """exits: {net: (edge, x)} with edge 'top' / 'bottom' (M3 to that edge of the band) / 'left' / 'right'
        (M2 track to x 0 / xr); x None picks one. m3_used: x positions of M3 verticals crossing this band (risers of
        other bands): kept free. Returns meta (with the band's global y extent)."""
        exits = dict(exits or {})
        c = Frame(cell, y0, flip)
        Y = dict(vss_b=-RAIL, vss_t=0)
        hn = [um(e['W']) for _, _, N, *_ in self.pl for e in N if e['k'] == 'mos']
        hn += [res_height(e) for _, _, N, *_ in self.pl for e in N if e['k'] == 'res']
        Y['n_top'] = 600 + max(hn + [self.nmin, 1000])
        t0 = self.terms(Null(), self.pl, dict(Y, p_bot=10 ** 7))
        npad = max([yy for (net, xx, yy, k, side, g, e) in t0 if side == 'N'] + [Y['n_top']])
        Y['t0'] = snap(npad + 230 + 190 + 5)
        # M3 verticals of this band: exits and VDD / VSS ties, at x positions apart from each other and m3_used
        used = [x for x in m3_used]

        def free(x):
            return all(abs(x - u) >= M3P for u in used)

        def pick(pref, lo, hi):
            lo, hi = max(lo, xmin), min(hi, xr - 700)
            cands = sorted(range(snap(lo), snap(hi) + 1, 85), key=lambda v: abs(v - pref))
            for x in cands:
                if free(x):
                    return snap(x)
            raise SystemExit(f'{self.name}: no free M3 x near {pref}')

        exl = [(net, ex) for net, v in exits.items() for ex in (v if isinstance(v, list) else [v])]
        verts = []                           # (net, x, edge) M3 verticals: 'top' / 'bottom' / 'through'
        for net, (edge, x) in exl:
            if edge in ('top', 'bottom', 'through') and x is not None:
                verts.append((net, snap(x), edge))
                used.append(snap(x))
        for net, (edge, x) in exl:
            if edge in ('top', 'bottom', 'through') and x is None:
                a, b = self.span0.get(net, (self.x0, self.xend))
                x = pick((a + b) // 2, a - 3000, b + 3000)
                verts.append((net, snap(x), edge))
                used.append(snap(x))
        ties = {}
        for net in ('VDD', 'VSS'):
            if net in self.span0:
                a, b = self.span0[net]
                # top edge (local) holds the VDD rail, bottom the VSS rail
                x = pick(a, a - 4000, b + 4000)
                ties[net] = x
                used.append(x)
        extra = {}
        for net, x, edge in verts:
            extra.setdefault(net, []).append(x)
        for net, x in ties.items():
            extra.setdefault(net, []).append(x)
        for net, (edge, x) in exl:
            if edge == 'left':
                extra.setdefault(net, []).append(300)
            elif edge == 'right':
                extra.setdefault(net, []).append(xr - 300)
        stubs = self.stubs(t0)
        trk, span = LL.assign_tracks(stubs, extra)
        ntrk = (max(trk.values()) + 1) if trk else 1
        ty = {n: Y['t0'] + k * TPITCH for n, k in trk.items()}
        Y['p_bot'] = snap(Y['t0'] + (ntrk - 1) * TPITCH + 190 + 230 + 635 + 80)
        hp = [um(e['W']) for _, P, *_ in self.pl for e in P] or [1000]
        Y['p_top'] = Y['p_bot'] + max(hp)
        islands = any(b for *_, taps in self.pl for b in taps)
        Y['vdd_b'] = Y['p_top'] + (1400 if islands else 600)
        Y['vdd_t'] = Y['vdd_b'] + RAIL
        terms = self.terms(c, self.pl, Y)

        # stubs, vias, rail drops
        vias = {}
        for t in terms:
            net, xx, yy, kind, side, g, e = t
            if self.is_chan(t):
                tt = ty[net]
                if side == 'N':
                    c.r('m1', xx - 190, yy - 5, xx + 190, tt + 190)
                else:
                    c.r('m1', xx - 190, tt - 190, xx + 190, yy + 5)
                near = [v for v in vias.get(net, []) if abs(v - xx) < 700]
                if near:
                    c.r('m1', min(near[0], xx) - 190, tt - 190, max(near[0], xx) + 190, tt + 190)
                else:
                    c.via1(xx, tt)
                    vias.setdefault(net, []).append(xx)
            elif net == 'VSS' and side == 'N':
                yt = g['cb'] if kind != 'rb' else yy + 360
                c.r('m1', xx - 190, Y['vss_t'] - 300, xx + 190, yt)
            elif net == 'VDD' and side == 'P':
                c.r('m1', xx - 190, g['ct'], xx + 190, Y['vdd_b'] + 300)
            elif kind in ('g', 'r', 'rb', 'tap'):
                raise SystemExit(f'{self.name}: unhandled terminal {net} {side} {kind} at {xx}')
            else:                            # a stack midpoint (one diffusion only): label it for the size diff
                if net not in ('VDD', 'VSS'):
                    c.label(net, 'm1', xx, (g['cb'] + g['ct']) // 2)
        for net in trk:
            a, b = span[net]
            c.r('m2', a - 190, ty[net] - 190, b + 190, ty[net] + 190)
            if net not in ('VDD', 'VSS'):
                c.label(net, 'm2', snap((a + b) / 2), ty[net])
        # island taps (n+ column, contacts, M1 down to the stub)
        hp_isl = {}
        for name, P, N, cp, cn, taps in self.pl:
            for (x0, b) in taps:
                hi = max(um(e['W']) for e in P if e['bulk'] == b)
                hp_isl.setdefault(b, []).append(hi)
                c.r('nsd', x0, Y['p_bot'], x0 + TAPW, Y['p_bot'] + max(hi, 760))
                c.r('nsc', x0 + 75, Y['p_bot'] + 75, x0 + TAPW - 75, Y['p_bot'] + max(hi, 760) - 75)
                c.r('m1', x0, Y['p_bot'] - 5, x0 + TAPW, Y['p_bot'] + max(hi, 760))
        # wells: VDD runs (to the rail's n-well strip) and islands
        runs = []                            # (x0, x1, bulk)
        for name, P, N, cp, cn, taps in self.pl:
            tapx = {b: x0 for (x0, b) in taps}
            for e, x0 in zip(P, cp):
                b = e['bulk']
                xa = tapx.pop(b, x0) if b != 'VDD' else x0
                x1 = x0 + elem_w(e, self.chan)
                if runs and runs[-1][2] == b and xa - runs[-1][1] < WELLGAP:
                    runs[-1] = (runs[-1][0], x1, b)
                else:
                    runs.append((xa, x1, b))
        Y['nw_b'] = Y['p_bot'] - 80 - 450
        for xa, x1, b in runs:
            if b == 'VDD':
                c.r('nwell', xa - 600, Y['nw_b'], x1 + 600, Y['vdd_b'] + 1900)
            else:
                hi = max(um(e['W']) for _, P, *_ in self.pl for e in P if e['bulk'] == b)
                c.r('nwell', xa - 450, Y['nw_b'], x1 + 450, Y['p_bot'] + max(hi, 760) + 450)
        # rails (M3 windows where an M3 vertical crosses), the rail n-well strip and taps
        skip_t = [(x - 700, x + 700) for x in list(m3_used) + [x for n, x, e in verts if e in ('top', 'through')]
                  + ([ties['VDD']] if 'VDD' in ties else [])]
        skip_b = [(x - 700, x + 700) for x in list(m3_used) + [x for n, x, e in verts if e in ('bottom', 'through')]
                  + ([ties['VSS']] if 'VSS' in ties else [])]
        # rails: drawn by stack(), once per shared rail, with the union of both bands' M3 windows
        rails = [('VSS', tuple(sorted((c.Y(Y['vss_b']), c.Y(Y['vss_t'])))), skip_b),
                 ('VDD', tuple(sorted((c.Y(Y['vdd_b']), c.Y(Y['vdd_t'])))), skip_t)]
        # M3 ties to the rails
        for net, x in ties.items():
            yr = (Y['vdd_b'] + Y['vdd_t']) // 2 if net == 'VDD' else (Y['vss_b'] + Y['vss_t']) // 2
            c.via2(x, ty[net])
            c.r('m3', x - 190, min(ty[net], yr) - 190, x + 190, max(ty[net], yr) + 190)
            c.via2(x, yr)
        # exits
        pins = {}
        for net, x, edge in verts:
            c.via2(x, ty[net])
            ya = Y['vss_b'] if edge in ('bottom', 'through') else ty[net]
            yb = Y['vdd_t'] if edge in ('top', 'through') else ty[net]
            c.r('m3', x - 190, ya, x + 190, yb)
            ye = Y['vss_b'] if edge == 'bottom' else Y['vdd_t']
            pins.setdefault(net, []).append((x, c.Y(ye), edge))
            if net in self.pins:
                c.label(net, 'm3', x, ye - 200 if ye == Y['vdd_t'] else ye + 200, port=True)
        for net, (edge, x) in exl:
            if edge in ('left', 'right'):
                xe = 0 if edge == 'left' else xr
                a, b = span[net]
                c.r('m2', min(xe, a - 190), ty[net] - 190, max(xe, b + 190), ty[net] + 190)
                pins.setdefault(net, []).append((xe, c.Y(ty[net]), edge))
                if net in self.pins:
                    c.label(net, 'm2', xe + 150 if edge == 'left' else xe - 150, ty[net], port=True)
        ys = sorted((c.Y(Y['vss_b']), c.Y(Y['vdd_t'])))
        self.Y, self.ty, self.trk, self.span = Y, ty, trk, span
        return dict(name=self.name, y=ys, flip=flip, y0=y0, Y=Y, ntrk=ntrk, ties=ties, pins=pins, rails=rails,
                    tracks={n: [k, c.Y(ty[n]), span[n]] for n, k in trk.items()}, offs=self.offs,
                    xend=self.xend, m3=[x for n, x, e in verts] + list(ties.values()))

def rail(c, yb, yt, x0, x1, tap=None, m3=True, skip=(), m3_only=False):
    """tx_drv.py rail(): M1 + M2 from x0 to x1 (via1 every 2 um), M3 with via2 every 2 um except in the skip
    windows, a tap strip ('p' / 'n') under it. m3_only: only the M3 + via2 (on a rail another generator drew)."""
    if not m3_only:
        c.r('m1', x0, yb, x1, yt)
        c.r('m2', x0, yb, x1, yt)
        x = x0 + 400
        while x + 400 < x1:
            c.r('v1', x - 130, yb + 300, x + 130, yt - 300)
            x += 2000
    else:
        tap = None
    if m3:
        segs, a = [], x0
        for (s0, s1) in sorted(skip):
            if s0 > a:
                segs.append((a, s0))
            a = max(a, s1)
        if a < x1:
            segs.append((a, x1))
        for a, b in segs:
            if b - a < 1000:
                continue
            c.r('m3', a, yb, b, yt)
            x = a + 500
            while x + 500 <= b:
                c.r('v2', x - 140, yb + 300, x + 140, yt - 300)
                x += 2000
    if tap:
        kind, (a, b) = tap
        imp, cont = ('psd', 'psc') if kind == 'p' else ('nsd', 'nsc')
        c.r(imp, a, yb + 1010, b, yb + 1390)
        c.r(cont, a + 75, yb + 1085, b - 75, yb + 1315)


def stack(cell, bands, exits, m3_shared=None, margin=900):
    """Place bands bottom to top (odd ones mirrored, sharing rails), all xr wide. exits: per band {net: (edge, x)}.
    m3_shared: M3 x positions that cross every band (risers between bands). Returns (metas, bbox)."""
    xr = max(b.place() for b in bands) + margin
    if callable(exits):
        exits = exits(bands, xr)
    metas = []
    y = 0
    m3_shared = list(m3_shared or [])
    xmin = STRAPX1 + 700 if len(bands) > 1 else 700     # M3 rail straps at the left edge
    for i, b in enumerate(bands):
        flip = i % 2 == 1
        if not flip:
            m = b.finish(cell, xr, y0=y, flip=False, exits=exits[i], m3_used=m3_shared, xmin=xmin)
            # next (mirrored) band shares this band's VDD rail: its local vdd rail maps onto [vdd_b, vdd_t]
            top_rail = (y + m['Y']['vdd_b'], y + m['Y']['vdd_t'])
        else:
            # draw once into scratch to learn its local Y, then for real with y0 so that local vdd_t -> top_rail[0]
            tmp = Cell('scratch')
            m0 = b.finish(tmp, xr, y0=0, flip=False, exits=exits[i], m3_used=m3_shared, xmin=xmin)
            y0 = top_rail[0] + m0['Y']['vdd_t']
            m = b.finish(cell, xr, y0=y0, flip=True, exits=exits[i], m3_used=m3_shared, xmin=xmin)
            top_rail = None
        metas.append(m)
        if not flip:
            y = None
        else:
            # next unmirrored band shares this band's VSS rail (local [-2400, 0] -> global [y0, y0 + 2400])
            y = y0 + RAIL
    ylo = min(m['y'][0] for m in metas)
    yhi = max(m['y'][1] for m in metas)
    draw_rails(cell, metas, xr)
    return metas, (0, ylo, xr, yhi)


STRAP = {'VSS': (400, 1400), 'VDD': (1800, 2800)}   # M3 straps joining the rails of a multi-band cell
STRAPX1 = 2800


def draw_rails(cell, metas, xr, x0=0, m3_only=()):
    """Every band's rails, a shared rail once with the union of the bands' M3 windows; n-well strip under VDD.
    With more than one rail per net, an M3 strap per net at the left edge joins them (windows in the other net's
    rails' M3, a via2 column where it crosses its own)."""
    rails = {}
    for m in metas:
        for net, (yb, yt), skip in m['rails']:
            r = rails.setdefault((yb, yt), [net, []])
            assert r[0] == net
            r[1] += skip
    c = Frame(cell)
    if len(rails) > 2:
        ys = [y for k in rails for y in k]
        for net, (a, b) in STRAP.items():
            c.r('m3', a, min(ys), b, max(ys))
            for (yb, yt), r in rails.items():
                if r[0] != net:                  # (its own rails' M3, with their via2 row, merge with the strap)
                    r[1].append((a - 300, b + 300))
    lab = set()
    for (yb, yt), (net, skip) in sorted(rails.items()):
        mo = (yb, yt) in m3_only
        rail(c, yb, yt, x0 + (300 if mo else 0), xr - (300 if mo else 0),
             tap=('p' if net == 'VSS' else 'n', (x0 + 300, xr - 300)), skip=skip, m3_only=mo)
        if net == 'VDD' and not mo:
            c.r('nwell', x0 + 150, yb + 500, xr - 150, yb + 1900)
        if net not in lab:
            c.label(net, 'm2', x0 + 1000, (yb + yt) // 2, port=True)
            lab.add(net)


# ---- output ------------------------------------------------------------------------------------------------------
def write(cells, top, gds, out, extra_tcl=''):
    """Write <out>/<top>.tcl (every cell), run magic on it (.mag files + GDS)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob('*.mag'):
        old.unlink()
    tcl = 'drc off\nsnap internal\n' + ''.join(c.tcl() for c in cells) + extra_tcl
    tcl += f'load {top}\nselect top cell\nexpand\ngds write {Path(gds).resolve()}\nquit -noprompt\n'
    (out / f'{top}.tcl').write_text(tcl)
    r = subprocess.run(['nice', '-n', '19', 'magic', '-rcfile', MAGICRC, '-noconsole', '-dnull', f'{top}.tcl'],
                       cwd=out, capture_output=True, text=True)
    (out / 'magic_gen.log').write_text(r.stdout + r.stderr)
    return out / 'magic_gen.log'


def bbox_str(bb):
    w, h = (bb[2] - bb[0]) / 1000, (bb[3] - bb[1]) / 1000
    return f'{w:.2f} x {h:.2f} um = {w * h:.0f} um2'


def save_meta(out, meta):
    Path(out).mkdir(parents=True, exist_ok=True)
    (Path(out) / 'meta.json').write_text(json.dumps(meta, indent=1, default=str))
