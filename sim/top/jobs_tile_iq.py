"""Scheduler job file for the iq-symmetry re-run on the re-extracted tile (branch iq-symmetry, 2026-11-19): the
Q level shifter moved into vco_core (docs/tile_layout.md, sim/top/tile_results.md "Update 2026-11-19").

    mkdir -p build/tile_sims_iq && TILE_SIMS_OUT=build/tile_sims_iq nohup setsid python3 sim/sched.py \
        sim/top/jobs_tile_iq.py --budget 24 --out build/tile_sims_iq > build/tile_sims_iq/sched.log 2>&1 &
    TILE_SIMS_OUT=build/tile_sims_iq python3 sim/top/tb_tile_verdict.py [--mutants]
The block references (ref_*, sim/top/tb_tile_ref.py) are not re-run: the blocks didn't change; their result
directories are linked from build/tile_sims. Estimates: the last run's measured times (build/tile_sims/*/runtime.txt)
+ 10 %. Every job is one ngspice; judge by result.json and the deck.log tails, not exit codes.
"""
import os
import sys
from pathlib import Path

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
OUT = os.path.join(REPO, "build", "tile_sims_iq")
os.environ["TILE_SIMS_OUT"] = OUT
sys.path.insert(0, os.path.join(REPO, "sim/top"))
sys.modules.pop("tb_tile", None)
import tb_tile as T  # noqa: E402

C = T.cases()
NAMES = ([n for n in C if n.startswith("vco_c_") and not n.endswith("_rx")]
         + ["iq_c_tt", "iq_c_ss", "iq_c_ff", "mut_iq_a2c",
            "tx_c_tt_on", "tx_c_tt_off", "tx_c_tt_on_k13", "mut_tx_noen", "mut_tx_rsw10",
            "rxhpre_c_tt", "rxh_c_tt_-70_p", "rxh_c_tt_-70_n", "mut_rx_off", "rxset_c_tt", "rxs_c_tt_-95_p",
            "dbg_c_tt", "mut_dbg_swap01", "mut_dbg_c_rxoff", "mut_vco_code", "mut_pwrup_txon", "iqx_vq_c_tt", "iqx_vq_c_ss"])
OLD = Path(REPO) / "build" / "tile_sims"


def est(n):
    try:
        return int(float((OLD / n / "runtime.txt").read_text()) * 1.1)
    except (OSError, ValueError):
        return C[n]["est"]


JOBS = []
for n in NAMES:
    c = C[n]
    j = dict(name=n, cmd=f"cd {REPO} && TILE_SIMS_OUT={OUT} python3 sim/top/tb_tile.py run {n}",
             threads=c.get("threads", 1), est=est(n))
    if c.get("pre"):
        j["deps"] = [c["pre"]]
    if n in ("rxset_c_tt", "rxhpre_c_tt") or n.startswith(("iq_c_", "mut_iq")):
        j["prio"] = 1             # the heads of the 2-3 h RX chains, and the new I/Q check, start first
    JOBS.append(j)
