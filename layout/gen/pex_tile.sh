#!/bin/bash
# Parasitic extraction of the whole tile without the tx_fine macro, for the extracted-tile sims (sim/top/tb_tile.py).
# Usage (repo root): bash layout/gen/pex_tile.sh [lvs|c|rc] [gds]
#   lvs: devices + connectivity; c: + C (cthresh 0, coupling C kept); rc: + R (extresist), then rcfix.py -> _rcx
# Writes layout/pex/tile_<mode>.spice: .subckt tile_<mode> <ports>, ports = the TT pins (template labels) + the three
# supplies + every other net of layout/gen/tile_nets.py that joins two blocks (labelled at one block-pin end from
# build/tile/meta.json net_points, made a port), so a testbench drives / probes them by name: the macro's outputs
# (DAC lines, rx_en, dbg_sel, ...) are driven by sources, its inputs (ck, ...) are probed.
# - the macro (tx_fine) is deleted before extraction: its standard cells would add ~10k devices that a transistor-
#   level analog run doesn't need; the routed wires up to its pins stay (their C is extracted).
# - magic 8.3.642 (MAGIC=...): 8.3.684 drops node-to-substrate C (CLAUDE.md).
# - the n-well resistor is repainted as rnw in cgm_ref (as check_tt.sh / pex_top.sh).
# - rc: always simulate the _rcx file (rcfix.py removes the double-counted port coupling, docs/rc_extraction_fix.md).
set -eu
MODE=${1:-c}
REPO=$(pwd)
GDS=$(realpath "${2:-gds/tt_um_mattvenn_gf433_vco.gds}")
T=tt_um_mattvenn_gf433_vco
B=tile
MAGIC=${MAGIC:-$( [ -x $HOME/.local/magic642/bin/magic ] && echo $HOME/.local/magic642/bin/magic || echo magic)}
OUT=$REPO/build/pex/${B}_$MODE
mkdir -p "$OUT" "$REPO/layout/pex"; cd "$OUT"
rm -f *.ext *.res.ext *.sim *.nodes
export PDK_ROOT=${PDK_ROOT:-/foss/pdks} PDK=gf180mcuD
RC=$PDK_ROOT/$PDK/libs.tech/magic/$PDK.magicrc
META=$REPO/build/tile/meta.json
[ -f "$META" ] && grep -q net_points "$META" || { echo "ERROR: $META has no net_points (run layout/gen/tile.py)"; exit 1; }

# 1. the tile without the macro
python3 - "$GDS" "$OUT/${B}_nomac.gds" <<'PYEOF'
import sys, klayout.db as db
ly = db.Layout(); ly.read(sys.argv[1]); top = ly.top_cell()
n = 0
for inst in list(top.each_inst()):
    if inst.cell.name == 'tx_fine':
        inst.delete(); n += 1
assert n == 1, n
ly.cleanup()
ly.write(sys.argv[2])
print('macro instances removed:', n)
PYEOF
# 2. rnw repaint (cgm_ref's own coordinates) and the net labels / ports
python3 - "$GDS" > rnwfix.tcl <<'PYEOF'
import sys, klayout.db as db
ly = db.Layout(); ly.read(sys.argv[1]); c = ly.cell("cgm_ref")
r = db.Region(c.begin_shapes_rec(ly.find_layer(21, 0))) & db.Region(c.begin_shapes_rec(ly.find_layer(110, 5)))
print("load cgm_ref")
for p in r.each():
    b = p.bbox().to_dtype(ly.dbu)
    print(f"box {b.left:.3f}um {b.bottom:.3f}um {b.right:.3f}um {b.top:.3f}um; paint rnw")
