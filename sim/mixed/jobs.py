"""Scheduler job file for the mixed-signal co-simulation (sim/sched.py; sim/mixed/gen_mixed.py has the runs).

    mkdir -p build/mixed && nohup setsid python3 sim/sched.py sim/mixed/jobs.py --budget 8 --out build/mixed \
        > build/mixed/sched.log 2>&1 &
    python3 sim/sched.py --status --out build/mixed
Every job is single-threaded ngspice (num_threads=1). Judge the runs by build/mixed/<name>/result.json and the
logs (sim/mixed/analyse.py checks the ngspice log for singular / timestep too small / Transient op started), then
python3 sim/mixed/verdict.py.
"""
import os
import sys

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "sim/mixed"))
import gen_mixed as G  # noqa: E402

EST = dict(step=2000, sd=1500, io=30, ref=330)
JOBS = [dict(name="build_so", cmd=f"cd {REPO} && bash sim/mixed/build_so.sh", threads=1, est=60)]
RERUN = {}     # bump to re-run a failed job (the scheduler re-runs a failed job whose command changed)
for n in G.names():
    kind = "ref" if n.startswith("ref_") else n.split("_")[0]
    tag = f"  # rerun {RERUN[n]}" if n in RERUN else ""
    JOBS.append(dict(name=n, cmd=f"cd {REPO} && python3 sim/mixed/gen_mixed.py run {n}{tag}", threads=1, est=EST[kind],
                     deps=["build_so"]))
JOBS.append(dict(name="verdict", cmd=f"cd {REPO} && python3 sim/mixed/verdict.py --mutants", threads=1, est=30,
                 deps=[n for n in G.names()]))
