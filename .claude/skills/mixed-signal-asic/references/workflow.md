# Working with several Claude sessions and machines

The previous chip was built by several sessions at once (Mac, cloud pod, big Linux box), all pushing to
`main`.

## Docs that keep sessions efficient
- `docs/agent_start.md`: read first, kept small.
  - Rules: only work on what you were assigned; fetch and rebase before every push; small commits.
  - What to read: STATUS.md whole, `grep` history.md for your block only, signatures and docstrings of
    shared libraries (`grep -n "^def \|^class \|\"\"\"" rows.py`, not the bodies), and one finished
    generator of a similar block as a template.
  - Pipe long output through tail/grep.
  - Done criteria per block.
  - An example prompt.
- `STATUS.md`: short, "pick up from here". Per-block detail lives in `docs/history.md`.
- `docs/layout.md`: one section per block, with results and lessons others can reuse.
- `docs/handoff_<topic>.md`: a paste-as-is prompt for a fresh session, structured as:
  - goal in one bold line;
  - Read first;
  - tools and host notes;
  - what exists (paths, run times);
  - numbered steps;
  - Verify (commands, pass criteria, reference numbers);
  - Don't (files other sessions own);
  - once complete, a "Done (date)" banner pointing to the next handoff.
- Plans carry a target-spec table, candidate approaches, tests per phase, a deliverable, a review gate,
  a risk table with fallbacks, and a "not pursued" banner when dropped.
- Record decisions with owner and date, keeping the recommendation next to the chosen option.
- Record reproduction commands and saved baselines (`sim/<x>/results/<date>/`) so later sessions
  compare like with like.

## Git with parallel sessions
- Fetch and rebase onto `origin/main` before every push. Re-check that the shared docs (STATUS.md,
  layout.md) merged cleanly, since they conflict most.
