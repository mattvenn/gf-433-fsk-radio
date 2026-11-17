#!/bin/bash
# The tile's check run (docs/handoff_tile_layout.md step 5, docs/tile_layout.md): one driver, each step checks its own
# output and stops the run on failure.
#   1 harden   tx_fine with LibreLane (only with HARDEN=1; else the committed macro/tx_fine GDS / LEF / netlists)
#   2 blocks   every re-laid-out block's own check (DRC, LVS against its schematic, antenna, mutations)
#   3 tile     layout/gen/tile.py (GDS + LEF), lvs/make_source.py (the LVS source)
#   4 drc      magic DRC (drc(full)) and KLayout DRC (feol=true beol=true; the rule
#              count must be > 0, or the deck ran nothing)
#   5 lvs      layout/gen/check_tt.sh: netgen LVS, resistor totals, 14 mutations that must all FAIL
#   6 antenna  KLayout's antenna deck on the tile (its rule count must be > 0; a planted violation must be caught)
#   7 precheck the structural TT rules, locally (layout/gen/tile_precheck.py); the real TT precheck runs in CI
#   8 summary
# Run from the repo root (in the image): bash layout/gen/tile_driver.sh     Results: build/tile/run/
#   status.txt (one line per step), DONE or FAILED (with the failing step's log tail), summary.txt.
set -u
REPO=$(pwd)
OUT=$REPO/build/tile/run
mkdir -p $OUT
command rm -f $OUT/DONE $OUT/FAILED
: > $OUT/status.txt
export PDK_ROOT=${PDK_ROOT:-/foss/pdks} PDK=gf180mcuD
T=tt_um_mattvenn_gf433_vco
NSTEP=8
step() { echo "$(date +%H:%M:%S) step $1/$NSTEP $2: $3" | tee -a $OUT/status.txt; }
fail() {  # fail <step> <log>
  step "$1" "$2" FAILED
  { echo "FAILED at step $1 ($2), $(date -Iseconds)"; echo "--- tail of $3"; tail -40 "$3"; } > $OUT/FAILED
  exit 1
}

# ---- 1. harden ----
if [ "${HARDEN:-0}" = 1 ]; then
  step 1 harden started
  ( cd macro/tx_fine && PDK=gf180mcuD STD_CELL_LIBRARY=gf180mcu_fd_sc_mcu7t5v0 PDKPATH=$PDK_ROOT/gf180mcuD \
      librelane config.json --pdk gf180mcuD --scl gf180mcu_fd_sc_mcu7t5v0 --run-tag drv --overwrite ) > $OUT/harden.log 2>&1
  M=macro/tx_fine/runs/drv/final/metrics.json
  python3 - $M > $OUT/harden.txt <<'PY' || fail 1 harden $OUT/harden.log
import json, sys
m = json.load(open(sys.argv[1]))
k = ['magic__drc_error__count', 'klayout__drc_error__count', 'design__lvs_error__count', 'route__antenna_violation__count']
bad = [x for x in k if m.get(x) != 0] + (['setup tt'] if m['timing__setup__ws__corner:nom_tt_025C_3v30'] < 0 else [])
print({x: m.get(x) for x in k}, 'setup tt', m['timing__setup__ws__corner:nom_tt_025C_3v30'])
sys.exit(1 if bad else 0)
PY
  for f in gds/tx_fine.gds lef/tx_fine.lef nl/tx_fine.nl.v pnl/tx_fine.pnl.v; do
    command cp -f macro/tx_fine/runs/drv/final/$f macro/tx_fine/$(dirname $f | sed 's/pnl/nl/')/
  done
  step 1 harden "done: $(cat $OUT/harden.txt)"
else
  step 1 harden "skipped (HARDEN=1 to run): the committed macro"
fi

# ---- 2. block checks ----
step 2 blocks started
B=$OUT/blocks; mkdir -p $B
: > $B/results.txt
blk() {  # blk <name> <command...>
  local n=$1; shift
  "$@" > $B/$n.log 2>&1
  local r; r=$(grep -h "^CHECK" $B/$n/summary.txt 2>/dev/null | tail -1)
  [ -z "$r" ] && r=$(tail -1 $B/$n.log)
  echo "$n: $r" | tee -a $B/results.txt
}
for c in rx_bias rx_lna rx_lsq rx_lobuf rx_mix rx_bb rx_lim; do
  blk $c bash layout/gen/check_rx_block.sh $c layout/$c.gds $B/$c
