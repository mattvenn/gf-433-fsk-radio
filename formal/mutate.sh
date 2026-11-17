#!/bin/bash
# Mutation tests of the formal properties (formal/tx_fine.sby): each mutant is one planted bug in a copy of
# src/tx_fine.v; the named task must FAIL on it (a counterexample).
#   bash formal/mutate.sh [name ...]       all mutants, or the ones named (each up to TMO s, default 1200)
# Work dirs in build/fvmut/<name>/. docs/verification_digital.md, "Formal".
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
B=$ROOT/build/fvmut
TMO=${TMO:-1200}
mkdir -p "$B"
fail=0
mut() {   # name task old new  (\n in old / new: a newline)
    local name=$1 task=$2 old=$3 new=$4
    [ ${#SEL[@]} -gt 0 ] && [[ " ${SEL[*]} " != *" $name "* ]] && return
    local d=$B/$name; rm -rf "$d"; mkdir -p "$d"
    python3 - "$ROOT/src/tx_fine.v" "$d/tx_fine.v" "$old" "$new" <<'PY' || { echo "$name: EDIT DID NOT APPLY"; fail=1; return; }
import sys
src, dst, old, new = sys.argv[1], sys.argv[2], sys.argv[3].replace('\\n', '\n'), sys.argv[4].replace('\\n', '\n')
t = open(src).read()
if t.count(old) != 1:
    sys.exit(f'{old!r} matches {t.count(old)} times')
open(dst, 'w').write(t.replace(old, new))
PY
    cp "$ROOT"/formal/{fv_tx_fine.sv,cg_nogate.v} "$d/"
    sed 's|^\.\./src/tx_fine.v|tx_fine.v|' "$ROOT/formal/tx_fine.sby" > "$d/tx_fine.sby"
    local t0=$(date +%s)
    (cd "$d" && timeout "$TMO" sby -f tx_fine.sby "$task" > sby.log 2>&1)
    local r=$(grep -o "DONE ([A-Z]*" "$d/sby.log" | tail -1 | cut -c7-)
    local a=$(grep -o "failed assertion.* at fv_tx_fine.sv:[0-9]*" "$d/sby.log" | head -1 | sed 's/.*fv_tx_fine.sv:/line /')
    local st=$(grep -o "at fv_tx_fine.sv:[0-9.-]* step [0-9]*" "$d/sby.log" | head -1 | sed 's/.* step /step /')
    if [ "$r" = FAIL ]; then echo "$name ($task): caught, assert $a, $st, $(( $(date +%s) - t0 )) s"
    else echo "$name ($task): NOT CAUGHT (${r:-timeout}), $(( $(date +%s) - t0 )) s"; fail=1; fi
}
SEL=("$@")
mut rst_dbg   prove "dbg <= 4'd0;" "dbg <= 4'd1;"
mut addr4     prove "3'd5: dbg      <=" "3'd4: dbg      <="
mut thermo    prove "dac_tn[i] <= ~(eff_q[17:13] > i);" "dac_tn[i] <= ~(eff_q[17:13] > (i ^ 1));"
mut no_sat    prove "(sum[18] ? 18'h00000 : sum[17:0])" "sum[17:0]"
mut sd_hold   prove "            acc <= 0;\n            dac_sdn <= 1'b1;\n        end\n" "            dac_sdn <= 1'b1;\n        end\n"
mut ck_glitch prove "assign ck_o = ck & g_en;" "assign ck_o = ck & ck_en;"
mut dec_gate  gates ".en(eff_q[17:8] != eff_int)" ".en(eff_q[17:9] != eff_int[9:1])"
mut spi_gate  gates "wire en_spi = sel | ~s_cs[2];" "wire en_spi = sel;"
exit $fail
