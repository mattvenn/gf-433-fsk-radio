"""The full verification run's job file (sim/sched.py): every EXISTING check of docs/verification.md and the NEW gap
1-6 tests of docs/plan_verify_gaps.md, in one scheduler. Driver: sim/verify/full_run.sh; brief:
docs/handoff_full_verification.md; verdict: sim/verify/verdict.py (run by the driver after the scheduler ends, so a
failed job never stops the verdict).

  ex_*   existing digital / layout checks (sim/verify/existing.sh: pinout, test/mutations.sh, cocotb RTL + GL, formal
         prove / gates_bmc / mutate.sh, eqy, floorplan, xschem, layout/gen/tile_driver.sh)
  mx_*   the mixed-signal co-simulation (sim/mixed/jobs.py)                      -> build/mixed
  te_*   the existing extracted-tile set (sim/top/jobs_tile.py, every case + the block references)
                                                                                 -> build/verify/tile_existing
  pw_*   the power grid IR drop / EM (sim/power/jobs.py)                         -> build/power
  (new)  gaps 2-6 on the tile (sim/verify/jobs_tile_verify.py)                   -> build/verify/tile
         gaps 1, 2, 4, 5 on the extracted blocks (sim/verify/jobs_chain.py)      -> build/verify/chain, coupling

    python3 sim/verify/jobs_full.py            # print the job count, CPU-hours and a wall-time estimate per budget
"""
import os
import runpy
import sys

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
os.environ.setdefault("VERIFY_SET", "full")
TE = os.path.join(REPO, "build", "verify", "tile_existing")
TV = os.path.join(REPO, "build", "verify", "tile")


def load(path, env=None):
    old = dict(os.environ)
    os.environ.update(env or {})
    for m in ("tb_tile", "tb_tile_ref", "tile_verify", "gen_mixed"):
        sys.modules.pop(m, None)
    try:
        return runpy.run_path(os.path.join(REPO, path))["JOBS"]
    finally:
        os.environ.clear()
        os.environ.update(old)


def prefixed(jobs, pre, cmd_env=None, drop=()):
    out = []
    names = {j["name"] for j in jobs}
    for j in jobs:
        if j["name"] in drop:
            continue
        j = dict(j)
        j["name"] = pre + j["name"]
        j["deps"] = [pre + d for d in j.get("deps", []) if d in names and d not in drop]
        if cmd_env:
            j["cmd"] = j["cmd"].replace("&& python3", f"&& {cmd_env} python3")
        out.append(j)
    return out


JOBS = []
# ---- existing digital / layout (estimates: the 2026-11-20 smoke run on this machine)
EX = dict(pinout=10, mutations=60, cocotb_macro=300, cocotb_macro_gl=600, cocotb_tt=300, cocotb_tt_gl=600,
          formal_prove=300, formal_gates_bmc=900, formal_mutate=5400, eqy=120, floorplan=10, xschem=600, layout=5400)
for c, est in EX.items():
    j = dict(name=f"ex_{c}", cmd=f"cd {REPO} && bash sim/verify/existing.sh {c}", threads=2 if c == "layout" else 1,
             est=est, prio=1)
    if c.startswith("cocotb") or c == "mutations":
        j["lock"] = "test_dir"                      # one user of test/ (sim_build_*, the generated wrapper) at a time
    JOBS.append(j)
# ---- mixed-signal (its own verdict job dropped: sim/verify/verdict.py runs sim/mixed/verdict.py --mutants)
JOBS += prefixed(load("sim/mixed/jobs.py"), "mx_", drop=("verdict",))
# ---- the existing extracted-tile set, into its own directory
JOBS += prefixed(load("sim/top/jobs_tile.py", {"TILE_SIMS_OUT": TE}), "te_", cmd_env=f"TILE_SIMS_OUT={TE}")
# ---- power grid (needs build/tile/meta.json from the layout step)
pw = prefixed(load("sim/power/jobs.py"), "pw_")
for j in pw:
    if not j["deps"]:
        j["deps"] = ["ex_layout"]
JOBS += pw
# ---- new: tile (gaps 2-6) and extracted blocks (gaps 1, 2, 4, 5)
tv = load("sim/verify/jobs_tile_verify.py", {"TILE_SIMS_OUT": TV, "VERIFY_SET": "full"})
ch = load("sim/verify/jobs_chain.py", {"VERIFY_SET": "full"})
chn = {j["name"] for j in ch}
JOBS += [j for j in tv if j["name"] not in chn]          # coupling_budget is in both: keep the chain file's
for j in ch:
    if j["name"] == "bbrec_tt_txrx":
        j["deps"] = j["deps"] + ["txrx_c_tt"]            # the TX -> RX recovery starts from the tile run's state
    JOBS.append(j)
names = [j["name"] for j in JOBS]
assert len(names) == len(set(names)), "duplicate job names"


if __name__ == "__main__":
    import collections
    cpu = sum(j["est"] * j.get("threads", 1) for j in JOBS) / 3600
    by = collections.defaultdict(float)
    for j in JOBS:
        k = j["name"].split("_")[0] if j["name"][:3] in ("ex_", "mx_", "te_", "pw_") else (
            "gap1_mc" if j["name"].startswith("mc_") else j["name"].split("_")[0])
        by[k] += j["est"] * j.get("threads", 1) / 3600
    print(f"{len(JOBS)} jobs, {cpu:.0f} CPU-hours")
    for k, v in sorted(by.items(), key=lambda kv: -kv[1]):
        print(f"  {k:12s} {v:7.1f} CPU-h")
    longest = max(JOBS, key=lambda j: j["est"])
    print(f"longest single job {longest['name']} {longest['est'] / 3600:.1f} h")
    for b in (28, 30):
        print(f"budget {b}: >= {max(cpu / b, longest['est'] / 3600):.1f} h wall (CPU-bound lower limit)")

# 2026-11-25: the first ex_layout failed (exit 0, RESULT FAIL: tt-support-tools missing on the new pod) and the
# scheduler counted it OK; renamed so it runs again, and the power-grid jobs wait for the new one
for j in JOBS:
    if j["name"] == "ex_layout":
        j["name"] = "ex_layout_r2"
    j["deps"] = ["ex_layout_r2" if d == "ex_layout" else d for d in j.get("deps", [])]

# 2026-11-25: coupling_budget reads the settled -95 dBm tt RX result; on a fresh pod only this run's own copy exists
for j in JOBS:
    if j["name"] == "coupling_budget":
        j["deps"] = j.get("deps", []) + ["te_rxs_c_tt_-95_p"]
        j["cmd"] += "  # 2026-11-25: after te_rxs_c_tt_-95_p"

# 2026-11-21: the scheduler process keeps its first import of tile_verify, so the packet's new thread count
# (tile_verify.py: 8 -> 3) is set here too, for the running scheduler's reload
for j in JOBS:
    if j["name"] == "fsk_c_tt_-95_n16":
        j["threads"], j["est"] = 3, 412 * 470
