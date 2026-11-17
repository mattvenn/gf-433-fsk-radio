#!/usr/bin/env python3
"""vco_core: the ring (ring_core_v3) + lsdiv as one cell for the tile floorplan (the vco_top split, 2026-11-17).

    python3 layout/gen/vco_core.py [--gds layout/vco_core.gds] [--out build/vco_tile] [--a2 w|n]
    python3 layout/gen/vco_core.py --decap [--gds layout/decap_ls.gds]     # the stand-alone VDD_LS decap cell

The same blocks and placements as layout/gen/vco_top.py (whose constants and decap helpers this reuses), without
cgm_ref and the main VDD_LS decap group (that one is the separate cell decap_ls): ring_core at (0, 0), lsdiv at
(-42.39, 31.455) with its a0 abutment (no a0 wire), and the short VDD_LS decap fingers under lsdiv (cell
vco_core_dcap, drawn by magic). Coordinates below are the core's (= vco_top's); the cell's bbox is
x -42.39 ... 68.19, y -4.0 ... 65.76 (110.58 x 69.76 um): the tile's own frame is that bbox's lower-left = (0, 0).

Pins (layout/floorplan/pins.md, vco.core; the tile places the cell MX):
  N edge (y 65.76): ls (lsdiv's own M3 port, x 21 of the own frame), vctrl (M3 riser at x 67.69 from the core's
         vctrl M2 track, y 12.935, over the core's right edge where the core has no M3)
  S edge (y -4.0):  vg (the core's M3 pin)
  W edge (x -42.39): a2 (M2, y 28.3: M3 drop from the core's a2 M2 at x 9.0 to the 1.4 um gap between the decap's
         strap and lsdiv's VSS rail, then M2 to the edge). --a2 n: M3 straight up to the N edge instead (x 9.0).
  E edge (x 68.19), bottom to top: bit4 bitb4 ... bit0 bitb0 (M2, staircase from the core's M3 bit pins), vbnf (M2,
         from an M3 riser at x 29.79 on the core's vbn track, left of every bit), a VDD M2 shield, ck (M2 at the top:
         M3 riser in lsdiv at its ck pin, M2 lane through lsdiv's passive band, y 62.19).
Supplies (M3 for the tile's Metal4 stripes, via3):
  VSS    : 2.4 um M3 strap along the whole bottom (y -2.4 ... 0, gap at vg), via2s onto the M2 rails;
  VDD    : the core's two VDD M3 risers (x 20.92 / 26.92) carried up to an M3 strap along the top (y 60.8 ... 65.76,
           x 20.92 ... 66.9);
  VDD_LS : M3 over lsdiv's VDD rail (y 41.17 ... 43.57, x -39.99 ... -6.69 with a gap at lsdiv's ls riser) and down
           to the under-lsdiv decap strap (x -37.39 ... -24.39): separate from VDD.
No Metal4 / Metal5.
"""
import argparse, json, os, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ring_core import Cell  # noqa: E402
import vco_top as vt  # noqa: E402

REPO = HERE.parents[1]
LS = vt.LS                       # lsdiv origin (-42.39, 31.455)
XL, XR = LS[0], 67190 + vt.CORE_DX  # cell left (lsdiv's left edge) and right (the core's right edge)
YB, YT = vt.YBOT, LS[1] + 34305   # cell bottom (the core's vg pin) and top (lsdiv's top, its ls port)
UX0 = XL + 400                    # under-lsdiv decap group: strap left edge on the cell's left edge
A2_Y = 28300                      # a2 lane (W option) between the decap strap (top 27.655) and lsdiv's VSS rail (29.055)
A2_X = 9000                       # a2 M3 drop / riser on the core's a2 M2 (x 8.235 ... 12.31, y 36.98 ... 37.36)
A2_CY = 37170
CK_Y = 62190                      # ck M2 lane: lsdiv y 30.735, 0.68 um under lsdiv's top VSS rail
CK_X = LS[0] + 1810               # ck M3 riser in lsdiv (lsdiv x 1.62 ... 2.0), via2 on its ck M2 (x 0 ... 2.32)
VBR_X = 29790                     # vbnf M3 riser, left of bitb0's riser (31.45)
VBNF_Y = 59990
SH_Y = (60800, 61400)             # VDD M2 shield between vbnf and ck
VDD_M3 = (20920, 60800, 66900, YT)
VCT_X = 67690                     # vctrl M3 riser
BIT_Y0, BIT_P = 51790, 800        # bit M2 tracks: rightmost bit lowest
BITS = ["bitb0", "bit0", "bitb1", "bit1", "bitb2", "bit2", "bitb3", "bit3", "bitb4", "bit4"]   # left to right
VDDLS_A = (LS[0] + 2400, LS[0] + 20400)   # VDD_LS M3 on lsdiv's VDD rail, between the ck riser and the ls riser
VDDLS_B = (LS[0] + 21500, LS[0] + 35700)  # ... between the ls riser and the lf riser
VDDLS_V = (LS[0] + 5000, LS[0] + 18000)   # ... and down to the decap strap


