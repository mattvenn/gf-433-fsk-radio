"""DC IR drop and EM of the tile's supplies: the meshes from sim/power/mesh.py, TT's switches and Metal5, block sinks.

Per net and case (A / B, mesh.py), a conductance matrix: the mesh, the Metal5 straps with their Via4 landings, and
the source. VDPWR / VAPWR: the straps run from the switch output column (x -20 / -4 um, west of the tile) to the last
pin; the switch (Ron, sim/power/pg_rdson.py) joins the column to the ideal chip supply. VGND: each chip-grid stripe
crosses the whole tile and is held at 0 V at both tile edges (nominal; it continues into the neighbours) or at every
landing ('gnd_ideal', the best case). Node voltages are the drop below the supply (VDPWR / VAPWR) or the rise above
the chip ground (VGND).

Sinks: a block's current is spread over the Metal1 cells of its contacts on that net inside its box (meta.json
'blocks'; a cell in two boxes goes to the smaller), in proportion to the contact area. Mesh islands without a path
to the source are dropped and their sinks reported.

    python3 sim/power/solve.py [mesh dir tag, default p0.5] [Ron set: tt|ss|ff]
-> build/power/<tag>/result.json (+ maps .npz for the figures)
"""
import json
import os
import sys

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as sla
from scipy.sparse.csgraph import connected_components

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import currents  # noqa: E402

ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
TAG = sys.argv[1] if len(sys.argv) > 1 else 'p0.5'
RON_SET = sys.argv[2] if len(sys.argv) > 2 else 'tt'
D = os.path.join(ROOT, 'build', 'power', 'mesh_' + TAG)
OUT = os.path.join(ROOT, 'build', 'power', 'res_' + TAG + ('' if RON_SET == 'tt' else '_' + RON_SET))
META = json.load(open(os.path.join(ROOT, 'build', 'tile', 'meta.json')))
RON = json.load(open(os.path.join(ROOT, 'build', 'power', 'pg_rdson.json')))
KEY = {'tt': 'typical', 'ss': 'ss', 'ff': 'ff'}[RON_SET]
R_SW = {'VDPWR': RON[f'3v3_hp_2_3.3V_{KEY}'], 'VAPWR': RON[f'5v0_2_3.3V_{KEY}']}
X_SRC = {'VDPWR': -20.0, 'VAPWR': -4.0}
W_TILE = 693.28
RS5 = 0.060
# EM limits, gf180mcuD tech LEF DCCURRENTDENSITY AVERAGE: Metal1-4 0.67 mA/um, Metal5 1.5 mA/um, Via1-4 0.18
# (read as mA per cut, as the sky130 study read its LEF; per um^2 it would be 0.012 mA per 0.26 um cut)
EM = {0: 0.67, 1: 0.67, 2: 0.67, 3: 0.67, 10: 0.18, 11: 0.18, 12: 0.18, 20: 0.18, 21: 1.5}
KNAME = {0: 'Metal1', 1: 'Metal2', 2: 'Metal3', 3: 'Metal4', 10: 'Via1', 11: 'Via2', 12: 'Via3', 20: 'Via4',
         21: 'Metal5'}


def block_of_cells(P, nx, ny):
    """block index per cell (-1 none), smallest box wins."""
    names = sorted(META['blocks'], key=lambda b: -((META['blocks'][b]['box'][2] - META['blocks'][b]['box'][0]) *
                                                   (META['blocks'][b]['box'][3] - META['blocks'][b]['box'][1])))
    lab = -np.ones((ny, nx), dtype=int)
    for k, b in enumerate(names):
        x0, y0, x1, y1 = META['blocks'][b]['box']
        lab[int(y0 / P):int(np.ceil(y1 / P)), int(x0 / P):int(np.ceil(x1 / P))] = k
    return names, lab


