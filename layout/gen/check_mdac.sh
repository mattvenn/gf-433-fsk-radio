#!/bin/bash
# mdac checks for the tile re-layout (vg / vbnf on the bottom edge): check_v2.sh (magic DRC, KLayout DRC feol+beol,
# antenna, netgen LVS) against the generator's LVS source (mdac.py lvs_source(), every finger incl. dummies), plus
# mutations that must FAIL. Usage (repo root): bash layout/gen/check_mdac.sh [outdir]
set -u
OUT=${1:-build/vco_tile/check_mdac}
mkdir -p $OUT
python3 -c "import sys; sys.path.insert(0, 'layout/gen'); import mdac; mdac.lvs_source(sys.argv[1])" $OUT/mdac_src.spice
SRC=$(realpath $OUT/mdac_src.spice)
bash layout/gen/check_v2.sh layout/mdac.gds mdac "$SRC" $OUT
cd $OUT
SETUP=/foss/pdks/gf180mcuD/libs.tech/netgen/gf180mcuD_setup.tcl
log() { echo "$*" | tee -a summary.txt; }
lvs() { netgen -batch lvs "mdac_lay.spice mdac" "$2 mdac" $SETUP $1.report > $1.log 2>&1
  grep -q "Final result: Circuits match uniquely" $1.report && ! grep -qi "property errors" $1.report && ! grep -qi "do not match" $1.report; }
mut_ok=1
mutate() {
  sed -e "$2" "$SRC" > $1.spice
  if cmp -s "$SRC" $1.spice; then log "== mutation $3: NOT APPLIED (BAD)"; mut_ok=0; return; fi
  if lvs $1 $1.spice; then log "== mutation $3: PASS (BAD: not caught)"; mut_ok=0
  else log "== mutation $3: FAIL (expected)  [$(grep -E 'Final result|roperty errors|do not match|pin matching' $1.report | sort -u | tr '\n' ' ')]"; fi
}
# vg <-> vbnf swapped on every device (the ports keep their names): as if the bottom-edge labels were swapped
mutate mut_pins '2,$ {s/ vg / @@ /g; s/ vbnf / vg /g; s/ @@ / vbnf /g}' "nets vg <-> vbnf swapped (pin labels)"
mutate mut_net  '0,/ vg mo VSS VSS nfet_03v3/s/ vg mo VSS VSS nfet_03v3/ vbnf mo VSS VSS nfet_03v3/' "one MO drain vg -> vbnf"
mutate mut_w    '0,/ pb vbnf VSS VSS nfet_03v3 w=1.200u/s/ pb vbnf VSS VSS nfet_03v3 w=1.200u/ pb vbnf VSS VSS nfet_03v3 w=1.000u/' "MB W 1.2 -> 1.0"
log "mutations caught: $mut_ok"
