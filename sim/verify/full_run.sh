#!/bin/bash
# The full verification run (docs/handoff_full_verification.md): one driver, every job chained, started ONCE with the
# Bash tool's run_in_background. Steps:
#   1 setup    tool versions, git revision, earlier outputs moved to build/old/<time>/, the scheduler's .final marker
#   2 jobs     sim/sched.py sim/verify/jobs_full.py (every existing check + the new gap tests), with an hourly
#              progress line (status.txt and, with GITHUB_TOKEN set, the "> Running:" line of the handoff, pushed)
#   3 verdict  sim/verify/verdict.py -> build/verify/verdict.md / verdict.json (every check and mutation)
#   4 done     DONE (with the verdict counts) or FAILED (with the failing step's log tail)
# Config (edit here, not in the scripts): BUDGET, LOAD, TOUT_H (the scheduler's give-up time), DISK_SOFT / DISK_HARD
# (GB over DISK_PATHS: the scheduler holds new jobs and prunes finished raws at the soft limit, kills the newest job
# at the hard one; the pod's disk is 100 GB and must stay under 80, Matt 2026-11-25).
# Results: hourly, sim/verify/persist.py save copies every job's small outputs to results/full_run/, committed and
# pushed with the progress line ([skip ci]). If results/full_run/ already holds a run, the driver RESUMES it
# (persist.py restore; finished jobs are skipped); FRESH=1 starts over.
#   bash sim/verify/full_run.sh          (repo root, IIC-OSIC-TOOLS image)
# Status: build/verify/full/status.txt, build/verify/full/DONE | FAILED; jobs: python3 sim/sched.py --status --out build/verify/full
set -u
export PDK_ROOT=/foss/pdks PDK=gf180mcuD STD_CELL_LIBRARY=gf180mcu_fd_sc_mcu7t5v0   # the image defaults to IHP
BUDGET=${BUDGET:-40}      # cap on the jobs' declared threads (ngspice often uses fewer than it declares)
LOAD=${LOAD:-28}          # real CPU: load average + jobs just started (the pod has 30 CPUs: keep 2 free)
TOUT_H=${TOUT_H:-96}
DISK_SOFT=${DISK_SOFT:-70}
DISK_HARD=${DISK_HARD:-78}
DISK_PATHS=${DISK_PATHS:-/foss/designs,/tmp,$HOME}
FRESH=${FRESH:-0}
DRY=${DRY:-0}          # DRY=1: the driver's own test (two trivial jobs, no outputs moved); DRY=fail: setup must fail
JOBF=sim/verify/jobs_full.py
REPO=$(pwd)
F=$REPO/build/verify/full
HANDOFF=docs/handoff_full_verification.md
RES=results/full_run
if [ "$DRY" != 0 ]; then
  F=$REPO/build/verify/full_dry; JOBF=sim/verify/jobs_dry.py
  RES=build/verify/full_dry_results                   # the dry run's own save / restore test, never committed
  export PERSIST_DST=$RES PERSIST_STATUS=build/verify/full_dry/status.json PERSIST_JOBF=$JOBF
fi
RESUME=0
[ "$FRESH" = 0 ] && [ -s "$RES/${F#$REPO/}/status.json" ] && RESUME=1
if [ "$RESUME" = 0 ] && [ -e "$RES" ]; then             # a fresh start: the earlier run's saved results go
  if [ "$DRY" = 0 ]; then git rm -r -q "$RES"; else command rm -rf "$RES"; fi
fi
mkdir -p "$RES"
mkdir -p "$F"
command rm -f "$F/DONE" "$F/FAILED"
NSTEP=4
T0=$(date +%s)
step() { echo "$(date '+%F %H:%M:%S') step $1/$NSTEP $2: $3" | tee -a "$F/status.txt"; }
push_line() {   # the one-line status at the top of the handoff, committed and pushed (only with a token)
  # pull with a merge, not a rebase: the run rewrites tracked files (the layout job's gds/), and a rebase refuses a dirty tree
  [ -n "${GITHUB_TOKEN:-}" ] && [ "$DRY" = 0 ] || return 0
  python3 - "$HANDOFF" "$1" <<'PY'
import sys, re
p, line = sys.argv[1], sys.argv[2]
t = open(p).read()
t = re.sub(r'(?m)^> (Running|Done|Failed|Not started):.*$', '> ' + line, t, count=1)
open(p, 'w').write(t)
PY
  python3 sim/verify/persist.py save >> "$F/persist.log" 2>&1
  git add "$HANDOFF" && git add -f "$RES" \
    && git -c user.name=Claude -c user.email=noreply@anthropic.com commit -q -m "full verification: $1 [skip ci]" -- "$HANDOFF" "$RES" \
    && git -c user.name=Claude -c user.email=noreply@anthropic.com pull -q --no-rebase --no-edit \
    && git -c credential.helper='!f() { echo username=x-access-token; echo "password=$GITHUB_TOKEN"; }; f' push -q || true
}
fail() {  # fail <step> <name> <log>
  step "$1" "$2" FAILED
  { echo "FAILED at step $1 ($2), $(date -Iseconds)"; echo "--- tail of $3"; tail -40 "$3"; } > "$F/FAILED"
  push_line "Failed: step $1/$NSTEP ($2) at $(date '+%F %H:%M'), see build/verify/full/FAILED"
  exit 1
}

