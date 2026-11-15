#!/bin/bash
# Driver for docs/handoff_rx_layout.md: blocks -> checks -> extraction -> benches -> summary, one command.
#   bash layout/gen/rx_layout_driver.sh            (repo root; start it with the Bash tool's run_in_background)
# Each step writes build/rx_layout/status.txt, checks its own outputs before the next starts, and pushes the
# handoff's first line ("> Running: step N/M since HH:MM, ETA HH:MM"). The end writes build/rx_layout/DONE or FAILED.
# CPU: the benches run 3 at a time, the chain (one ngspice, many hours) alongside them: at most 4 processes, nice 19.
set -u
# ---- config (the handoff's corner policy: 27 C, 3.3 V, tt + the bounding corners ss / ff) ----
CORNERS=typical,ss,ff
JOBS=3
CHAIN_LEVEL=-70
CELLS="rx_bias rx_lna rx_mix rx_lobuf rx_lsq rx_bb rx_lim"
# ----
REPO=$(pwd)
B=$REPO/build/rx_layout
mkdir -p $B
command rm -f $B/DONE $B/FAILED
N=6
T0=$(date +%s)
step() {   # step <n> <text> <eta minutes>
  echo "step $1/$N $2 since $(date +%H:%M) (ETA $(date -d "+$3 min" +%H:%M))" > $B/status.txt
  echo "== $(date +%T) step $1/$N: $2" | tee -a $B/driver.log
  sed -i "1s|.*|> Running: step $1/$N ($2) since $(date +%H:%M), ETA $(date -d "+$3 min" +%H:%M)|" docs/handoff_rx_layout.md
  ( git add docs/handoff_rx_layout.md && git commit -q -m "handoff rx_layout: step $1/$N ($2)" \
    && git pull -q --rebase && git push -q origin rx-option-b ) >> $B/driver.log 2>&1 || echo "status push failed" >> $B/driver.log
}
fail() {
  echo "FAILED at $(cat $B/status.txt): $*" | tee $B/FAILED | tee -a $B/driver.log
  tail -20 "${LOGF:-$B/driver.log}" >> $B/FAILED 2>/dev/null
  exit 1
}

step 1 "generate the 8 cells" 5
for c in $CELLS rx_top; do
  LOGF=$B/gen_$c.log
  nice -n 19 python3 layout/gen/$c.py > $LOGF 2>&1 || fail "generator $c"
  [ -s layout/$c.gds ] || fail "no layout/$c.gds"
done

step 2 "DRC / antenna / LVS / sizes / mutations, 8 cells" 10
# the antenna proof copy: rx_bias with a 60 x 30 um Metal2 plate on its en pin (outside the cell, clear of the rails)
mkdir -p $B/antenna_proof
python3 - <<'EOF' >> $B/driver.log 2>&1 || fail "antenna proof copy"
import json, klayout.db as db
m = json.load(open('build/rx_layout/gen/rx_bias/meta.json'))
x, y, e = [p for p in m['bands'][0]['pins']['en'] if p[2] == 'right'][0]
ly = db.Layout(); ly.read('layout/rx_bias.gds')
top = ly.cell('rx_bias'); li = ly.layer(36, 0)
d = lambda v: int(round(v / 1000 / ly.dbu))
top.shapes(li).insert(db.Box(d(x - 100), d(y - 190), d(x + 1000), d(y + 190)))
top.shapes(li).insert(db.Box(d(x + 1000), d(y - 15000), d(x + 61000), d(y + 15000)))
ly.write('build/rx_layout/antenna_proof/rx_bias_ant.gds')
EOF
for c in $CELLS rx_top; do
  LOGF=$B/check_$c.log
  if [ $c = rx_bias ]; then
    ANT_GDS=$B/antenna_proof/rx_bias_ant.gds bash layout/gen/check_rx_block.sh $c > $LOGF 2>&1
    grep -q "antenna proof run.*violations [1-9]" $B/check/$c/summary.txt || fail "antenna proof did not catch the plate"
  else
    bash layout/gen/check_rx_block.sh $c > $LOGF 2>&1
  fi
  tail -1 $B/check/$c/summary.txt | grep -q "^CHECK OK" || fail "check $c: $(tail -1 $B/check/$c/summary.txt)"
