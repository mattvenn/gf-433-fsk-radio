"""Run a list of verification jobs on one machine within a CPU budget (sim-0: 28 CPUs).

A job file (Python) defines JOBS = [dict(name=, cmd=, threads=, est=, deps=[...], lock=None), ...]:
  threads: CPUs the job keeps busy (ngspice NT / num_threads; 1 for python, magic, verilator ...)
  est:     expected wall time, s (longest first: the long runs start early)
  deps:    names that must have finished OK first
  lock:    jobs with the same lock never run together (a shared netlist / output file)
  prio:    start order before est (default 0): e.g. the short first job of a long dependency chain
  stagger: (group, s): a job of the group starts at least s after the previous one (scripts that rewrite
           a shared netlist at start, then only read their own copy)
A job starts when its deps are done, its lock is free, the threads of the running jobs plus its own stay
within --budget, and the 1-minute load average is below --load (so work running outside the scheduler
counts too). Each job's output goes to <out>/logs/<name>.log; <out>/status.json has every job's state,
exit code, start and end. A restarted scheduler adopts jobs an earlier instance left running (state
'exited' when they end: their exit status is lost, judge them by their logs). The job file is re-read when it changes, so jobs can be appended while it runs;
a failed job whose command changed runs again. It exits once nothing is running or waiting and
<jobs>.final exists. A restart skips jobs already OK.

    nohup setsid python3 sim/rerun/sched.py sim/rerun/jobs_2026-10-13.py --budget 26 > build/rerun/sched.log 2>&1 &
    python3 sim/rerun/sched.py --status [--out build/rerun]

Disk watch (2026-11-25: the full run's pod was lost, possibly at its 50 GB disk limit): every --disk-every s the
scheduler measures `du` over --disk-paths and writes <out>/disk.txt.
  >= --disk-soft GB: no new job starts, and finished jobs' *.raw waveforms are deleted, oldest first, until the
            total is 5 GB below the soft limit. Only a raw with a newer result.json beside it, in a directory no
            unfinished job depends on, is deleted; the verdicts read result.json, not the raw.
  >= --disk-hard GB: the most recently started job is killed and requeued (state wait), one per check.
"""
import argparse
import json
import os
import runpy
import signal
import subprocess
import time
from pathlib import Path

H_RESERVE = 3600                                          # jobs this long (s) reserve their threads
ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))   # the repo (was '..', '..' from sim/rerun/)


def load_status(path):
    try:
        return json.load(open(path))
    except (OSError, ValueError):
        return {}


def alive(pid):
    """A job's process is the leader of its own session (start_new_session); bash may have exec'd the
    command, so don't match on the name."""
    try:
        return os.getsid(pid) == pid
    except OSError:
        return False


def disk_gb(paths):
    """Bytes under the paths (du -sbx), in GB; None if du fails. Hard links are counted once."""
    try:
        r = subprocess.run(['du', '-scbx'] + paths, capture_output=True, text=True, timeout=600)
        return int(r.stdout.strip().splitlines()[-1].split()[0]) / 1e9
    except Exception:                                    # noqa: BLE001
        return None


def prune_raws(roots, keep_dirs, need_gb, log):
    """Delete finished jobs' *.raw files, oldest first, until need_gb GB are freed. A raw is deletable when a newer
    result.json sits beside it (the job analysed it) and its directory's name is not in keep_dirs (a job a waiting
    or running job depends on: it may read the raw). Returns the GB freed."""
    cand = []
    for r in roots:
        for f in Path(r).rglob('*.raw'):
            res = f.parent / 'result.json'
            try:
                if f.parent.name in keep_dirs or not res.exists() or res.stat().st_mtime < f.stat().st_mtime:
                    continue
                cand.append((f.stat().st_mtime, f.stat().st_size, f))
            except OSError:
                continue
    freed = 0
    for _, size, f in sorted(cand):
        if freed >= need_gb * 1e9:
            break
        try:
            f.unlink()
            freed += size
            log(f'disk: pruned {f} ({size / 1e9:.2f} GB)')
        except OSError:
            pass
    return freed / 1e9