# ---- 1. setup
step 1 setup started
push_line "Running: step 1/$NSTEP setup since $(date '+%F %H:%M')"
{
  echo "git $(git rev-parse --short HEAD) $(git rev-parse --abbrev-ref HEAD)"
  echo "ngspice: $(ngspice -v 2>&1 | grep -m1 ngspice)"
  echo "magic: $(magic -dnull -noconsole --version 2>&1 | head -1)"
  echo "netgen: $(timeout 20 netgen -batch quit < /dev/null 2>&1 | grep -m1 -i 'netgen')"
  echo "klayout: $(timeout 20 klayout -v < /dev/null 2>&1)"
  echo "PDK: $PDK_ROOT/$PDK"
  echo "magic (pinned, for PEX only): $($HOME/.local/magic642/bin/magic -dnull -noconsole --version 2>&1 | tail -1)"
  echo "cores: $(nproc), load $LOAD, budget $BUDGET, disk soft $DISK_SOFT / hard $DISK_HARD GB"
} > "$F/setup.txt" 2>&1
if [ "$RESUME" = 1 ]; then
  python3 sim/verify/persist.py restore >> "$F/setup.txt" 2>&1 || fail 1 setup "$F/setup.txt"
  echo "resumed from $RES" >> "$F/setup.txt"
elif [ "$DRY" = 0 ]; then
  OLD=$REPO/build/old/$(date +%Y%m%d_%H%M); mkdir -p "$OLD"
  for d in build/verify/tile build/verify/tile_existing build/verify/chain build/verify/coupling build/verify/existing \
           build/mixed build/power build/eqy build/fvmut build/mut; do
    [ -e "$d" ] && mv "$d" "$OLD/" 2>/dev/null
  done
  mkdir -p build/verify/tile build/verify/tile_existing build/verify/chain build/verify/coupling build/mixed build/power
fi
[ "$RESUME" = 1 ] || command rm -f "$F/status.json"
touch $JOBF.final                                        # the job list is complete: the scheduler may exit when done
python3 $JOBF > "$F/plan.txt" 2>&1 || fail 1 setup "$F/plan.txt"
for f in layout/pex/tile_c.spice layout/pex/rx_bb_c.spice layout/pex/rx_lim_c.spice layout/pex/rx_lna_c.spice \
         layout/pex/rx_mix_c.spice layout/pex/rx_bias_c.spice $( [ "$DRY" = fail ] && echo layout/pex/missing_for_the_test.spice ); do
  [ -s "$f" ] || { echo "missing $f" >> "$F/setup.txt"; fail 1 setup "$F/setup.txt"; }
done
step 1 setup "done: $(head -1 "$F/setup.txt"); $(head -1 "$F/plan.txt")"

# ---- 2. jobs
step 2 jobs started
push_line "Running: step 2/$NSTEP jobs since $(date '+%F %H:%M'), estimate $(grep -m1 'budget 28' "$F/plan.txt")"
timeout $((TOUT_H * 3600)) python3 sim/sched.py $JOBF --budget "$BUDGET" --load "$LOAD" --out "$F" \
  --disk-paths "$DISK_PATHS" --disk-soft "$DISK_SOFT" --disk-hard "$DISK_HARD" >> "$F/sched.log" 2>&1 &
SP=$!
n=0
while kill -0 $SP 2>/dev/null; do
  sleep ${POLL:-60}; n=$((n + 1))
  if [ $((n % ${SAVE_EVERY:-60})) = 0 ]; then             # hourly: progress line, results saved and pushed
    c=$(python3 -c "
import json, collections
s = json.load(open('$F/status.json'))
c = collections.Counter(v['state'] for k, v in s.items() if not k.startswith('_'))
print(', '.join(f'{k} {c[k]}' for k in ('ok', 'fail', 'stalled', 'skip', 'run', 'wait') if c[k]))")
    c="$c; disk $(cut -d' ' -f3-4 "$F/disk.txt" 2>/dev/null)"
    echo "$(date '+%F %H:%M') progress: $c" >> "$F/status.txt"
    [ "$DRY" = 0 ] || python3 sim/verify/persist.py save >> "$F/persist.log" 2>&1
    push_line "Running: step 2/$NSTEP jobs since $(date -d @$T0 '+%F %H:%M'): $c"
  fi
done
wait $SP
python3 sim/verify/persist.py save >> "$F/persist.log" 2>&1
grep -q "all done" "$F/sched.log" || fail 2 jobs "$F/sched.log"
python3 sim/sched.py --status --out "$F" | grep -v "^ok" > "$F/not_ok.txt"
grep -l -i "singular\|timestep too small\|transient op started" build/verify/*/*/deck.log build/verify/chain/*/*/deck.log \
  build/mixed/*/*.log 2>/dev/null > "$F/flagged_logs.txt"
step 2 jobs "done: $(tail -1 "$F/sched.log" | cut -c10-); flagged logs: $(wc -l < "$F/flagged_logs.txt")"

# ---- 3. verdict
step 3 verdict started
python3 sim/verify/verdict.py $( [ "$DRY" != 0 ] && echo --smoke ) > "$F/verdict.log" 2>&1
V=build/verify/verdict.md; [ "$DRY" != 0 ] && V=build/verify/verdict_smoke.md
[ -s $V ] || fail 3 verdict "$F/verdict.log"
step 3 verdict "done: $(tail -1 $V)"

# ---- 4. done
command rm -f $JOBF.final
{ echo "done $(date -Iseconds), $(( ($(date +%s) - T0) / 3600 )) h"; tail -1 $V; } > "$F/DONE"
step 4 done "$(tail -1 $V)"
push_line "Done: $(date '+%F %H:%M'), $(tail -1 $V) ($V; write-up next)"