- Sessions can share one checkout and index: another session's commit swept up files someone had just
  staged. **Stage and commit in one command**, never `git add -A` / `commit -a`, and never `rebase
  --autostash` (it stashed another session's edits and conflicted). Rebase from a throwaway worktree
  instead.
- Risky or shared changes (generators, floorplan, shared tools) go on a branch in a separate worktree
  (`git worktree add ../repo-topic -b topic`), so main stays a tapeout-ready fallback. Merge only when
  the human says. Copy the gitignored inputs (pcell venv, DEF) into the new worktree.
- If a request looks like it was meant for another session's job, ask before acting.
- Subagents may be blocked from `git push` by the permission classifier. Brief them to commit their own paths only,
  and push from the main session.
- A measurement session doesn't edit the generators another session is changing. It measures, reports
  and proposes options with an estimated effect each, and the human picks.
- Block moves, circuit changes and spec trade-offs are the human's call. When stuck, stop and write
  down what and why rather than forcing a route.
- Batch small layout fixes for the next tile rebuild, and keep layout compromises on an explicit
  sign-off list for the owner.

## Long jobs
- Anything over a minute: run it in the background and end the turn. Never wait on it with a
  foreground `until … sleep` loop.
- `scripts/longrun <name> <cmd>`: detached, logged, a `.done` marker, the machine kept awake. On the
  Mac use `caffeinate -i`.
- `scripts/sched.py`: a job list with threads/est/deps/lock/stagger, run within a CPU budget and a
  load-average limit. It adopts orphaned jobs on restart, re-reads the job file, and reruns failed jobs
  whose command changed. Long jobs reserve their threads, and the short jobs that gate long ones go
  first.
- **Every `est` from a measurement.** After each run, `durations.py --json` writes per-job minutes into a
  tracked file, and the next job file loads it (+10 %). Guessed estimates in one run were 8–88× out, and a
  large wrong `est` also decides start order and thread reservations.
- Don't fake an `est` to steer the scheduler: raising priority jobs to 20 h hid their real times and made them
  reserve threads. Use `prio` (start order) and `reserve: False` (a waiting long job doesn't hold threads).
- Declare the threads a job really keeps busy: one job running two ngspice at ~3 CPUs each, declared as 4,
  pushed the load to 37–39 on 28 CPUs and slowed everything 5–10 %.
- An estimate for a set of jobs is its longest job, not the typical one: "about an hour" for a power-delivery
  pass forgot its 6.6 h TX transient. Read the durations file before quoting.
- Before blaming a suspect for a slow run, A/B it with short timing runs (old vs fixed input, small vs big
  netlist). A plausible bug (repeated PWL times) turned out to cost nothing; the netlist and the load did.
- Don't edit a script while it runs. Don't run two copies of a script that rewrites a shared netlist.
- Judge runs by their output files, not exit codes.
- **Background agents end their turn "waiting" on a run and sit idle.** One did for 3 hours. Every brief needs:
  "never end your turn while runs are pending; wait with a background command that exits when they finish".
- Wait on a scheduler through its status file (`sched.py --status`, `status.json`), not `pgrep -f <script>`. The
  wait loop's own command line contains the pattern, so `pgrep -f` matches itself and the loop never exits.

### Unattended runs on a sim server (paste into each handoff as "Running unattended")
Tested on gf-433-oscillator: results pushed under 2 minutes after the last sim, with no human ping.
1. Start jobs with `run_in_background` (the harness wakes the agent when they exit), never a bare `nohup … &`. If a
   job must outlive the session, also watch a done-marker with a Monitor.
2. **One driver script per handoff** chaining every job; corner lists come from a config section in the handoff.
   Each step writes `status.txt`; the end writes `DONE` or `FAILED` (with the log tail).
3. Fail early: each step checks its own outputs (files, row counts, no "Transient op", no "singular") before the
   next starts. Retry at most twice, then write up and stop.
4. A heartbeat wakeup at ~1.5× the estimate (20-60 min, re-armed), in case a notification is missed.
5. Push a `> Running: step N/M since HH:MM, ETA HH:MM` line at the top of the handoff at each step change, and the
   `Done` line at the end.
6. Write up, commit and push in the same session, straight after the driver ends.

## Estimates
- Quote run times from the timestamps of the same jobs (`ls -lT build/...`), with every chained step
  included. Past mistake: "~45 min" for three variants that took ~45 min *each*.
- Estimate Claude's own coding work from how long similar changes took in this repo (often minutes),
  not from what a person would need.

## Reports
- Every table has units, in the column header or beside each number.
- Every run report has a job-duration table (count, threads, min / median / max, est, ratio) and what the
  times say for next time.
- Check every number in a draft against its log before publishing: a 40-row report's first draft had five
  wrong (a misread column, block counts, a supply point).
- When a later run disproves an explanation in a report, correct the report, the TODO and the code comments
  in one commit, and say so plainly.

## Machines
- Laptop: design, layout, small sims. The big machine: full verification batches, started from a
  handoff doc with the branch pushed.
- Tools wrapper (`scripts/osic-mac`): runs any command in the pinned IIC-OSIC-TOOLS image with the repo
  mounted at its own path, `.designinit` mounted (without it the image defaults to IHP and
  KLayout/netgen fail), `.spiceinit` copied into `build/`, `[INFO]` noise filtered, and an
  `OSIC_PDK_ROOT` override for the TT precheck's PDK hash. Inside the image (a pod) it runs commands
  directly.
- Pods are stateless: an idempotent `pod_setup.sh` handles git identity, the credential helper, the
  pinned magic build and missing pip deps.
- Explain docker commands before running them.

## Nice extras that paid off
- An interactive explainer page built from the simulation files doubled as a video storyboard. Keep
  its claims exactly as accurate as the verification, because the video outlives the page.
- A GDS → PNG render (`render_gds.py`) and TT GDS viewer links (`gds_links.py`) in the layout README.
- Classical redrawn schematics with device values shown, for review.