def show(out):
    st = load_status(os.path.join(out, 'status.json'))
    now = time.time()
    for name, s in sorted(st.items(), key=lambda kv: (kv[1]['state'], kv[0])):
        t = (s.get('end') or now) - s['start'] if s.get('start') else 0
        print(f"{s['state']:8s} {name:40s} rc={s.get('rc')!s:5s} {t / 60:7.1f} min  thr={s.get('threads')}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('jobs', nargs='?')
    ap.add_argument('--budget', type=int, default=26)
    ap.add_argument('--load', type=float, default=28.0)
    ap.add_argument('--out', default=os.path.join(ROOT, 'build', 'rerun'))
    ap.add_argument('--status', action='store_true')
    ap.add_argument('--disk-paths', default=ROOT, help='comma-separated paths whose total size is watched')
    ap.add_argument('--disk-soft', type=float, default=70.0, help='GB: start no job, prune finished raws')
    ap.add_argument('--disk-hard', type=float, default=78.0, help='GB: kill and requeue the newest job')
    ap.add_argument('--disk-every', type=float, default=120.0, help='s between disk checks')
    ap.add_argument('--prune-roots', default=os.path.join(ROOT, 'build'),
                    help='comma-separated directories where finished raws may be pruned')
    a = ap.parse_args()
    if a.status:
        return show(a.out)
    os.makedirs(os.path.join(a.out, 'logs'), exist_ok=True)
    spath = os.path.join(a.out, 'status.json')
    st = load_status(spath)
    jobs, mtime = {}, None
    run = {}                                              # name -> Popen
    last = {}                                             # stagger group -> last start time
    adopted = {n: s0['pid'] for n, s0 in st.items()       # still running from an earlier instance
               if s0.get('state') == 'run' and s0.get('pid') and alive(s0['pid'])}

    def reload():
        """(Re)read the job file: jobs can be added while the scheduler runs. Running / finished jobs
        keep their state; a new or not-yet-OK job waits."""
        nonlocal jobs, mtime
        new = {j['name']: {**dict(deps=[], lock=None, est=600, threads=1), **j}
               for j in runpy.run_path(a.jobs)['JOBS']}
        for j in new.values():
            for d in j['deps']:
                assert d in new, f"{j['name']}: unknown dep {d}"
        for n in new:                                     # new, unfinished, or failed with a changed command
            s0 = st.get(n, {})
            if n not in run and n not in adopted and (s0.get('state') not in ('ok', 'fail', 'skip', 'exited')
                                 or (s0.get('state') in ('fail', 'skip') and s0.get('cmd') != new[n]['cmd'])):
                st[n] = dict(state='wait', threads=new[n]['threads'])
        for n in list(st):                                # dropped from the file: forget it unless running
            if n not in new and n not in run and n not in adopted and st[n]['state'] == 'wait':
                del st[n]
        jobs = {**{n: jobs[n] for n in run}, **{n: dict(threads=st[n]['threads'], deps=[], lock=None, est=0, cmd='')
                                                 for n in adopted if n not in new}, **new}
        mtime = os.path.getmtime(a.jobs)

    def save():
        json.dump(st, open(spath + '.tmp', 'w'), indent=1)
        os.replace(spath + '.tmp', spath)

    def log(msg):
        print(time.strftime('%H:%M:%S'), msg, flush=True)

    dpaths = [p for p in a.disk_paths.split(',') if p and os.path.exists(p)]
    droots = [p for p in a.prune_roots.split(',') if p]
    dlast, dgb, dfull = 0.0, None, False

    def disk_check():
        """Measure; above soft prune and hold new jobs; above hard kill the newest job. Returns True when full."""
        nonlocal dgb
        dgb = disk_gb(dpaths)
        if dgb is None:
            log('disk: du failed, treating as full')
            return True
        full = dgb >= a.disk_soft
        if full:
            pending = {n for n, s0 in st.items() if s0['state'] in ('wait', 'run')}
            keep = set()
            for n in pending:
                for d in jobs.get(n, {}).get('deps', []):
                    keep |= {d, d.split('_', 1)[-1]}     # te_x / mx_x jobs write to a directory named x
            freed = prune_raws(droots, keep, dgb - (a.disk_soft - 5), log)
            if freed:
                dgb = disk_gb(dpaths) or dgb
            full = dgb >= a.disk_soft
        if dgb >= a.disk_hard and run:
            n = max(run, key=lambda m: st[m]['start'])
            try:
                os.killpg(run[n].pid, signal.SIGTERM)
                run[n].wait(timeout=60)
            except Exception:                            # noqa: BLE001
                try:
                    os.killpg(run[n].pid, signal.SIGKILL)
                except OSError:
                    pass
            del run[n]
            st[n].update(state='wait', rc=None, start=None, pid=None, requeued=st[n].get('requeued', 0) + 1)
            log(f'disk: {dgb:.1f} GB >= hard {a.disk_hard} GB: killed and requeued {n}')
        with open(os.path.join(a.out, 'disk.txt'), 'w') as fh:
            fh.write(f"{time.strftime('%F %H:%M:%S')} {dgb:.1f} GB (soft {a.disk_soft}, hard {a.disk_hard})"
                     f"{' FULL: no new jobs' if full else ''}\n")
        return full

    reload()
    for n, pid in adopted.items():
        log(f'adopted {n} (pid {pid}, started by an earlier instance)')
    while True:
        if time.time() - dlast >= a.disk_every:
            was = dfull
            dfull = disk_check()
            dlast = time.time()
            if dfull != was:
                log(f'disk: {dgb if dgb is not None else -1:.1f} GB, ' + ('holding new jobs' if dfull else 'resumed'))
        for n, pid in list(adopted.items()):
            if not alive(pid):                            # its exit status isn't ours to read: judge by its log
                st[n].update(state='exited', rc=None, end=time.time())
                del adopted[n]
                log(f'exited {n} (adopted; check its log)')
        if os.path.getmtime(a.jobs) != mtime:
            try:
                reload()
                log('job file reloaded')
            except Exception as e:                       # a half-written file: try again next round
                log(f'job file not loaded ({e})')
        for n, p in list(run.items()):
            rc = p.poll()
            if rc is not None:
                st[n].update(state='ok' if rc == 0 else 'fail', rc=rc, end=time.time())
                del run[n]
                log(f'{"done" if rc == 0 else "FAIL"} {n} (rc {rc}, {(st[n]["end"] - st[n]["start"]) / 60:.1f} min)')
        # a failed dep fails its dependents; a skipped job waits again once its deps have recovered
        for n, j in jobs.items():
            if st[n]['state'] == 'skip' and not any(st[d]['state'] in ('fail', 'skip') for d in j['deps']):
                st[n].update(state='wait')
                log(f'requeue {n} (its deps recovered)')
            if st[n]['state'] == 'wait' and any(st[d]['state'] in ('fail', 'skip') for d in j['deps']):
                st[n].update(state='skip', rc=None)
                log(f'skip {n} (a dep failed)')
        ready = [n for n, j in jobs.items() if st[n]['state'] == 'wait'
                 and all(st[d]['state'] in ('ok', 'exited') for d in j['deps'])]
        ready.sort(key=lambda n: (-jobs[n].get('prio', 0), -jobs[n]['est']))   # prio first (a long chain's head)
        reserved = 0                                      # threads held back for a longer job that didn't fit
        for n in ready if not dfull else []:
            j = jobs[n]
            used = sum(jobs[m]['threads'] for m in run) + sum(st[m]['threads'] for m in adopted) + reserved
            if used + j['threads'] > a.budget and (run or adopted):
                # don't let shorter jobs keep filling the gap it is waiting for (2026-10-13: an 8-thread
                # job starved behind 4-thread ones): hold its threads unless it can never fit
                # (one job at a time: ook-asic-radio 2026-11-04, three waiting 8-thread jobs each reserved,
                # 24 of 26, and nothing else started for ~7 h at load 7)
                if j['est'] >= H_RESERVE and j['threads'] <= a.budget and not reserved:
                    reserved += j['threads']
                continue
            if j['lock'] and any(jobs[m]['lock'] == j['lock'] for m in list(run) + list(adopted) if m in jobs):
                continue
            if j.get('stagger') and time.time() - last.get(j['stagger'][0], 0) < j['stagger'][1]:
                continue
            ext = max(0.0, os.getloadavg()[0] - used)    # load from work outside the scheduler
            if (run or adopted) and used + j['threads'] + ext > a.load:
                continue                                  # a smaller job may still fit (was break: stalled)
            fh = open(os.path.join(a.out, 'logs', n + '.log'), 'w')
            run[n] = subprocess.Popen(['bash', '-c', j['cmd']], cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT,
                                      start_new_session=True)
            st[n].update(state='run', start=time.time(), pid=run[n].pid, cmd=j['cmd'])
            if j.get('stagger'):
                last[j['stagger'][0]] = time.time()
            log(f'start {n} ({j["threads"]} thr, est {j["est"] / 60:.0f} min; running {used + j["threads"]})')
        save()
        if not run and not adopted and not any(s['state'] == 'wait' for s in st.values()) and os.path.exists(a.jobs + '.final'):
            break                                         # touch <jobs>.final when no more jobs will be added
        time.sleep(10)
    log('all done: ' + ', '.join(f'{k} {sum(1 for s in st.values() if s["state"] == k)}'
                                  for k in ('ok', 'fail', 'skip')))


if __name__ == '__main__':
    main()
