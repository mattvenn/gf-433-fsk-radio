"""a2 (the Q tap, red) against a0 (the I tap into lsdiv, blue) and the other ring nodes (light blue), Metal1-Metal4,
traced in the tile GDS. python3 layout/gen/fig/a2_vs_a0.py -> docs/img/a2_vs_a0.png"""
import klayout.db as db, matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Patch
ly = db.Layout(); ly.read('gds/tt_um_mattvenn_gf433_vco.gds'); top = ly.top_cell()
ly.flatten(top.cell_index(), -1, True)
L = {'m1': (34, 0), 'v1': (35, 0), 'm2': (36, 0), 'v2': (38, 0), 'm3': (42, 0), 'v3': (40, 0), 'm4': (46, 0)}
l2n = db.LayoutToNetlist(db.RecursiveShapeIterator(ly, top, []))
R = {k: l2n.make_layer(ly.layer(*v), k) for k, v in L.items()}
for a, v, b in [('m1', 'v1', 'm2'), ('m2', 'v2', 'm3'), ('m3', 'v3', 'm4')]:
    for x in (a, v, b): l2n.connect(R[x])
    l2n.connect(R[a], R[v]); l2n.connect(R[v], R[b])
l2n.extract_netlist()
SEED = {'a0': (312.7, 163.09), 'a1': (319.12, 164.09), 'a2': (324.67, 162.09), 'a3': (325.97, 164.09), 'a4': (323.02, 163.09)}
def boxes(net):
    out = []
    for k in ('m1', 'm2', 'm3', 'm4'):
        for p in l2n.shapes_of_net(net, R[k], True).merged().decompose_trapezoids_to_region().each():
            b = p.bbox(); out.append((b.left * ly.dbu, b.bottom * ly.dbu, b.right * ly.dbu, b.top * ly.dbu))
    return out
nets = {n: l2n.probe_net(R['m2'], db.DPoint(*xy)) for n, xy in SEED.items()}
X0, Y0, X1, Y1 = 250, 145, 335, 180
fig, ax = plt.subplots(figsize=(14, 6.5))
# everything else, faint
for k in ('m1', 'm2', 'm3', 'm4'):
    for p in db.Region(top.begin_shapes_rec(ly.layer(*L[k]))).merged().decompose_trapezoids_to_region().each():
        b = p.bbox(); b = (b.left * ly.dbu, b.bottom * ly.dbu, b.right * ly.dbu, b.top * ly.dbu)
        if b[2] < X0 or b[0] > X1 or b[3] < Y0 or b[1] > Y1: continue
        ax.add_patch(Rectangle(b[:2], b[2] - b[0], b[3] - b[1], fc='#000', ec='none', alpha=0.06))
STY = {'a2': ('#d62728', 1.0, 4), 'a0': ('#1f4fd6', 1.0, 4), 'a1': ('#7fb2ff', 0.8, 3), 'a3': ('#7fb2ff', 0.8, 3), 'a4': ('#7fb2ff', 0.8, 3)}
length = {}
for n, net in nets.items():
    c, a, z = STY[n]
    bs = boxes(net)
    length[n] = sum(max(b[2] - b[0], b[3] - b[1]) for b in bs)
    for b in bs:
        ax.add_patch(Rectangle(b[:2], b[2] - b[0], b[3] - b[1], fc=c, ec='none', alpha=a, zorder=z))
for name, (x0, y0, x1, y1) in {'vco_core': (272.01, 133.5, 382.59, 203.26), 'rx_lsq': (216.45, 107.2, 256.94, 161.95)}.items():
    ax.add_patch(Rectangle((x0, y0), x1 - x0, y1 - y0, fc='none', ec='k', ls='--', lw=0.8))
    ax.text(max(x0, X0) + 0.5, min(y1, Y1) - 0.5, name, va='top', fontsize=9)
ax.text(327, 157, 'the ring\n(5 nodes)', fontsize=9, ha='left')
ax.legend(handles=[Patch(fc='#d62728', label='a2 -> rx_lsq (Q tap): 19.0 fF'),
                   Patch(fc='#1f4fd6', label='a0 -> lsdiv (I tap, abutted): about 3.3 fF'),
                   Patch(fc='#7fb2ff', label='a1, a3, a4: about 3.0-3.5 fF')], loc='lower left', fontsize=9, framealpha=0.95)
ax.set_xlim(X0, X1); ax.set_ylim(Y0, Y1); ax.set_aspect('equal'); ax.set_xlabel('x (µm)'); ax.set_ylabel('y (µm)')
ax.set_title('The two LO taps on the ring: a2 (Q, red) runs about 80 µm to rx_lsq; a0 (I, blue) stays inside the core')
fig.tight_layout(); fig.savefig('docs/img/a2_vs_a0.png', dpi=130)
print({k: round(v, 1) for k, v in length.items()})