done

step 3 "extraction (C and R+C), 8 cells" 5
for c in $CELLS rx_top; do
  for m in c rc; do
    LOGF=$B/pex_${c}_$m.log
    bash layout/gen/pex_rx_block.sh $c $m > $LOGF 2>&1 || fail "extraction $c $m"
  done
  [ -s layout/pex/${c}_c.spice ] && [ -s layout/pex/${c}_rcx.spice ] || fail "no extraction for $c"
done

step 4 "LNA / baseband / hysteresis benches on the extraction" 5
for m in lna bb lim; do
  LOGF=$B/bench_$m.log
  cs=$CORNERS; [ $m = lim ] && cs=typical
  nice -n 19 python3 layout/gen/rx_pexbench.py $m --corners $cs --jobs $JOBS > $LOGF 2>&1 || fail "bench $m"
done
python3 - <<'EOF' >> $B/driver.log 2>&1 || fail "bench outputs"
import json
for m in ('lna', 'bb', 'lim'):
    rows = json.load(open(f'build/rx_layout/bench/{m}.json'))['rows']
    for r in rows:
        bad = set(r.get('bad') or [])
        if m == 'bb':
            bad -= {'error:', 'no such'}       # the bench's print of @m.xbb.xmvbsnk.m0[id]: no such device in the extraction
        assert not bad, (m, r.get('corner'), bad)
        key = dict(lna='nf', bb='fhi', lim='hyst_mv')[m]
        assert r.get(key) is not None, (m, r.get('corner'), 'no', key)
print('bench outputs ok')
EOF

step 5 "LO ring bench (I/Q phase, ring shift) on tt/ss/ff; the FSK chain started alongside" 40
LOGC=$B/bench_chain.log
( nice -n 19 python3 layout/gen/rx_pexbench.py chain --level $CHAIN_LEVEL --pex c > $LOGC 2>&1; echo $? > $B/chain.rc ) &
CHAIN_PID=$!
LOGF=$B/bench_lo.log
nice -n 19 python3 layout/gen/rx_pexbench.py lo --corners $CORNERS --jobs $JOBS > $LOGF 2>&1 || fail "bench lo"
python3 - <<'EOF' >> $B/driver.log 2>&1 || { kill $CHAIN_PID 2>/dev/null; fail "LO bench outputs / I/Q phase stop rule"; }
import json
rows = json.load(open('build/rx_layout/bench/lo.json'))['rows']
for r in rows:
    assert not r.get('bad') and 'error' not in r and r.get('f'), r
    if r['case'] == 'pex':
        ph = r['iq_phase']
        assert 72 - 25 <= ph <= 72 + 25, f"I/Q phase {ph:.1f} deg outside 72 +- 25 ({r['corner']}): rx_lsq is not a faithful copy"
print('LO outputs ok:', [(r['corner'], round(r['iq_phase'], 1), round(r.get('shift_pct', 0), 2)) for r in rows if r['case'] == 'pex'])
EOF

step 6 "FSK chain through the real ring LO, extracted rx_top, tt, -70 dBm" 600
LOGF=$LOGC
wait $CHAIN_PID
[ "$(cat $B/chain.rc 2>/dev/null)" = 0 ] || fail "chain bench exit $(cat $B/chain.rc 2>/dev/null)"
python3 - <<'EOF' >> $B/driver.log 2>&1 || fail "chain outputs"
import json
r = json.load(open('build/rx_layout/bench/chain.json'))['rows'][0]
assert 'error' not in r and not r.get('bad'), r
assert r.get('bit_errors') is not None, r
print('chain ok:', {k: r.get(k) for k in ('counts', 'model_counts', 'bit_errors', 'glitches', 'lo_iq_phase', 'idd_ma')})
EOF

echo "done $(date -Iseconds), $(( ($(date +%s) - T0) / 60 )) min" | tee $B/DONE >> $B/driver.log
echo "step $N/$N done" > $B/status.txt
