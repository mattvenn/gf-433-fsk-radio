"""Write macro/tx_fine/pin_order.cfg from the floorplan (layout/floorplan/floorplan.json, pins_moved.xmac).

The macro is placed MY in the tile, so its own E edge faces west (towards mdac and the TT pins) and its own S edge
faces south (towards the ring and the receiver). LibreLane's sides are the macro's own frame, so the floorplan's own
edges map one to one: #E bottom -> top, #S left -> right.

LibreLane's io_place spaces the listed pins evenly over the edge's pin slots; `$N` leaves N empty slots. With
@min_distance = 2 tracks (1.12 um) and as many pins + gaps as there are slots minus one, slot k sits at
0.28 + 1.12 k um, so each pin goes in the slot nearest its floorplan target (moved up / down to the next free one).
(io_place has no comment syntax, so the cfg itself carries no header.)
Run: python3 macro/tx_fine/make_pin_order.py [die_w die_h]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
W, H = (float(sys.argv[1]), float(sys.argv[2])) if len(sys.argv) > 2 else (250.0, 176.8)
# the TT-facing pins: on the N edge (2026-11-17, step 3: under the TT pins they go to, not on the west face), at the
# own east end (MY: the tile's west end), in the order of their TT pins along the tile's top edge (own frame: reversed)
TOPN = ['clk', 'rst_n', 'fsk', 'sclk', 'mosi', 'cs_n', 'ck_o', 'div16', 'div64', 'div1024', 'miso']
PITCH, ORG, STEP = 0.56, 0.28, 2          # Metal2 / Metal3 tracks, every 2nd one


def slots(length):
    n = 0
    while ORG + n * PITCH < length:
        n += 1
    return len(range(0, n, STEP))      # pin tracks on this side


def side_list(pins, length):
    """pins: [(name, pos)] -> the cfg lines (names and $gaps), and the slot positions used."""
    n = slots(length) - 1                    # pins + gaps = slots - 1: one slot per 1.12 um from the bottom / left
    taken = {}
    for name, pos in sorted(pins, key=lambda p: p[1]):
        k = max(0, min(n - 1, round((pos - ORG) / (PITCH * STEP))))
        while k in taken.values():
            k += 1
        taken[name] = k
    names = sorted(taken, key=lambda m: taken[m])
    for i in range(len(names) - 1, -1, -1):          # pins crowded at the top end: push them back down
        cap = n - 1 if i == len(names) - 1 else taken[names[i + 1]] - 1
        taken[names[i]] = min(taken[names[i]], cap)
    assert taken[names[0]] >= 0 and len(set(taken.values())) == len(names), "no slots left"
    out, last = [], -1
    for name, k in sorted(taken.items(), key=lambda t: t[1]):
        if k - last - 1 > 0:
            out.append(f"${k - last - 1}")
        out.append(name.replace("[", r"\[").replace("]", r"\]"))
        last = k
    if n - 1 - last > 0:
        out.append(f"${n - 1 - last}")
    return out, {nm: ORG + k * PITCH * STEP for nm, k in taken.items()}


FPJ = Path(sys.argv[3]) if len(sys.argv) > 3 else ROOT / "layout/floorplan/floorplan.json"
fp = json.load(open(FPJ))
# the agreed floorplan's pin targets (variant B, pins_moved.xmac, kept here since the floorplan no longer moves pins)
pm = json.load(open(ROOT / "macro/tx_fine/floorplan_pins.json"))
east = [(n, xy[1]) for n, xy in pm.items() if abs(xy[0] - 249.75) < 0.01 and xy[1] > 0 and n not in TOPN]
# the 37 DAC lines: level with mdac's real pins (its control lines are fixed by its PMOS rows: pairs 0.68 um apart,
# 4.58 um pair pitch), not the floorplan's fitted targets, so the gap between the two needs only sub-um jogs.
# Both are placed without a y flip (MY), so macro own y = mdac own y + mdac y - macro y.
blk = {b['inst']: b for b in fp['blocks']}
mpins = json.load(open(ROOT / "layout/floorplan/blocks.json"))['mdac']['pins']
dy = blk['xmdac']['y'] - blk['xmac']['y']


def mdac_pin(n):
    if n == 'dac_sdn':
        return 'nsd'
    k = int(n.split('[')[1][:-1])
    return f"ns{k + 1}" if n.startswith('dac_tn') else f"nb{k}"


east = [(n, mpins[mdac_pin(n)]['y'] + dy if n.startswith('dac_') else y) for n, y in east]
south = [(n, xy[0]) for n, xy in pm.items() if n not in dict(east) and n not in TOPN]
north = [(n, W - 13.0 + 1.12 * k) for k, n in enumerate(TOPN)]
assert len(east) + len(south) + len(north) == len(pm)
e_lines, e_pos = side_list(east, H)
s_lines, s_pos = side_list(south, W)
n_lines, n_pos = side_list(north, W)
cfg = ["@min_distance=1.12", "#E"] + e_lines + ["#S"] + s_lines + ["#N"] + n_lines + ["#W"]
(ROOT / "macro/tx_fine/pin_order.cfg").write_text("\n".join(cfg) + "\n")
worst = max(abs(e_pos[n] - p) for n, p in east)
worst_s = max(abs(s_pos[n] - p) for n, p in south)
print(f"E {len(east)} pins, S {len(south)} pins; worst offset from the target E {worst:.2f} / S {worst_s:.2f} um")
json.dump({"E": e_pos, "S": s_pos, "N": n_pos}, open(ROOT / "macro/tx_fine/pin_targets.json", "w"), indent=1)
