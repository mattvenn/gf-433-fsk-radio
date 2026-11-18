#!/bin/bash
# dbg_tg (the debug switch) checks: layout/gen/check_rx_block.sh run as is (xschem/dbg_tg.sch as the LVS source;
# magic DRC, KLayout DRC feol + beol with the rule count, antenna, netgen LVS, two mutations that must FAIL), except
# the device-size diff: rx_sizes.py's reference is the receiver (sim/rx/rx_top.py), so here its functions are run
# against sim/rx/dbg_tg.py block() instead (a copy of the check script with that one line swapped).
# Usage: bash layout/gen/check_dbg.sh [gds] [outdir]     defaults: layout/dbg_tg.gds build/tx_tile/check/dbg_tg
# Results: <outdir>/summary.txt (last line CHECK OK / CHECK FAIL)
set -u
REPO=$(pwd)
GDS=${1:-layout/dbg_tg.gds}
OUT=${2:-build/tx_tile/check/dbg_tg}
mkdir -p "$OUT"; OUT=$(realpath "$OUT")
cat > "$OUT/sizes_dbg.py" <<PYEOF
import sys
from pathlib import Path
sys.path[:0] = ['$REPO/layout/gen', '$REPO/sim/rx']
import rx_sizes as S, dbg_tg as D
ref = S.flat(S.parse(D.block()), 'dbg_tg')
lay, un = S.name_auto(S.flat(S.parse(Path(sys.argv[1]).read_text()), 'dbg_tg'), ref)
if un:
    print('layout nets without a sim name:', ' '.join(un))
r, l = S.groups(ref), S.groups(lay)
ks = sorted(set(r) | set(l), key=str)
bad = [k for k in ks if k not in r or k not in l or abs(l[k] - r[k]) > 0.005 * r[k]]
for k in ks:
    print('BAD' if k in bad else 'ok ', k, 'sim', r.get(k), 'layout', l.get(k))
print(f'SIZES OK ({len(ks)} groups)' if not bad else f'SIZES FAIL ({len(bad)} of {len(ks)} groups differ)')
PYEOF
sed -e "s#python3 \$REPO/layout/gen/rx_sizes.py \${B}_lay.spice \$B#python3 $OUT/sizes_dbg.py \${B}_lay.spice#" \
  layout/gen/check_rx_block.sh > "$OUT/check_dbg_run.sh"
grep -q "sizes_dbg.py" "$OUT/check_dbg_run.sh" || { echo "sizes step not replaced"; exit 1; }
bash "$OUT/check_dbg_run.sh" dbg_tg "$GDS" "$OUT"
