"""Scheduler job file (sim/sched.py) for the extracted-block receiver runs (sim/verify/chain_x.py, coupling.py,
mc_report.py): gap 1 (Monte Carlo), gap 2 (BER statistics), gap 4 (overload, +6 dBm rating, recovery), gap 5 (budget).

    VERIFY_SET=smoke|full (default full)
    mkdir -p build/verify/chain && VERIFY_SET=smoke nohup setsid python3 sim/sched.py sim/verify/jobs_chain.py \
        --budget 8 --out build/verify/chain > build/verify/chain/sched.log 2>&1 &
Every job is one single-threaded ngspice at a time. The 'sch' jobs are the schematic with unit instances: an extra
for statistics, never the only evidence. Estimates from the smoke run (sim/verify/estimates.json) + 10 %.
The TX -> RX recovery (bbrec_tt_txrx) needs the tile run txrx_c_tt (sim/verify/jobs_tile_verify.py): in the full run
both job files are joined by sim/verify/jobs_full.py, which adds that dependency.
"""
import json
import os

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SET = os.environ.get("VERIFY_SET", "full")
X = f"cd {REPO} && python3 sim/verify/chain_x.py "
try:
    EST = json.load(open(os.path.join(REPO, "sim/verify/estimates.json")))
except (OSError, ValueError):
    EST = {}
JOBS = []


RERUN = {"ovl1_tt_-95": 1, "ovl1_tt_-10": 1, "ovl1_tt_0": 1, "ovl1_tt_6": 1, "coupling_budget": 1, "rate_tt_6": 1,
         "rate_tt_6_vdd4.5": 1}   # bump: re-run a failed job


def job(name, cmd, est, deps=(), threads=1, prio=0):
    cmd += f"  # rerun {RERUN[name]}" if name in RERUN else ""
    JOBS.append(dict(name=name, cmd=cmd, threads=threads, est=int(EST.get(name, est / 1.1) * 1.1), deps=list(deps),
                     prio=prio))


CN = dict(typical="tt", ss="ss", ff="ff")
# ---- gap 1: Monte Carlo (extracted blocks; mismatch off and one merged device as the mutations)
if SET == "smoke":
    MC = dict(typical=20, ss=10, ff=10)
    NMERGE, NSCH = 10, 10
else:
    MC = dict(typical=200, ss=100, ff=100)
    NMERGE, NSCH = 20, 100
mcjobs = []
for corner, n in MC.items():
    for s in range(1, n + 1):
        nm = f"mc_pex_{CN[corner]}_s{s}"
        job(nm, X + f"mc --kind pex --corner {corner} --seed {s}; exit 0", 270, prio=1)
        mcjobs.append(nm)
    for s in ((1, 2) if corner == "typical" else (1,)):      # tt: two seeds, which must give the same numbers
        nm = f"mc_pex_{CN[corner]}_s{s}_mmoff"
        job(nm, X + f"mc --kind pex --corner {corner} --seed {s} --mut mmoff", 270, prio=1)
        mcjobs.append(nm)
for s in range(1, NMERGE + 1):
    nm = f"mc_pex_tt_s{s}_merge"
    job(nm, X + f"mc --kind pex --seed {s} --mut merge; exit 0", 270, prio=1)
    mcjobs.append(nm)
for s in range(1, NSCH + 1):
    nm = f"mc_sch_tt_s{s}"
    job(nm, X + f"mc --kind sch --seed {s}; exit 0", 250)
    mcjobs.append(nm)
job("mc_report", f"cd {REPO} && python3 sim/verify/mc_report.py", 900 if SET == "smoke" else 3600, deps=mcjobs,
    threads=8)

# ---- gap 2: bit errors with noise, extracted chain (ideal LO), against the model's BER (statistics)
fskjobs = []
if SET == "smoke":
    FSK = [(-114, 7.3, s, None) for s in (1, 2, 3)] + [(-114, 0.0, s, "nf0") for s in (1, 2, 3)] \
        + [(-105, 7.3, 1, None), (-105, 27.3, 1, "nfx10")]
else:
    FSK = [(lv, 7.3, s, None) for lv in (-105, -108, -110, -112, -114) for s in range(1, 9)] \
        + [(-114, 0.0, s, "nf0") for s in range(1, 5)] + [(-105, 27.3, s, "nfx10") for s in (1, 2)]
for lv, nf, s, mut in FSK:
    nm = f"fsk_pex_tt_{lv}_n8_nf{nf:g}_s{s}"
    job(nm, X + f"fsk --level {lv} --nf {nf} --seed {s} --ndata 8; exit 0", 16000)
    fskjobs.append(nm)
if SET != "smoke":                                  # noiseless 16 bits through the extracted chain (gap 6 extra)
    for lv in (-70, -95):
        nm = f"fsk_pex_tt_{lv}_n16"
        job(nm, X + f"fsk --level {lv} --ndata 16", 26000)

# ---- gap 4: overload phase 1 (RF chain, 12 us of the burst), rating, phase 2 (baseband: 1 ms burst, 2.5 ms FSK)
for lv in (-95, -10, 0, 6):
    job(f"ovl1_tt_{lv}", X + f"ovl1 --level {lv}", 900, prio=1)
for lv in (6,) if SET == "smoke" else (-10, 0, 6):
    job(f"rate_tt_{lv}", X + f"rate --level {lv}", 300, prio=2)
job("rate_tt_6_vdd4.5", X + "rate --level 6 --vdd 4.5", 300, prio=2)        # mutation: the checker must flag it
for lv in (-10, 0, 6):
    job(f"bbrec_tt_{lv}_1ms", X + f"bbrec --src ovl1_tt_{lv} --tburst 1e-3", 1800, deps=[f"ovl1_tt_{lv}", "ovl1_tt_-95"],
        prio=2)
job("bbrec_tt_-10_0.1ms", X + "bbrec --src ovl1_tt_-10 --tburst 1e-4", 1800, deps=["ovl1_tt_-10", "ovl1_tt_-95"],
    prio=2)                                         # a shorter burst: is the 1 ms state saturated?
job("bbrec_tt_-10_1ms_burston", X + "bbrec --src ovl1_tt_-10 --tburst 1e-3 --mut burston", 1800,
    deps=["ovl1_tt_-10", "ovl1_tt_-95"])
job("bbrec_tt_-95_0ms", X + "bbrec --src ovl1_tt_-95 --tburst 0", 1800, deps=["ovl1_tt_-95"], prio=2)   # no burst: reference
if SET != "smoke":                                  # (smoke: run by hand once txrx_c_tt is done)
    job("bbrec_tt_txrx", X + "bbrec --src tile --tstop 2.5e-3", 1800, deps=["ovl1_tt_-95"])

# ---- gap 5: the coupling budget (analysis + its mutation)
job("coupling_budget", f"cd {REPO} && python3 sim/verify/coupling.py", 600, prio=2)
job("coupling_budget_mut", f"cd {REPO} && python3 sim/verify/coupling.py --mut", 600, deps=["coupling_budget"])
