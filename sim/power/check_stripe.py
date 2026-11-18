"""Hand cross-check of the mesh: one Metal4 stripe's end-to-end R against Rsheet x squares.

The VAPWR stripe at x 49.52 um (2.0 um wide, y 5 .. 320.36 um) on its own: the Metal4 cells of the mesh inside the
stripe's x band, every other edge removed, R from the bottom row to the top row (both rows tied).

    python3 sim/power/check_stripe.py     (meshes from sim/power/mesh.py at 0.5 and 0.25 um)
"""
import os

import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as sla

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
X0, W, Y0, Y1, RS = 49.52, 2.0, 5.0, 320.36, 0.090


def main():
    hand = RS * (Y1 - Y0) / W
    print(f'hand: {RS} ohm/sq x {Y1 - Y0:.2f} / {W} um = {hand:.3f} ohm')
    for p in ('0.5', '0.25'):
        z = np.load(os.path.join(ROOT, 'build', 'power', f'mesh_p{p}', 'VAPWR.npz'))
        P = float(z['P'])
        ids = z['ids'][3]
        ix0, ix1 = int(np.floor(X0 / P)), int(np.ceil((X0 + W) / P))
        col = ids[:, ix0:ix1]
        nodes = set(col[col >= 0].tolist())
        I, J, G, K = z['I'], z['J'], z['G'], z['K']
        sel = (K == 3) & np.isin(I, list(nodes)) & np.isin(J, list(nodes))
        nl = sorted(nodes)
        idx = {n: k for k, n in enumerate(nl)}
        a = np.array([idx[i] for i in I[sel]]); b = np.array([idx[j] for j in J[sel]]); g = G[sel]
        n = len(nl)
        A = sp.coo_matrix((g, (a, b)), shape=(n, n)).tocsr()
        A = A + A.T
        Y = sp.diags(np.asarray(A.sum(axis=1)).ravel()) - A
        rows = [iy for iy in range(col.shape[0]) if (col[iy] >= 0).any()]
        bot = [idx[c] for c in col[rows[0]] if c >= 0]
        topr = [idx[c] for c in col[rows[-1]] if c >= 0]
        Y = Y.tolil()
        for t in bot:                       # bottom row grounded (big conductance)
            Y[t, t] += 1e9
        rhs = np.zeros(n)
        rhs[topr] = 1.0 / len(topr)
        v = sla.spsolve(Y.tocsc(), rhs)
        r = float(np.mean(v[topr]))
        span = (rows[-1] - rows[0]) * P
        print(f'mesh P {P} um: {r:.3f} ohm over {span:.2f} um of cell centres '
              f'(hand over the same span {RS * span / W:.3f} ohm, {100 * (r / (RS * span / W) - 1):+.1f} %)')


main()
