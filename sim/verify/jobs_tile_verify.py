"""Scheduler job file (sim/sched.py) for the extracted-tile verification runs (sim/verify/tile_verify.py), gaps 2-6.

    VERIFY_SET=smoke|full (default full); TILE_SIMS_OUT (default build/verify/tile)
    mkdir -p build/verify/tile && VERIFY_SET=smoke nohup setsid python3 sim/sched.py sim/verify/jobs_tile_verify.py \
        --budget 22 --out build/verify/tile > build/verify/tile/sched.log 2>&1 &
The RX pre-run rxset_c_tt is tb_tile.py's own case, run into the same directory (the full run reruns it; the smoke
run links the 2026-11-20 one from build/tile_sims_nb, same netlist). Estimates: smoke-run times (sim/verify/
estimates.json when present) + 10 %, else the case's est. Judge by result.json and the log tails, not exit codes.
"""
import json
import os
import sys

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.environ.get("TILE_SIMS_OUT", os.path.join(REPO, "build", "verify", "tile"))
os.environ["TILE_SIMS_OUT"] = OUT
sys.path.insert(0, os.path.join(REPO, "sim/verify"))
for m in ("tb_tile", "tile_verify"):
    sys.modules.pop(m, None)
import tile_verify as V  # noqa: E402

SET = os.environ.get("VERIFY_SET", "full")
C = V.cases()
NAMES = V.SMOKE if SET == "smoke" else [n for n in C if not n.endswith("_n2") and "_n2_" not in n]
try:
    EST = json.load(open(os.path.join(REPO, "sim/verify/estimates.json")))
except (OSError, ValueError):
    EST = {}
E = f"cd {REPO} && TILE_SIMS_OUT={OUT} "
RERUN = {"fskn_c_tt_-105_n2_s1": 1, "pvt_ss_70_3.15_pu": 1}     # bump to re-run a failed job (the scheduler re-runs it when its command changes)
JOBS = []
if SET != "smoke":
    JOBS.append(dict(name="rxset_c_tt", cmd=E + "python3 sim/top/tb_tile.py run rxset_c_tt", threads=4, est=2600, prio=1))
for n in NAMES:
    c = C[n]
    j = dict(name=n, cmd=E + f"python3 sim/verify/tile_verify.py run {n}" + (f"  # rerun {RERUN[n]}" if n in RERUN else ""),
             threads=c.get("threads", 1),
             est=int(EST.get(n, c["est"] / 1.1) * 1.1), deps=[d for d in V.deps(n, c) if d in NAMES or d == "rxset_c_tt"])
    if SET == "smoke":
        j["deps"] = [d for d in j["deps"] if d != "rxset_c_tt"]
    if n.endswith("_op"):
        j["prio"] = 2
    if n == "mut_rx0_ccoup":
        j["deps"].append("coupling_budget")
    JOBS.append(j)
if SET != "smoke":
    JOBS.append(dict(name="coupling_budget", cmd=f"cd {REPO} && python3 sim/verify/coupling.py", threads=1, est=600))