def build(net, case, gnd_ideal=False):
    z = np.load(os.path.join(D, f'{net}.npz'))
    m5 = json.load(open(os.path.join(D, f'{net}_m5.json')))[case]
    nn, P = int(z['nn']), float(z['P'])
    n = m5['n'] + 1                     # + the switch output node (switched nets)
    src = m5['n']
    I = list(z['I']); J = list(z['J']); G = list(z['G']); K = list(z['K'])
    E = m5['E']
    I += [e[0] for e in E]; J += [e[1] for e in E]; G += [e[2] for e in E]; K += [e[3] for e in E]
    gdiag = np.zeros(n)
    meta_edges = []                      # Metal5 from the source / edges: (node, g) to src or ground
    for nm, yc, w, nodes, xs in m5['straps']:
        if not nodes:
            continue
        if net == 'VGND':
            if gnd_ideal:
                for a in nodes:
                    gdiag[a] += 1e6
            else:
                gdiag[nodes[0]] += w / (RS5 * max(xs[0], 0.5))
                gdiag[nodes[-1]] += w / (RS5 * max(W_TILE - xs[-1], 0.5))
        else:
            g = w / (RS5 * (xs[0] - X_SRC[net]))
            I.append(nodes[0]); J.append(src); G.append(g); K.append(21)
    if net != 'VGND':
        gdiag[src] += 1.0 / R_SW[net]
    I = np.array(I, dtype=np.int64); J = np.array(J, dtype=np.int64); G = np.array(G); K = np.array(K)
    A = sp.coo_matrix((G, (I, J)), shape=(n, n)).tocsr()
    A = A + A.T
    deg = np.asarray(A.sum(axis=1)).ravel() + gdiag
    Y = sp.diags(deg) - A
    # keep the component(s) that reach the source / ground
    ncomp, lab = connected_components(A, directed=False)
    good = set(lab[np.nonzero(gdiag)[0]])
    keep = np.isin(lab, list(good))
    return dict(z=z, Y=Y, keep=keep, n=n, nn=nn, P=P, I=I, J=J, G=G, K=K, src=src, m5=m5)