done
blk dbg_tg bash layout/gen/check_dbg.sh layout/dbg_tg.gds $B/dbg_tg
blk tx_drv bash layout/gen/check_tx.sh layout/tx_drv.gds $B/tx_drv
blk vco_core bash layout/gen/check_core.sh layout/vco_core.gds $B/vco_core
blk cgm_ref bash layout/gen/check_ref.sh layout/cgm_ref.gds $B/cgm_ref
blk mdac bash -c "bash layout/gen/check_mdac.sh $B/mdac && cp $B/mdac/summary.txt $B/mdac/summary.full && \
  { grep -q '^LVS PASS' $B/mdac/summary.full && grep -q 'magic DRC.*count 0' $B/mdac/summary.full && \
    grep -q 'rules run [1-9][0-9]*: count 0' $B/mdac/summary.full && grep -q 'violations 0' $B/mdac/summary.full && \
    ! grep -q 'NOT caught\|PASS (BAD' $B/mdac/summary.full && echo 'CHECK OK (mdac)' || echo 'CHECK FAIL (mdac)'; } >> $B/mdac/summary.txt"
blk decap_ls bash -c "bash layout/gen/check_decap.sh $B/decap_ls && \
  { grep -q '^LVS PASS' $B/decap_ls/summary.txt && grep -q 'magic DRC.*count 0' $B/decap_ls/summary.txt && \
    grep -q 'rules run [1-9][0-9]*: count 0' $B/decap_ls/summary.txt && grep -q 'violations 0' $B/decap_ls/summary.txt && \
    echo 'CHECK OK (decap_ls)' || echo 'CHECK FAIL (decap_ls)'; } >> $B/decap_ls/summary.txt"
nok=$(grep -c "CHECK OK" $B/results.txt); nall=$(wc -l < $B/results.txt)
[ "$nok" = "$nall" ] || fail 2 blocks $B/results.txt
step 2 blocks "done: $nok / $nall CHECK OK"

# ---- 3. tile ----
step 3 tile started
python3 layout/gen/tile.py > $OUT/tile.log 2>&1 || fail 3 tile $OUT/tile.log
grep -q "UNROUTED" $OUT/tile.log && fail 3 tile $OUT/tile.log
[ -s gds/$T.gds ] && [ -s lef/$T.lef ] || fail 3 tile $OUT/tile.log
python3 lvs/make_source.py > $OUT/source.log 2>&1 || fail 3 tile $OUT/source.log
step 3 tile "done: $(grep '^round' $OUT/tile.log | tail -1); $(tail -1 $OUT/source.log)"

# ---- 4. DRC ----
step 4 drc started
D=$OUT/drc; mkdir -p $D
{
  echo "gds read $REPO/gds/$T.gds"
  echo "load $T"
  echo "select top cell"
  echo "drc euclidean on"
  echo "drc style drc(full)"
  echo "drc check"
  echo "drc catchup"
  echo "set fp [open $D/magic_drc.txt w]"
  echo 'puts $fp "count [drc list count total]"'
  echo 'foreach {why boxes} [drc listall why] { puts $fp "[llength $boxes]  $why" }'
  echo 'close $fp'
  echo "quit -noprompt"
} > $D/magic_drc.tcl
nice -n 19 magic -dnull -noconsole -rcfile $PDK_ROOT/$PDK/libs.tech/magic/$PDK.magicrc $D/magic_drc.tcl > $D/magic.log 2>&1
( cd $D && nice -n 19 klayout -b -r $PDK_ROOT/$PDK/libs.tech/klayout/tech/drc/gf180mcu.drc -rd input=$REPO/gds/$T.gds \
    -rd topcell=$T -rd report=$D/klayout_drc.lyrdb -rd variant=D -rd run_mode=deep -rd threads=8 \
    -rd decks=all,-density -rd feol=true -rd beol=true > klayout_drc.log 2>&1 )
nrule=$(grep -c "Executing rule" $D/klayout_drc.log)
nkl=$(python3 -c "import xml.etree.ElementTree as E; print(len(E.parse('$D/klayout_drc.lyrdb').getroot().find('items')))")
echo "magic $(head -1 $D/magic_drc.txt); KLayout: $nkl errors, $nrule rules run" > $D/result.txt
[ "$nrule" -gt 0 ] && [ "$nkl" = 0 ] || fail 4 drc $D/klayout_drc.log
grep -q "^count 0$" $D/magic_drc.txt || fail 4 drc $D/magic_drc.txt
step 4 drc "done: $(cat $D/result.txt)"

