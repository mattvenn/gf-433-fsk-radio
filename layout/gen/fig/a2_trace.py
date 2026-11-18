import json, sys, klayout.db as db
ly = db.Layout(); ly.read('gds/tt_um_mattvenn_gf433_vco.gds'); top = ly.top_cell()
ly.flatten(top.cell_index(), -1, True)
L = {'poly': (30,0), 'cont': (33,0), 'm1': (34,0), 'v1': (35,0), 'm2': (36,0), 'v2': (38,0), 'm3': (42,0), 'v3': (40,0), 'm4': (46,0)}
l2n = db.LayoutToNetlist(db.RecursiveShapeIterator(ly, top, []))
R = {k: l2n.make_layer(ly.layer(*v), k) for k, v in L.items()}
for a, v, b in [('m1','v1','m2'), ('m2','v2','m3'), ('m3','v3','m4')]:
    l2n.connect(R[a]); l2n.connect(R[v]); l2n.connect(R[b]); l2n.connect(R[a], R[v]); l2n.connect(R[v], R[b])
l2n.extract_netlist()
m = json.load(open('build/tile/meta.json'))
seeds = {n: p[0] for n, p in m['net_points'].items()}
H = top.dbbox().height()
for net, x, w, *_ in m['stripes']:
    seeds.setdefault(net, ('m4', x + w / 2, H / 2, ''))
out = {}
for net, (lay, x, y, *_ ) in seeds.items():
    n = l2n.probe_net(R[lay], db.DPoint(x, y))
    if n is None: continue
    shp = {}
    for k in ('m1', 'm2', 'm3', 'm4'):
        reg = l2n.shapes_of_net(n, R[k], True)
        shp[k] = [[b.left*ly.dbu, b.bottom*ly.dbu, b.right*ly.dbu, b.top*ly.dbu] for b in (p.bbox() for p in reg.merged().decompose_trapezoids_to_region().each())]
    out[net] = shp
json.dump(out, open('build/a2fig/nets.json', 'w'))
print(len(out), 'nets;', 'a2 shapes', {k: len(v) for k, v in out['a2'].items()}, 'ls', {k: len(v) for k, v in out['ls'].items()})