def sinks(m, names, blab):
    z = m['z']
    ids, co = z['ids'][0], z['co']
    out = {}
    for k, b in enumerate(names):
        sel = (blab == k) & (co > 0) & (ids >= 0)
        if not sel.any():
            continue
        nodes, w = ids[sel], co[sel]
        ok = m['keep'][nodes]
        out[b] = dict(nodes=nodes[ok], w=w[ok] / w[ok].sum() if ok.any() else w[ok], lost=int((~ok).sum()),
                      n=int(len(nodes)))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    res = {'R_switch': R_SW, 'cases': {}}
    for case, gi in (('A', False), ('B', False), ('A', True)):
        cname = case + ('_gnd_ideal' if gi else '')
        rc = res['cases'][cname] = {}
        for net in ('VAPWR', 'VDPWR', 'VGND'):
            if gi and net != 'VGND':
                continue
            m = build(net, case, gi)
            z = m['z']
            nx, ny, P = int(z['nx']), int(z['ny']), m['P']
            names, blab = block_of_cells(P, nx, ny)
            sk = sinks(m, names, blab)
            keep = np.nonzero(m['keep'])[0]
            idx = -np.ones(m['n'], dtype=np.int64)
            idx[keep] = np.arange(len(keep))
            Yk = m['Y'][keep][:, keep].tocsc()
            lu = sla.splu(Yk)
            rn = rc[net] = {'dropped_nodes': int(m['n'] - len(keep)),
                            'sinks': {b: {'cells': s['n'], 'lost': s['lost']} for b, s in sk.items()}}
            # a loaded block with no sink on this net is not connected to it (or lost to an island): flag it
            want = {b for mo in currents.MODES for b in currents.mode(mo)[net]}
            rn['missing'] = sorted(b for b in want if b not in sk or not len(sk[b]['nodes']))
            if rn['missing']:
                print(f'*** {cname} {net}: NOT CONNECTED to the grid: {rn["missing"]}', flush=True)
            # unit responses: 1 A at each loaded block -> mean / worst drop at every block (ohm)
            loaded = sorted({b for mo in currents.MODES for b in currents.mode(mo)[net]} & set(sk))
            T = {}
            for bi in loaded:
                rhs = np.zeros(len(keep))
                np.add.at(rhs, idx[sk[bi]['nodes']], sk[bi]['w'])
                v = lu.solve(rhs)
                T[bi] = {bj: float(np.dot(v[idx[sk[bj]['nodes']]], sk[bj]['w'])) for bj in sk if len(sk[bj]['nodes'])}
            rn['R_self'] = {b: T[b][b] for b in T}
            if net != 'VGND':
                rn['R_src_node_self'] = {}
            # modes
            rn['modes'] = {}
            for mo in currents.MODES:
                cur = currents.mode(mo)[net]
                rhs = np.zeros(len(keep))
                for b, i in cur.items():
                    if b in sk and len(sk[b]['nodes']):
                        np.add.at(rhs, idx[sk[b]['nodes']], sk[b]['w'] * i * 1e-3)
                v = lu.solve(rhs)
                full = np.zeros(m['n'])
                full[keep] = v
                vsw = float(full[m['src']]) if net != 'VGND' else 0.0
                blk = {}
                for b, s in sk.items():
                    if not len(s['nodes']):
                        continue
                    vb = full[s['nodes']]
                    blk[b] = {'mean_mV': float(np.dot(vb, s['w'])) * 1e3, 'worst_mV': float(vb.max()) * 1e3}
                # EM: branch currents
                Ib = m['G'] * (full[m['I']] - full[m['J']])            # A
                em = {}
                cov, ids = z['cov'], z['ids']
                nmesh = len(z['I'])
                for k in sorted(set(m['K'].tolist())):
                    sel = np.nonzero(m['K'] == k)[0]
                    if k < 4:
                        sel = sel[sel < nmesh]
                        # width of the edge: min coverage x P (um); current density mA/um
                        a, bnode = m['I'][sel], m['J'][sel]
                        wid = np.minimum(cov_of(z, k, a), cov_of(z, k, bnode)) * P
                        dens = np.abs(Ib[sel]) * 1e3 / np.maximum(wid, 1e-3)
                        # a cell edge only partly covered at a wire's side reads high: report the 99.9th
                        # percentile too, and the worst over edges whose width is at least half a cell
                        full_w = wid >= 0.5 * P
                        j = int(np.argmax(np.where(full_w, dens, 0)))
                        em[KNAME[k]] = {'worst': float(dens[j]), 'p999': float(np.percentile(dens, 99.9)),
                                        'xy': xy_of(z, k, a[j]), 'unit': 'mA/um'}
                    elif k in (10, 11, 12):
                        a = m['I'][sel]
                        ncut = m['G'][sel] * 4.5
                        dens = np.abs(Ib[sel]) * 1e3 / ncut
                        j = int(np.argmax(dens))
                        em[KNAME[k]] = {'worst': float(dens[j]), 'xy': xy_of(z, k - 10, a[j]), 'unit': 'mA/cut'}
                    elif k == 20:      # Via4 landings: sum the edges of each landing node
                        a = m['I'][sel]
                        tot = {}
                        for ai, ii, g in zip(a, Ib[sel], m['G'][sel]):
                            t = tot.setdefault(int(ai), [0.0, 0.0])
                            t[0] += ii
                            t[1] += g * 4.5
                        worst = max(tot.items(), key=lambda kv: abs(kv[1][0]) / kv[1][1])
                        em['Via4'] = {'worst': abs(worst[1][0]) * 1e3 / worst[1][1], 'unit': 'mA/cut',
                                      'landing_mA': abs(worst[1][0]) * 1e3}
                    elif k == 21:
                        sel21 = sel
                        wd = []
                        for e in sel21:
                            wd.append(0)
                        # Metal5 width from the strap list: worst current over the narrowest strap
                        imax = float(np.max(np.abs(Ib[sel21]))) * 1e3 if len(sel21) else 0.0
                        em['Metal5'] = {'worst_mA': imax, 'unit': 'mA (strap current)',
                                        'worst': imax / 8.75}
                for kk, e in em.items():
                    lim = {'Metal5': 1.5, 'Via4': 0.18}.get(kk, 0.67 if kk.startswith('Metal') else 0.18)
                    e['limit'] = lim
                    e['ratio'] = e['worst'] / lim
                tot_mA = sum(cur.values())
                rn['modes'][mo] = {'I_total_mA': tot_mA, 'switch_mV': vsw * 1e3, 'blocks': blk, 'em': em}
                if mo == 'all':
                    np.savez_compressed(os.path.join(OUT, f'map_{cname}_{net}.npz'),
                                        v=full[:m['nn']], ids=z['ids'], vsw=vsw)
            rn['T_ohm'] = T
            print(f'{cname} {net}: dropped {rn["dropped_nodes"]} nodes; '
                  + ', '.join(f"{b} {T[b][b]:.2f}" for b in T), flush=True)
            for mo in currents.MODES:
                d = rn['modes'][mo]
                w = max(d['blocks'].items(), key=lambda kv: kv[1]['worst_mV'] if kv[0] in currents.mode(mo)[net]
                        else -1)
                print(f'   {mo:4s} I {d["I_total_mA"]:6.2f} mA switch {d["switch_mV"]:6.2f} mV, worst '
                      f'{w[0]} {w[1]["worst_mV"]:.2f} mV (mean {w[1]["mean_mV"]:.2f}); EM '
                      + ', '.join(f"{k} {e['ratio']:.2f}" for k, e in d['em'].items()), flush=True)
    json.dump(res, open(os.path.join(OUT, 'result.json'), 'w'), indent=1)


def cov_of(z, k, nodes):
    ids = z['ids'][k]
    off = int(ids[ids >= 0].min())
    flat = np.full(int(ids.max()) - off + 1, 0.0)
    m = ids >= 0
    flat[ids[m] - off] = z['cov'][k][m]
    return flat[nodes - off]


def xy_of(z, k, node):
    ids = z['ids'][k]
    w = np.argwhere(ids == node)
    if not len(w):
        return None
    iy, ix = w[0]
    P = float(z['P'])
    return [round(float(ix * P), 2), round(float(iy * P), 2)]


if __name__ == '__main__':
    main()