def dcap_cell():
    """vco_core_dcap: the under-lsdiv VDD_LS decap group + the VSS rail from the cell's left edge to the core."""
    c = Cell("vco_core_dcap")
    g = vt.DRAW["under"]
    x1, s_b, s_t = vt.decap_group(c, UX0, vt.um(g["w"]), g["nf"])
    assert s_t < vt.TAP_TOP and x1 < -1900, (s_t, x1)
    vt.vss_rail(c, XL, vt.RAIL_END, vt.RAIL_END - 1300)
    c.label("VSS", "m2", XL + 1000, (vt.VSS_B + vt.VSS_T) // 2, port=True)
    c.label("VDD_LS", "m2", UX0 + 1000, (s_b + s_t) // 2, port=True)
    return c, dict(strap=(UX0 - 400, s_b, x1, s_t))


def magic_gds(c, out, gds):
    tcl = "drc off\nsnap internal\n" + c.tcl() + f"load {c.name}\nselect top cell\nexpand\ngds write {gds}\nquit -noprompt\n"
    (out / f"{c.name}.tcl").write_text(tcl)
    rc = f"{os.environ.get('PDK_ROOT', '/foss/pdks')}/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc"
    for old in out.glob(f"{c.name}.mag"):
        old.unlink()
    r = subprocess.run(["magic", "-rcfile", rc, "-noconsole", "-dnull", f"{c.name}.tcl"], cwd=out,
                       capture_output=True, text=True)
    (out / f"magic_{c.name}.log").write_text(r.stdout + r.stderr)
    assert Path(gds).exists(), f"magic did not write {gds}"


def assemble(dgds, dinfo, dst, a2="w"):
    import klayout.db as db
    ly = db.Layout()
    ly.dbu = 0.001
    for f in (REPO / "layout/ring_core_v3.gds", REPO / "layout/lsdiv.gds", dgds):
        ly.read(str(f))
    top = ly.create_cell("vco_core")
    for name, (x, y) in (("ring_core", vt.CORE), ("lsdiv", LS), ("vco_core_dcap", (0, 0))):
        top.insert(db.CellInstArray(ly.cell(name).cell_index(), db.Trans(db.Vector(x, y))))
    L = {k: ly.layer(*v) for k, v in dict(m1=(34, 0), v1=(35, 0), m2=(36, 0), v2=(38, 0), m3=(42, 0),
                                          m2t=(36, 10), m3t=(42, 10)).items()}

    def r(layer, x1, y1, x2, y2):
        x1, x2 = sorted((x1, x2)); y1, y2 = sorted((y1, y2))
        top.shapes(L[layer]).insert(db.Box(x1, y1, x2, y2))

    def v2(x, y):                               # one 0.26 um via2 cut (V2.1), M2 / M3 drawn by the caller
        r("v2", x - 130, y - 130, x + 130, y + 130)

    pins = {}

    def lab(text, layer, x, y, edge):
        top.shapes(L[layer + "t"]).insert(db.Text(text, db.Trans(db.Vector(x, y))))
        pins[text] = [round((x - XL) / 1000, 3), round((y - YB) / 1000, 3), edge, {"m2": "Metal2", "m3": "Metal3"}[layer]]

    # ---- VSS: M2 bridge decap rail -> core rail; 2.4 um M3 strap along the bottom (gap at vg) ----
    r("m2", vt.RAIL_END - 500, vt.VSS_B, -500, vt.VSS_T)
    vg_gap = (vt.VG_X[0] - 600, vt.VG_X[1] + 600)
    m3_vss = [(XL, vg_gap[0]), (vg_gap[1], XR)]
    for (a, b) in m3_vss:
        r("m3", a, vt.VSS_B, b, vt.VSS_T)
        x = a + 300
        while x <= min(b, 66800) - 300:         # the M2 rails end at x 67.21
            v2(x, -1200)
            x += 2000
    lsx = LS[0] + 300                           # lsdiv's left M3 VSS strap down into the bottom rail (as vco_top)
    r("m3", lsx, vt.VSS_B, lsx + 1000, LS[1] + 500)
    r("m3", lsx, vt.VSS_B, lsx + 4000, LS[1] - 500)
    lab("VSS", "m3", -20000, (vt.VSS_B + vt.VSS_T) // 2, "S")
    # ---- VDD: the core's M3 risers up to a top M3 strap; M2 shield between vbnf and ck ----
    for xa in (20920, 26920):
        r("m3", xa, 45000, xa + 1000, VDD_M3[1] + 100)
    r("m3", *VDD_M3)
    r("m2", VDD_M3[0], SH_Y[0], XR, SH_Y[1])
    for x in range(VDD_M3[0] + 500, VDD_M3[2] - 400, 1000):
        v2(x, (SH_Y[0] + SH_Y[1]) // 2)
    lab("VDD", "m3", 45000, (VDD_M3[1] + VDD_M3[3]) // 2, "N")
    # ---- VDD_LS: M3 on lsdiv's VDD rail (via2s between its via1s) and down to the decap strap ----
    lv = (vt.LS_VDD[0], vt.LS_VDD[1])
    for (a, b) in (VDDLS_A, VDDLS_B):
        r("m3", a, lv[0], b, lv[1])
        x = LS[0] + 1570
        while x <= b - 300:
            if x >= a + 300:
                for y in (lv[0] + 600, lv[0] + 1200, lv[0] + 1800):
                    v2(x, y)
            x += 2000
    sx0, sb, sx1, st = dinfo["strap"]
    r("m3", VDDLS_V[0], sb, VDDLS_V[1], lv[1])
    for x in range(VDDLS_V[0] + 500, VDDLS_V[1] - 300, 1000):
        v2(x, (sb + st) // 2)
    lab("VDD_LS", "m3", (VDDLS_A[0] + VDDLS_A[1]) // 2, (lv[0] + lv[1]) // 2, "-")
    # ---- vctrl: via2 on the core's vctrl M2 track, M3 riser to the N edge ----
    vy = 12935
    r("m3", VCT_X - 190, vy - 190, VCT_X + 190, YT)
    v2(VCT_X, vy)
    lab("vctrl", "m3", VCT_X, YT - 200, "N")
    # ---- bits: M3 risers up from the core's pins, via2, M2 to the E edge (staircase, no crossings) ----
    # CORE_BITS_X is ordered as vco_top's names list (bitb0, bit0, bitb1, ...), left to right
    for i, ((a, b), nm) in enumerate(zip(vt.CORE_BITS_X, BITS)):
        y = BIT_Y0 + (len(BITS) - 1 - i) * BIT_P
        cx = (a + b) // 2
        r("m3", a, vt.CORE_TOP - 400, b, y + 190)
        r("m2", a, y - 190, XR, y + 190)
        v2(cx, y)
        lab(nm, "m2", XR - 100, y, "E")
    # ---- vbnf: the core's vbn M2 track extended left, M3 riser left of the bits, M2 to the E edge ----
    r("m2", VBR_X - 190, 42475, 33500, 42855)
    v2(VBR_X, 42665)
    r("m3", VBR_X - 190, 42475, VBR_X + 190, VBNF_Y + 190)
    v2(VBR_X, VBNF_Y)
    r("m2", VBR_X - 190, VBNF_Y - 190, XR, VBNF_Y + 190)
    lab("vbnf", "m2", XR - 100, VBNF_Y, "E")
    # ---- ck: via2 on lsdiv's ck M2, M3 riser in lsdiv, M2 lane through lsdiv's passive band to the E edge ----
    cky0 = LS[1] + 2940
    r("m3", CK_X - 190, cky0 - 190, CK_X + 190, CK_Y + 190)
    v2(CK_X, cky0)
    v2(CK_X, CK_Y)
    r("m2", CK_X - 190, CK_Y - 190, XR, CK_Y + 190)
    lab("ck", "m2", XR - 100, CK_Y, "E")
    # ---- a2 ----
    v2(A2_X, A2_CY)
    if a2 == "w":
        r("m3", A2_X - 190, A2_Y - 190, A2_X + 190, A2_CY + 190)
        v2(A2_X, A2_Y)
        r("m2", XL, A2_Y - 190, A2_X + 190, A2_Y + 190)
        lab("a2", "m2", XL + 100, A2_Y, "W")
    else:
        r("m3", A2_X - 190, A2_CY - 190, A2_X + 190, YT)
        lab("a2", "m3", A2_X, YT - 200, "N")
    # ---- pins that are the blocks' own ----
    lab("vg", "m3", (vt.VG_X[0] + vt.VG_X[1]) // 2, YB + 300, "S")
    lab("ls", "m3", LS[0] + (vt.LS_PIN[0] + vt.LS_PIN[1]) // 2, YT - 200, "N")
    pins["VSS"][2] = "S (M3 strap y -2.4 ... 0 core coords)"
    for li in ly.layer_indexes():
        info_l = ly.get_info(li)
        if info_l.layer in (46, 81, 41, 82) and not db.Region(top.begin_shapes_rec(li)).is_empty():
            raise SystemExit(f"Metal4/5 or via3/4 found on {info_l}")
    ly.write(str(dst))
    bb = top.dbbox()
    assert abs(bb.left * 1000 - XL) < 1 and abs(bb.right * 1000 - XR) < 1 and abs(bb.bottom * 1000 - YB) < 1 \
        and abs(bb.top * 1000 - YT) < 1, bb
    m3 = dict(VSS=[[(a - XL) / 1000, (vt.VSS_B - YB) / 1000, (b - XL) / 1000, (vt.VSS_T - YB) / 1000] for a, b in m3_vss],
              VDD=[[(VDD_M3[0] - XL) / 1000, (VDD_M3[1] - YB) / 1000, (VDD_M3[2] - XL) / 1000, (VDD_M3[3] - YB) / 1000]],
              VDD_LS=[[(a - XL) / 1000, (lv[0] - YB) / 1000, (b - XL) / 1000, (lv[1] - YB) / 1000] for a, b in
                      (VDDLS_A, VDDLS_B)] + [[(VDDLS_V[0] - XL) / 1000, (sb - YB) / 1000, (VDDLS_V[1] - XL) / 1000,
                                              (lv[1] - YB) / 1000]])
    return dict(bbox=[bb.left, bb.bottom, bb.right, bb.top], origin=[bb.left, bb.bottom], pins=pins, m3_rails=m3,
                cells=sorted(c.name for c in ly.each_cell()))


def build_decap(gds, out):
    c, info = vt.decap_cell(m3=True)
    magic_gds(c, out, gds)
    import klayout.db as db
    ly = db.Layout(); ly.read(str(gds)); bb = ly.cell("decap_ls").dbbox()
    o = (bb.left, bb.bottom)
    m3 = {k: [[(v[0] / 1000 - o[0]), (v[1] / 1000 - o[1]), (v[2] / 1000 - o[0]), (v[3] / 1000 - o[1])]]
          for k, v in info["m3"].items()}
    return dict(bbox=[bb.left, bb.bottom, bb.right, bb.top], origin=list(o), m3_rails=m3,
                pins=dict(VSS=[round(1.0 - o[0], 3), round(-1.2 - o[1], 3), "S", "Metal2/Metal3"],
                          VDD_LS=[round(1.0 - o[0], 3), round((info["strap"][1] + info["strap"][3]) / 2000 - o[1], 3),
                                  "N", "Metal2/Metal3"]),
                gate_area_um2=vt.DRAW["main"]["nf"] * vt.DRAW["main"]["w"] * vt.DCLS["l"])



# ---- LVS sources (layout/gen/check_core.sh and lvs/make_source.py) --------------------------------------------------
CORE_PORTS = "VDD VDD_LS VSS vctrl bit0 bit1 bit2 bit3 bit4 bitb0 bitb1 bitb2 bitb3 bitb4 ck vg ls vbnf a2".split()


def lvs_source(t):
    """The xschem vco_top netlist (text) -> the same with vco_top replaced by vco_core (the ring + lsdiv + the short
    VDD_LS fingers under lsdiv, XDCU: 3 x 26 / 10 um) and the cgm_ref subckt dropped; lsdiv's "Cc a0 net1 2e-15"
    removed (drawn as M2 / M3 fingers: parasitic C, not a device)."""
    import re
    t, ncc = re.subn(r"^Cc a0 net1 2e-15\n", "", t, flags=re.M)
    t, nref = re.subn(r"^\.subckt cgm_ref .*?^\.ends\n", "", t, flags=re.M | re.S)
    blk = re.search(r"^\.subckt vco_top .*?^\.ends\n", t, flags=re.M | re.S).group(0)
    core = re.search(r"^xcore .*$", blk, flags=re.M).group(0)
    ls = re.search(r"^xls .*$", blk, flags=re.M).group(0)
    g = vt.DRAW["under"]
    new = (f".subckt vco_core {' '.join(CORE_PORTS)}\n{core}\n{ls}\n"
           f"XDCU VSS VDD_LS VSS VSS nfet_03v3 L={vt.DCLS['l']:.1f}u W={g['w']:.1f}u nf=1 ad=0 as=0 pd=0 ps=0 nrd=0 "
           f"nrs=0 sa=0 sb=0 sd=0 m={g['nf']}\n.ends\n")
    assert ncc == 1 and nref == 1, (ncc, nref)
    return t.replace(blk, new)


def decap_ls_source():
    """decap_ls: the main VDD_LS decap group of vco_top (vco_top.py DRAW["main"])."""
    g = vt.DRAW["main"]
    return (".subckt decap_ls VDD_LS VSS\n"
            f"XDC VSS VDD_LS VSS VSS nfet_03v3 L={vt.DCLS['l']:.1f}u W={g['w']:.1f}u nf=1 ad=0 as=0 pd=0 ps=0 nrd=0 "
            f"nrs=0 sa=0 sb=0 sd=0 m={g['nf']}\n.ends decap_ls")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gds", default=None)
    ap.add_argument("--out", default=str(REPO / "build" / "vco_tile"))
    ap.add_argument("--a2", default="w", choices=["w", "n"])
    ap.add_argument("--decap", action="store_true", help="write the stand-alone decap_ls cell instead")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.decap:
        gds = Path(a.gds or REPO / "layout" / "decap_ls.gds").resolve()
        meta = build_decap(gds, out)
        (out / "decap_ls_meta.json").write_text(json.dumps(meta, indent=1))
        bb = meta["bbox"]
        print(f"decap_ls {bb[2] - bb[0]:.3f} x {bb[3] - bb[1]:.3f} um -> {gds}")
        return
    gds = Path(a.gds or REPO / "layout" / "vco_core.gds").resolve()
    c, dinfo = dcap_cell()
    dgds = out / "vco_core_dcap.gds"
    magic_gds(c, out, dgds.resolve())
    meta = assemble(dgds, dinfo, gds, a.a2)
    (out / f"vco_core_meta{'' if a.a2 == 'w' else '_a2n'}.json").write_text(json.dumps(meta, indent=1))
    bb = meta["bbox"]
    print(f"vco_core {bb[2] - bb[0]:.3f} x {bb[3] - bb[1]:.3f} um, bbox origin {bb[0]}, {bb[1]} -> {gds}")
    for k, v in meta["pins"].items():
        print(f"  {k:7s} {v}")


if __name__ == "__main__":
    main()
