#!/bin/bash
# Driver for docs/handoff_mdac_fineword.md: re-run the medium-DAC Monte Carlo of Table III (docs/tx_fine_tune.md)
# keeping every sample's per-word currents, then measure how often the fine word (word + ΣΔ fraction) falls at a word
# boundary (sim/tune/mdac_fineword.py). Run from the repo root with the Bash tool's run_in_background:
#     bash sim/tune/run_mdac_fineword.sh
# Config (edit here, not below): corners, samples per corner, parallel jobs.
CORNERS="typical ss ff"
N=200
JOBS=${JOBS:-26}

cd "$(dirname "$0")/../.." || exit 1
B=build/tx_fine/mdac; mkdir -p $B; rm -f $B/DONE $B/FAILED; ST=$B/fineword_status.txt
log() { echo "$(date +%H:%M) $*" | tee -a $ST; }
fail() { log "FAILED: $*"; { echo "$*"; tail -20 "${2:-/dev/null}" 2>/dev/null; } > $B/FAILED; exit 1; }
: > $ST
log "start: corners $CORNERS, N $N, jobs $JOBS"

log "step 1: analysis self-test"
python3 sim/tune/mdac_fineword.py --selftest > $B/fineword_selftest.log 2>&1 || fail "self-test" $B/fineword_selftest.log

step=2
for c in $CORNERS; do
  log "step $step: Monte Carlo $c (N $N)"
  python3 sim/tune/mdac_sim.py mc --corner $c --n $N --jobs $JOBS > $B/mc_$c.out 2>&1
  tail -3 $B/mc_$c.out >> $ST
  nlog=$(grep -l '^SD1 ' $B/mc_$c/s*.log 2>/dev/null | wc -l)
  [ "$nlog" -eq "$N" ] || fail "mc $c: $nlog of $N complete logs" $B/mc_$c.out
  grep -q -i 'singular\|transient op started' $B/mc_$c/s*.log && fail "mc $c: singular or transient op in a log" $B/mc_$c.out
  step=$((step + 1))
done

log "step $step: fine-word analysis"
python3 sim/tune/mdac_fineword.py --corners "$(echo $CORNERS | tr ' ' ',')" > $B/fineword.out 2>&1 || fail "analysis" $B/fineword.out
cat $B/fineword.out >> $ST
for c in $CORNERS; do [ -s $B/fineword_$c.json ] || fail "no fineword_$c.json" $B/fineword.out; done
log "done"
touch $B/DONE