# ---- 5. LVS ----
step 5 lvs started
bash layout/gen/check_tt.sh gds/$T.gds lvs/$T.spice $OUT/lvs > $OUT/lvs.log 2>&1
grep -q "^CHECK OK" $OUT/lvs/summary.txt || fail 5 lvs $OUT/lvs/summary.txt
step 5 lvs "done: $(tail -1 $OUT/lvs/summary.txt)"

# ---- 6. antenna ----
step 6 antenna started
A=$OUT/antenna; mkdir -p $A
( cd $A && nice -n 19 klayout -b -r $PDK_ROOT/$PDK/libs.tech/klayout/tech/drc/gf180mcu.drc -rd input=$REPO/gds/$T.gds \
    -rd topcell=$T -rd report=$A/antenna.lyrdb -rd variant=D -rd run_mode=deep -rd threads=8 -rd decks=antenna \
    -rd feol=true -rd beol=true > klayout_antenna.log 2>&1 )
nantr=$(grep -c "Executing rule" $A/klayout_antenna.log)
nant=$(python3 -c "import xml.etree.ElementTree as E; print(len(E.parse('$A/antenna.lyrdb').getroot().find('items')))" 2>/dev/null)
[ "$nantr" -gt 0 ] && [ "$nant" = 0 ] || fail 6 antenna $A/klayout_antenna.log
# mutation: the tile plus a planted violation (a 300 x 300 um Metal1 plate on a 0.5 x 0.6 um gate, off to the side)
# must give ANT violations. (Removing the three antenna-diode rows is no mutation: the tile still passes without
# them, 2026-11-17, since the protected nets stay off Metal4, tile_nets.NO_M4_NETS.)
python3 - $REPO/gds/$T.gds $A/mut.gds <<'PYEOF'
import sys, klayout.db as db
ly = db.Layout(); ly.read(sys.argv[1]); top = ly.top_cell()
def B(l, x0, y0, x1, y1):
    top.shapes(ly.layer(l, 0)).insert(db.Box(*(round(v * 1000) - 2000000 for v in (x0, y0, x1, y1))))
B(22, 0, 0, 2, 0.6); B(32, -0.5, -0.5, 2.5, 1.1); B(30, 0.8, -0.5, 1.3, 3)   # COMP, NPLUS, POLY2: the gate
B(33, 0.9, 2.3, 1.12, 2.52); B(34, 0.7, 2.1, 300, 300)                       # contact, the Metal1 plate
ly.write(sys.argv[2])
PYEOF
( cd $A && nice -n 19 klayout -b -r $PDK_ROOT/$PDK/libs.tech/klayout/tech/drc/gf180mcu.drc -rd input=$A/mut.gds \
    -rd topcell=$T -rd report=$A/mut.lyrdb -rd variant=D -rd run_mode=deep -rd threads=8 -rd decks=antenna \
    -rd feol=true -rd beol=true > klayout_antenna_mut.log 2>&1 )
nmut=$(python3 -c "import xml.etree.ElementTree as E; print(len(E.parse('$A/mut.lyrdb').getroot().find('items')))" 2>/dev/null)
[ "${nmut:-0}" -gt 0 ] || fail 6 antenna "planted antenna violation not caught: $A/klayout_antenna_mut.log"
step 6 antenna "done: KLayout antenna deck ($nantr rules) $nant violations; planted violation caught ($nmut)"

# ---- 7. precheck (local) ----
# The structural Tiny Tapeout rules re-implemented here (layout/gen/tile_precheck.py: pins at the template's places,
# power stripes, no Metal5, boundary, info.yaml / project.v). The real TT precheck (tt-support-tools) runs in CI
# (.github/workflows/gds.yaml) or by hand before submitting.
step 7 precheck started
python3 layout/gen/tile_precheck.py > $OUT/precheck.log 2>&1 || fail 7 precheck $OUT/precheck.log
step 7 precheck "done: $(tail -1 $OUT/precheck.log)"

# ---- 8. summary ----
{
  echo "tile check run $(date -Iseconds)"
  cat $OUT/status.txt
  echo; echo "== blocks"; cat $B/results.txt
  echo; echo "== LVS"; cat $OUT/lvs/summary.txt
} > $OUT/summary.txt
step 8 summary done
date -Iseconds > $OUT/DONE
