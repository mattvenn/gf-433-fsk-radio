#!/bin/bash
# One EXISTING check of the tile (docs/verification.md, Table I), run for the full verification run. Writes the
# check's log to build/verify/existing/<check>.log and, as its last line, "RESULT <check> PASS|FAIL <detail>", judged
# from the tool's own output (not only its exit code). sim/verify/verdict.py reads these lines.
#   bash sim/verify/existing.sh <check>        (from the repo root, in the IIC-OSIC-TOOLS image)
# checks: pinout mutations cocotb_macro cocotb_macro_gl cocotb_tt cocotb_tt_gl formal_prove formal_gates_bmc
#         formal_mutate eqy floorplan xschem layout
set -u
REPO=$(pwd)
B=$REPO/build/verify/existing
mkdir -p "$B"
c=$1
L=$B/$c.log
res() { echo "RESULT $c $1 $2" | tee -a "$L"; }
xml() {  # cocotb results file -> PASS if tests > 0 and no failure / error
  python3 - "$1" <<'PY'
import sys, xml.etree.ElementTree as E
try:
    r = E.parse(sys.argv[1]).getroot()
except Exception as e:
    print('FAIL no results file'); sys.exit()
tc = r.findall('.//testcase')
bad = [t.get('name') for t in tc if t.find('failure') is not None or t.find('error') is not None]
print(('PASS' if tc and not bad else 'FAIL') + f' {len(tc) - len(bad)} / {len(tc)} pass' + (f'; failing {bad}' if bad else ''))
PY
}
case $c in
  pinout)
    python3 tools/check_pinout.py > "$L" 2>&1
    if grep -q "^pinout: OK" "$L"; then res PASS "$(grep '^pinout: OK' "$L")"; else res FAIL "$(grep -m1 ERROR "$L")"; fi ;;
  mutations)
    bash test/mutations.sh > "$L" 2>&1
    n=$(grep -c ": caught" "$L"); m=$(grep -ci "NOT CAUGHT\|DID NOT APPLY" "$L")
    [ "$m" = 0 ] && [ "$n" -gt 0 ] && res PASS "mutants caught $n / $((n + m))" || res FAIL "mutants caught $n / $((n + m))" ;;
  cocotb_macro|cocotb_tt|cocotb_macro_gl|cocotb_tt_gl)
    tb=${c#cocotb_}; tb=${tb%_gl}; gl=""; suf=""
    [[ $c == *_gl ]] && gl="GL=1" && suf=_gl
    rm -f test/results_${tb}${suf}.xml
    (cd test && make TB=$tb $gl) > "$L" 2>&1
    r=$(xml test/results_${tb}${suf}.xml); res ${r%% *} "${r#* }" ;;
  formal_prove|formal_gates_bmc)
    t=${c#formal_}; d=$REPO/build/verify/formal_$t; rm -rf "$d"; mkdir -p "$d"
    cp formal/tx_fine.sby formal/fv_tx_fine.sv formal/cg_nogate.v "$d/"
    sed -i "s|^\.\./src/|$REPO/src/|" "$d/tx_fine.sby"
    (cd "$d" && timeout 3600 sby -f tx_fine.sby $t) > "$L" 2>&1
    r=$(grep -o "DONE ([A-Z]*" "$L" | tail -1 | cut -c7-)
    [ "$r" = PASS ] && res PASS "sby $t: PASS" || res FAIL "sby $t: ${r:-no result}" ;;
  formal_mutate)
    TMO=1200 bash formal/mutate.sh > "$L" 2>&1
    n=$(grep -c ": caught" "$L"); m=$(grep -ci "NOT CAUGHT\|DID NOT APPLY" "$L")
    [ "$m" = 0 ] && [ "$n" -gt 0 ] && res PASS "mutants caught $n / $((n + m))" || res FAIL "mutants caught $n / $((n + m))" ;;
  eqy)
    bash formal/eqy/run.sh > "$L" 2>&1
    n=$(grep -c "^  caught" "$L"); m=$(grep -c "SELF-TEST FAIL" "$L")
    if grep -q "^eqy: ALL PASS" "$L"; then res PASS "equivalent; planted bugs caught $n / $((n + m))"
    else res FAIL "$(grep -m1 '^eqy:' "$L"); planted bugs caught $n / $((n + m))"; fi ;;
  floorplan)
    node layout/floorplan/page/check.js layout/floorplan/floorplan.json > "$L" 2>&1
    f=$(grep -c "^FAIL" "$L"); w=$(grep -c "^WARN" "$L")
    [ "$f" = 0 ] && res PASS "no rule fails, $w warnings" || res FAIL "$f rules fail" ;;
  xschem)
    python3 xschem/gen/check.py > "$L" 2>&1
    f=$(grep -c ": FAIL  \|: FAIL (\| FAIL \[" "$L"); bad=$(grep -c "BAD: not caught" "$L")
    [ "$f" = 0 ] && [ "$bad" = 0 ] && res PASS "every sheet matches; mutations caught" || res FAIL "$f FAIL lines, $bad mutations not caught" ;;
  layout)
    bash layout/gen/tile_driver.sh > "$L" 2>&1
    # tile_driver.sh step 3 regenerates gds/ lef/ lvs/ (the GDS differs at least in its timestamp): record, then
    # restore the committed files so the run leaves the tree clean (the checks above ran on the regenerated copy)
    ch=$(git status --short gds lef lvs | tr '\n' ' ')
    echo "regenerated, differing from the commit: ${ch:-none}" >> "$L"
    git checkout -q -- gds lef lvs 2>/dev/null
    if [ -f build/tile/run/DONE ] && [ ! -f build/tile/run/FAILED ]; then res PASS "$(tr '\n' ' ' < build/tile/run/status.txt | tail -c 400)"
    else res FAIL "$(head -3 build/tile/run/FAILED 2>/dev/null | tr '\n' ' ')"; fi ;;
  *) echo "unknown check $c"; exit 2 ;;
esac
exit 0
