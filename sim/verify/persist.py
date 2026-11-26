"""Keep the full run's results in git, so a lost machine (the sim server's pod was replaced on 2026-11-22/25 and took
538 finished jobs with it) costs only the jobs that were running.

  python3 sim/verify/persist.py save      # build/ -> results/full_run/ (small text files only), run by the driver hourly
  python3 sim/verify/persist.py restore   # results/full_run/ -> build/, status.json fixed so a restart skips OK jobs
  python3 sim/verify/persist.py size      # what save would keep, MB

Saved: every *.json / *.txt / *.csv / *.md / *.log under the run's output directories (logs over MAX bytes keep their
last lines as <name>.tail). Not saved: waveforms (*.raw), decks and netlists (regenerated from the job files).
The verdicts (sim/verify/verdict.py and the scripts it calls) read result.json and logs, so they run on a restore.

On restore the scheduler's status.json is fixed: jobs that were running when the machine went are set to wait, and
an OK job some unfinished job depends on is set to wait too (its dependents may need files that are not saved).
"""
import filecmp
import json
import os
import runpy
import shutil
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DST = REPO / os.environ.get('PERSIST_DST', 'results/full_run')
DIRS = ['build/verify', 'build/mixed', 'build/power', 'build/tile/run', 'build/eqy', 'build/fvmut', 'build/mut']
EXCL_DIRS = ({'old'} if os.environ.get('PERSIST_DST') else {'full_dry', 'old'}) | {DST.name}
EXT = {'.json', '.txt', '.csv', '.md', '.log'}
MAX = 64 * 1024
TAIL = 200
STATUS = os.environ.get('PERSIST_STATUS', 'build/verify/full/status.json')
JOBF = os.environ.get('PERSIST_JOBF', 'sim/verify/jobs_full.py')      # the driver's dry run sets these three


def files(root):
    for d in DIRS:
        base = root / d
        if not base.is_dir():
            continue
        for dp, dn, fn in os.walk(base):
            dn[:] = [x for x in dn if x not in EXCL_DIRS and not x.startswith('sim_build')]
            for f in fn:
                p = Path(dp) / f
                if p.suffix in EXT or p.name.endswith('.tail'):
                    yield p


def save():
    n = 0
    for p in files(REPO):
        rel = p.relative_to(REPO)
        try:
            size = p.stat().st_size
        except OSError:
            continue
        out = DST / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        # long logs: keep the tail (the verdict reads the end). JSON whole: a truncated status.json can't resume (2026-11-26:
        # at 974 jobs it passed 64 KB, was saved only as status.json.tail, and a restart took the fresh-start path)
        if size > MAX and p.suffix != '.json':
            out = out.with_name(out.name + '.tail')
            lines = p.read_text(errors='replace').splitlines()[-TAIL:]
            txt = f'[tail: last {len(lines)} lines of {size} bytes]\n' + '\n'.join(lines) + '\n'
            if out.exists() and out.read_text(errors='replace') == txt:
                continue
            out.write_text(txt)
        else:
            if out.exists() and filecmp.cmp(p, out, shallow=False):
                continue
            shutil.copy2(p, out)
        n += 1
    print(f'saved {n} changed files to {DST.relative_to(REPO)}')


def restore():
    if not DST.is_dir():
        sys.exit(f'nothing to restore: {DST} missing')
    n = 0
    for dp, _, fn in os.walk(DST):
        for f in fn:
            src = Path(dp) / f
            rel = src.relative_to(DST)
            out = REPO / rel
            if out.exists():
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out)
            n += 1
    print(f'restored {n} files into build/')
    sp = REPO / STATUS
    if not sp.exists():
        return
    st = json.loads(sp.read_text())
    st.pop('_sched', None)                               # the dead scheduler's heartbeat
    jobs = {j['name']: j for j in runpy.run_path(str(REPO / JOBF))['JOBS']}
    for n_, s in st.items():                             # running when the machine went: run again
        if s.get('state') == 'run':
            s.update(state='wait', pid=None, start=None, rc=None, lost=s.get('lost', 0) + 1)
    changed = True
    while changed:                                       # an OK job with an unfinished dependent runs again
        changed = False
        for n_, j in jobs.items():
            if st.get(n_, {}).get('state') in ('ok', 'exited'):
                continue
            for d in j.get('deps', []):
                if st.get(d, {}).get('state') in ('ok', 'exited'):
                    st[d].update(state='wait', pid=None, start=None, rc=None)
                    changed = True
    sp.write_text(json.dumps(st, indent=1))
    c = {}
    for s in st.values():
        c[s['state']] = c.get(s['state'], 0) + 1
    print('status after restore: ' + ', '.join(f'{k} {v}' for k, v in sorted(c.items())))


def size():
    tot = 0
    for p in files(REPO):
        try:
            tot += min(p.stat().st_size, MAX)
        except OSError:
            pass
    print(f'{tot / 1e6:.1f} MB would be saved')


if __name__ == '__main__':
    {'save': save, 'restore': restore, 'size': size}[sys.argv[1] if len(sys.argv) > 1 else 'size']()
