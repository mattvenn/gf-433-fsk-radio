"""Grid maze router for the tile (layout/gen/tile.py): three layers on one 0.68 um grid,
M2 (horizontal preferred), M3 (vertical preferred) and M4 (vertical preferred, over the blocks that allow it).

The grid is a numpy array own[layer, i, j]: 0 free, -1 obstacle, k > 0 the net id that owns the node. A wire is
0.38 um wide on a 0.68 um pitch (0.30 um space). Routing is A* from one end to the tree built so far, net by net;
`cost` adds a per-net penalty map (e.g. keep a clock away from a bias wire).
"""
import heapq

import numpy as np

P = 680                  # grid pitch (nm)
HW = 190                 # half wire width
CLR = HW + 300           # wire centre to an obstacle edge
LAYERS = ('m2', 'm3', 'm4')
VIA = {(0, 1): 'v2', (1, 2): 'v3'}
# step cost: [layer][0 = along x, 1 = along y]
STEP = ((1, 4), (4, 1), (6, 1))
VCOST = (4, 6)           # via2, via3


class Grid:
    def __init__(self, w, h):
        self.nx, self.ny = w // P + 1, h // P + 1
        self.own = np.zeros((3, self.nx, self.ny), dtype=np.int32)
        self.pen = None                     # optional extra cost per node, set per net
        self.m4mask = np.zeros((self.nx, self.ny), dtype=bool)   # Metal4 nodes only some nets may use
        # the outermost ring of nodes is unusable (wires would leave the tile)
        self.own[:, 0, :] = -1
        self.own[:, :, 0] = -1
        self.own[:, -1, :] = -1
        self.own[:, :, -1] = -1
        self.w, self.h = w, h
        self.own[:, :, self.ny - 1] = -1
        for i in range(self.nx):
            if i * P + HW > w - 100:
                self.own[:, i, :] = -1
        for j in range(self.ny):
            if j * P + HW > h - 100:
                self.own[:, :, j] = -1

    @staticmethod
    def X(i):
        return i * P

    Y = X

    def ij(self, x, y):
        return int(round(x / P)), int(round(y / P))

    def span(self, a, b, clr):
        """index range of nodes whose centre lies within [a - clr, b + clr]"""
        lo = max(0, -(-(a - clr) // P))
        hi = (b + clr) // P
        return lo, hi

    def block(self, l, x0, y0, x1, y1, owner=-1, clr=CLR, force=True):
        i0, i1 = self.span(x0, x1, clr)
        j0, j1 = self.span(y0, y1, clr)
        i1, j1 = min(i1, self.nx - 1), min(j1, self.ny - 1)
        if i0 > i1 or j0 > j1:
            return
        v = self.own[l, i0:i1 + 1, j0:j1 + 1]
        if force or owner == -1:
            if owner == -1:
                v[...] = -1
            else:
                v[v == 0] = owner
        else:
            v[v == 0] = owner

    def free(self, l, i, j, net):
        o = self.own[l, i, j]
        return o == 0 or o == net

    def route(self, srcs, dsts, net, allow=(True, True, True), bias=None, m4mask_ok=False):
        """A* from any of srcs to any node of dsts (sets of (l, i, j)). Returns the node path or None."""
        dl = list(dsts)
        dx = np.array([d[1] for d in dl])
        dy = np.array([d[2] for d in dl])
        if len(dl) > 400:                       # heuristic on a sample (admissible enough: it is a lower bound
            sel = np.linspace(0, len(dl) - 1, 400).astype(int)     # only when the sample holds the nearest)
            dx, dy = dx[sel], dy[sel]

        def h(i, j):
            return int(np.min(np.abs(dx - i) + np.abs(dy - j)))
        own, pen = self.own, self.pen
        mask = None if m4mask_ok else self.m4mask
        nx, ny = self.nx, self.ny
        pq = []
        cost = {}
        prev = {}
        for s in srcs:
            cost[s] = 0
            prev[s] = None
            heapq.heappush(pq, (h(s[1], s[2]), 0, s))
        dset = set(dsts)
        while pq:
            f, g, n = heapq.heappop(pq)
            if n in dset:
                path = []
                while n is not None:
                    path.append(n)
                    n = prev[n]
                return path[::-1]
            if g > cost.get(n, 1 << 60):
                continue
            l, i, j = n
            nb = [(l, i + 1, j, STEP[l][0]), (l, i - 1, j, STEP[l][0]), (l, i, j + 1, STEP[l][1]),
                  (l, i, j - 1, STEP[l][1])]
            if l > 0 and allow[l - 1]:
                nb.append((l - 1, i, j, VCOST[l - 1]))
            if l < 2 and allow[l + 1]:
                nb.append((l + 1, i, j, VCOST[l]))
            for (ml, mi, mj, c) in nb:
                if not (0 <= mi < nx and 0 <= mj < ny):
                    continue
                o = own[ml, mi, mj]
                if o != 0 and o != net:
                    continue
                if ml == 2 and mask is not None and mask[mi, mj]:
                    continue
                if ml != l:                     # a via needs both its nodes free
                    o2 = own[l, i, j]
                    if o2 != 0 and o2 != net:
                        continue
                g2 = g + c
                if pen is not None:
                    g2 += int(pen[ml, mi, mj])
                m = (ml, mi, mj)
                if g2 < cost.get(m, 1 << 60):
                    cost[m] = g2
                    prev[m] = n
                    heapq.heappush(pq, (g2 + h(mi, mj), g2, m))
        return None


def path_shapes(path):
    """[(layer name, x0, y0, x1, y1)] for a node path: one rectangle per straight run, a via + pads per layer change."""
    out = []
    k = 0
    while k < len(path) - 1:
        a, b = path[k], path[k + 1]
        if a[0] != b[0]:
            lo, hi = sorted((a[0], b[0]))
            x, y = Grid.X(a[1]), Grid.Y(a[2])
            out.append((LAYERS[lo], x - HW, y - HW, x + HW, y + HW))
            out.append((LAYERS[hi], x - HW, y - HW, x + HW, y + HW))
            out.append((VIA[(lo, hi)], x - 130, y - 130, x + 130, y + 130))
            k += 1
            continue
        # straight run on one layer in one direction
        m = k + 1
        d = (b[1] - a[1], b[2] - a[2])
        while m + 1 < len(path) and path[m + 1][0] == a[0] and (path[m + 1][1] - path[m][1],
                                                                  path[m + 1][2] - path[m][2]) == d:
            m += 1
        e = path[m]
        xa, ya, xb, yb = Grid.X(a[1]), Grid.Y(a[2]), Grid.X(e[1]), Grid.Y(e[2])
        out.append((LAYERS[a[0]], min(xa, xb) - HW, min(ya, yb) - HW, max(xa, xb) + HW, max(ya, yb) + HW))
        k = m
    return out
