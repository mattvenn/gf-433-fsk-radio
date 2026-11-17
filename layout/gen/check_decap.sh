#!/bin/bash
# decap_ls (stand-alone VDD_LS decap for the tile) checks: check_v2.sh + mutations that must FAIL. Repo root.
set -u
OUT=${1:-build/vco_tile/check_decap}; mkdir -p $OUT
python3 -c "import sys; sys.path.insert(0, 'layout/gen'); import vco_core; print(vco_core.decap_ls_source())" > $OUT/decap_ls_src.spice
SRC=$(realpath $OUT/decap_ls_src.spice)
bash layout/gen/check_v2.sh layout/decap_ls.gds decap_ls "$SRC" $OUT
cd $OUT
SETUP=/foss/pdks/gf180mcuD/libs.tech/netgen/gf180mcuD_setup.tcl
log() { echo "$*" | tee -a summary.txt; }
mut() { sed -e "$2" "$SRC" > $1.spice; cmp -s "$SRC" $1.spice && { log "== mutation $3: NOT APPLIED (BAD)"; return; }
  netgen -batch lvs "decap_ls_lay.spice decap_ls" "$1.spice decap_ls" $SETUP $1.report > $1.log 2>&1
  if grep -q "Final result: Circuits match uniquely" $1.report && ! grep -qi "property errors" $1.report && ! grep -qi "do not match" $1.report
  then log "== mutation $3: PASS (BAD: not caught)"; else log "== mutation $3: FAIL (expected)  [$(grep -E 'Final result|roperty errors|do not match|pin matching' $1.report | sort -u | tr '\n' ' ')]"; fi; }
mut mut_m   '/^XDC /s/m=3$/m=2/' "XDC m 3 -> 2"
mut mut_g   '/^XDC /s/^XDC VSS VDD_LS /XDC VSS VSS /' "XDC gate VDD_LS -> VSS"