PYEOF
python3 - "$META" "$REPO/layout/gen" > netlabels.tcl <<'PYEOF'
import json, re, sys
sys.path.insert(0, sys.argv[2])
import tile_nets as TN
pinned = {n for n, e in TN.nets().items() if any(i == 'PIN' for i, _ in e)}   # named by their TT pin already
pts = json.load(open(sys.argv[1]))['net_points']
LAY = {'m1': 'metal1', 'm2': 'metal2', 'm3': 'metal3', 'm4': 'metal4'}
k = 0
for net, lst in sorted(pts.items()):
    lst = [p for p in lst if not p[3].startswith('xmac.')]     # the macro is gone: label at an analog end
    if len(lst) == 0 or net in pinned or re.fullmatch(r'(VGND|VDPWR|VAPWR)', net):
        continue
    l, x, y, where = lst[0]
    print(f"box {x:.3f}um {y:.3f}um {x:.3f}um {y:.3f}um; label {{{net}}} c {LAY[l]}; port make  ;# {where}")
    k += 1
print(f"# {k} net ports")
PYEOF
[ "$(grep -c 'paint rnw' rnwfix.tcl)" -ge 1 ] || { echo "rnw repaint: no NWELL & RES_MK box found"; exit 1; }
case $MODE in
  lvs) EXT='ext2spice lvs
ext2spice cthresh infinite' ;;
  c)   EXT='ext2spice lvs
ext2spice cthresh 0' ;;
  rc)  EXT='ext2sim labels on
ext2sim
extresist tolerance 10
extresist
ext2spice lvs
ext2spice cthresh 0
ext2spice extresist on' ;;
esac
{
echo "gds read $OUT/${B}_nomac.gds"
cat rnwfix.tcl
echo "load $T"
echo "flatten -dotoplabels ${B}_flat"
echo "load ${B}_flat"
cat netlabels.tcl
echo "cellname delete $T"
echo "cellname rename ${B}_flat ${B}_$MODE"
echo "select top cell"
echo "extract do local"
echo "extract all"
echo "ext2spice short resistor"
echo "$EXT"
echo "ext2spice -o ${B}_raw.spice"
echo "quit -noprompt"
} > pex.tcl
t0=$(date +%s)
nice -n 10 "$MAGIC" -dnull -noconsole -rcfile $RC pex.tcl > magic.log 2>&1
echo "magic $("$MAGIC" --version) $MODE extraction: $(( $(date +%s) - t0 )) s; rnw boxes $(grep -c paint rnwfix.tcl); $(tail -1 netlabels.tcl)"
grep -q "Error parsing" magic.log && { echo "ERROR: magic: $(grep -m1 "Error parsing" magic.log)"; exit 1; }
[ -s ${B}_raw.spice ] || { echo "ERROR: no ${B}_raw.spice"; tail -20 magic.log; exit 1; }
DST=$REPO/layout/pex/${B}_$MODE.spice
{ echo "* tile without tx_fine, extracted $(date -Iseconds) with magic $("$MAGIC" --version), mode $MODE, from $(basename $GDS)"
  echo "* by layout/gen/pex_tile.sh; the substrate node is VGND"
  cat ${B}_raw.spice; } > "$DST"
if [ "$MODE" = rc ]; then
  python3 "$REPO/layout/gen/rcfix.py" "$DST" "$REPO/layout/pex/${B}_rcx.spice" --vss VGND \
    $( [ -f "$REPO/layout/pex/${B}_c.spice" ] && echo --check "$REPO/layout/pex/${B}_c.spice" )
  DST=$REPO/layout/pex/${B}_rcx.spice
fi
# 3. checks: every labelled net is a port; device counts; the nwell resistor survived
python3 - "$DST" netlabels.tcl <<'PYEOF'
import re, sys
txt = re.sub(r'\n\+', ' ', open(sys.argv[1]).read())
m = re.search(r'^\.subckt (\S+) (.*)$', txt, re.M)
ports = set(m.group(2).split())
want = set(re.findall(r'label \{(\S+)\} c', open(sys.argv[2]).read()))
miss = sorted(want - ports)
dev = {k: len(re.findall(rf'^{k}', txt, re.M)) for k in 'XMCRD'}
print(f'subckt {m.group(1)}: {len(ports)} ports; devices {dev}')
print('labelled nets that are not ports:', miss if miss else 'none')
assert ' nwell ' in txt or 'nwell' in txt, 'no nwell resistor'
PYEOF
