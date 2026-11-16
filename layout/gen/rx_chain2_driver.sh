#!/bin/bash
# Driver for docs/handoff_rx_chain2.md: the FSK chain through the real ring LO on the SECOND-PASS extracted rx_top.
#   bash layout/gen/rx_chain2_driver.sh        (repo root; start it with the Bash tool's run_in_background)
# Steps: 1 smoke test (ngspice + PDK models: the extracted comparator's hysteresis must be the known +-36.3 mV)
#        2 the chain (one ngspice, ~9 h at nice 19)  3 output checks.
# Each step writes build/rx_chain2/status.txt and pushes the handoff's first line ("> Running: step N/3 ...");
# the end writes build/rx_chain2/DONE or FAILED. Inputs are committed files only (layout/pex/rx_top_c.spice,
# the extracted lsdiv): no extraction here.
set -u
# ---- config ----
CHAIN_LEVEL=-70          # dBm, as the first pass and the schematic run
NICE=19
# ----
REPO=$(pwd)
B=$REPO/build/rx_chain2
mkdir -p $B
command rm -f $B/DONE $B/FAILED
H=docs/handoff_rx_chain2.md
N=3
step() {   # step <n> <text> <eta minutes>
  echo "step $1/$N $2 since $(date +%H:%M) (ETA $(date -d "+$3 min" +%H:%M))" > $B/status.txt
  echo "== $(date +%T) step $1/$N: $2" | tee -a $B/driver.log
  sed -i "1s|.*|> Running: step $1/$N ($2) since $(date +%H:%M), ETA $(date -d "+$3 min" +%H:%M)|" $H
  ( git add $H && git commit -q -m "handoff rx_chain2: step $1/$N ($2)" \
    && git pull -q --rebase --autostash && git push -q origin rx-option-b ) >> $B/driver.log 2>&1 \
    || echo "status push failed" >> $B/driver.log
}
fail() {
  echo "FAILED at $(cat $B/status.txt): $*" | tee $B/FAILED | tee -a $B/driver.log
  tail -20 "${LOGF:-$B/driver.log}" >> $B/FAILED 2>/dev/null
  exit 1
}

step 1 "smoke test: extracted rx_lim hysteresis" 2
for f in layout/pex/rx_top_c.spice layout/pex/rx_lim_rcx.spice; do [ -s $f ] || fail "missing $f"; done
LOGF=$B/smoke.log
nice -n $NICE python3 layout/gen/rx_pexbench.py lim --corners typical --jobs 1 > $LOGF 2>&1 || fail "lim bench"
python3 - <<'EOF' >> $B/driver.log 2>&1 || fail "smoke test: hysteresis not +-36.3 mV (ngspice / PDK models differ?)"
import json
r = json.load(open('build/rx_layout/bench/lim.json'))['rows'][0]
assert not r.get('bad'), r
assert abs(r['hyst_mv'] - 36.29) < 0.5, r['hyst_mv']
print('smoke ok: hysteresis', round(r['hyst_mv'], 2), 'mV')
EOF

step 2 "FSK chain, real ring LO, second-pass extracted rx_top, tt, $CHAIN_LEVEL dBm" 600
LOGF=$B/chain.log
nice -n $NICE python3 layout/gen/rx_pexbench.py chain --level $CHAIN_LEVEL --pex c > $LOGF 2>&1 || fail "chain bench exit $?"

step 3 "output checks" 1
python3 - <<'EOF' >> $B/driver.log 2>&1 || fail "chain outputs"
import json, shutil
d = json.load(open('build/rx_layout/bench/chain.json'))
r = d['rows'][0]
assert 'error' not in r and not r.get('bad'), r
assert r.get('bit_errors') is not None and r.get('counts'), r
shutil.copy('build/rx_layout/bench/chain.json', 'build/rx_chain2/chain.json')
ft = r.get('f_ring_track') or [0]
print('chain ok:', {k: r.get(k) for k in ('counts', 'model_counts', 'bit_errors', 'glitches', 'lo_iq_phase', 'idd_ma')},
      'ring drift', round(max(ft) - min(ft)), 'Hz', 'pre-run drift', round(r['pre']['drift_hz']), 'Hz',
      'wall', round(r['wall_s'] / 3600, 1), 'h')
EOF
echo "done $(date -Iseconds)" | tee $B/DONE >> $B/driver.log
echo "step $N/$N done" > $B/status.txt
