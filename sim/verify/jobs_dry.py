"""The full-run driver's own test (DRY=1 bash sim/verify/full_run.sh): trivial jobs, one depending on another, and
dry_c (DRY_SLEEP s, default 1) writing a result.json and a raw like a simulation, for the save / restore / disk test."""
import os

D = "build/verify/dry_out/dry_c"
S = os.environ.get("DRY_SLEEP", "1")
JOBS = [dict(name="dry_a", cmd="echo a", threads=1, est=1),
        dict(name="dry_b", cmd="echo b", threads=1, est=1, deps=["dry_a"]),
        dict(name="dry_c", cmd=f"mkdir -p {D} && head -c 1000000 /dev/zero > {D}/out.raw && sleep {S} "
                               f"&& echo '{{\"ok\": 1}}' > {D}/result.json", threads=1, est=2)]
