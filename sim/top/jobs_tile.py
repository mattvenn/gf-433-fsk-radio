"""Scheduler job file for the extracted-tile simulations (sim/sched.py; the cases are in sim/top/tb_tile.py, the
block-level references in sim/top/tb_tile_ref.py, the verdicts in sim/top/tb_tile_verdict.py).

    mkdir -p build/tile_sims && nohup setsid python3 sim/sched.py sim/top/jobs_tile.py --budget 14 \
        --out build/tile_sims > build/tile_sims/sched.log 2>&1 &
    python3 sim/sched.py --status --out build/tile_sims
Every job is one single-threaded ngspice (num_threads=1). Judge the runs by build/tile_sims/<name>/result.json and
the deck.log tails (flags: singular / timestep too small / Transient op started), not by exit codes.
"""
import os
import sys

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.join(REPO, "sim/top"))
for _m in ("tb_tile", "tb_tile_ref"):          # the scheduler re-runs this file: pick up edited cases
    sys.modules.pop(_m, None)
import tb_tile as T  # noqa: E402
import tb_tile_ref as R  # noqa: E402

JOBS = []
for n, c in T.cases().items():
    j = dict(name=n, cmd=f"cd {REPO} && python3 sim/top/tb_tile.py run {n}" + (f" --rev {c['rev']}" if c.get("rev") else ""), threads=c.get("threads", 1), est=c["est"])
    if c.get("pre"):
        j["deps"] = [c["pre"]]
    if c["kind"] == "rx" and n not in ("rx_c_tt_-70_p", "rxh_c_tt_-70_p", "rxh_c_tt_-70_n", "rxh_c_tt_-95_p"):
        j["deps"] = j.get("deps", []) + ["rxh_c_tt_-70_p"]   # queue behind tt: no thread reservation meanwhile
    JOBS.append(j)
for n in R.cases():
    # tb_tile_ref rewrites build/tx_fine/mdac/mdac_cm_ports.spice when it builds a deck: start them apart
    JOBS.append(dict(name=n, cmd=f"cd {REPO} && python3 sim/top/tb_tile_ref.py run {n}", threads=1, est=2400 if ("ca16" in n or "schdac" in n) else 2000,
                     stagger=("ref", 20)))
