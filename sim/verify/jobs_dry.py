"""The full-run driver's own test (DRY=1 bash sim/verify/full_run.sh): two trivial jobs, one depending on the other."""
JOBS = [dict(name="dry_a", cmd="echo a", threads=1, est=1),
        dict(name="dry_b", cmd="echo b", threads=1, est=1, deps=["dry_a"])]
