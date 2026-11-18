#!/bin/bash
# Parasitic extraction of one receiver layout cell (generalised from pex_tx.sh), with magic 8.3.642 (8.3.684 drops
# substrate C, CLAUDE.md). Run from the repo root.
#   bash layout/gen/pex_rx_block.sh <cell> [c|rc|lvs] [gds]
#   c : devices + C (cthresh 0, coupling C kept)                         -> layout/pex/<cell>_c.spice
#   rc: + R (extresist) -> <cell>_rc.spice, then layout/gen/rcfix.py     -> layout/pex/<cell>_rcx.spice
#       (magic's rc mode double-counts coupling C on ports and split nets: only ever simulate the _rcx file)
# The port order is the sim netlister's (sim/rx/rx_top.py block()), so the result drops into the benches in place
# of the schematic subckt. Hierarchical cells (rx_top) are flattened first.
set -eu
B=$1
MODE=${2:-c}
REPO=$(pwd)
GDS=$(realpath "${3:-layout/$B.gds}")
MAGIC=${MAGIC:-$( [ -x $HOME/.local/magic642/bin/magic ] && echo $HOME/.local/magic642/bin/magic || echo magic)}
OUT=$REPO/build/rx_layout/pex/${B}_$MODE
mkdir -p "$OUT" "$REPO/layout/pex"; cd "$OUT"
command rm -f *.ext *.res.ext *.sim *.nodes
export PDK_ROOT=${PDK_ROOT:-/foss/pdks} PDK=gf180mcuD
RC=$PDK_ROOT/$PDK/libs.tech/magic/$PDK.magicrc
# the sim subckt (its .subckt line gives pexfix.py the port order)
python3 -c "
import sys, re; sys.path.insert(0, '$REPO/sim/rx')
import rx_top
t = rx_top.block()
m = re.search(r'^\.subckt $B .*?^\.ends', t, re.S | re.M)
print(m.group(0))" > sim.spice
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
cat > pex.tcl <<EOF
gds read $GDS
load $B
flatten ${B}_flat
load ${B}_flat
cellname delete $B
cellname rename ${B}_flat $B
select top cell
extract do local
extract all
$EXT
ext2spice -o ${B}_raw.spice
quit -noprompt
EOF
t0=$(date +%s)
nice -n 19 "$MAGIC" -dnull -noconsole -rcfile $RC pex.tcl > magic.log 2>&1
echo "magic $("$MAGIC" --version) $MODE extraction of $B: $(( $(date +%s) - t0 )) s"
DST=$REPO/layout/pex/${B}_$MODE.spice
python3 "$REPO/layout/gen/pexfix.py" ${B}_raw.spice sim.spice "$DST"
sed -i "1a * extracted $(date -Iseconds) with magic $("$MAGIC" --version), mode $MODE, from $(basename $GDS)" "$DST"
# hierarchical cells: magic names a subcell's nets <inst>.<net>; rcfix.py reads <net>.t<i> / <net>.n<i> as the
# pieces of a split net, so b.n2 (rx_bias's n2) would become a piece of 'b'. Use <inst>_<net> instead.
if grep -q '^X.* rx_' ${B}_raw.spice 2>/dev/null || [ "$B" = rx_top ]; then
  sed -i -E 's/(^| )(b|lna|lo_lq|lo_bi|lo_bq|mi|mq|bbi|bbq|li|lq|dc)\./\1\2_/g' "$DST"
fi
if [ "$MODE" = rc ]; then
  python3 "$REPO/layout/gen/rcfix.py" "$DST" "$REPO/layout/pex/${B}_rcx.spice" \
    $( [ -f "$REPO/layout/pex/${B}_c.spice" ] && echo --check "$REPO/layout/pex/${B}_c.spice" )
fi
