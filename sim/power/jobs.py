"""Scheduler job file for the power-grid IR-drop / EM study (sim/sched.py).

    mkdir -p build/power && nohup setsid python3 sim/sched.py sim/power/jobs.py --budget 14 \
        --out build/power > build/power/sched.log 2>&1 &
    python3 sim/sched.py --status --out build/power
Judge the runs by build/power/res_*/result.json and the log tails, not by exit codes.
"""
import os

REPO = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
C = f"cd {REPO} && "
JOBS = [
    dict(name='pg_rdson', cmd=C + 'python3 sim/power/pg_rdson.py', threads=1, est=10),
    dict(name='mesh_p0.5', cmd=C + 'python3 sim/power/mesh.py 0.5', threads=1, est=20),
    dict(name='mesh_p0.25', cmd=C + 'python3 sim/power/mesh.py 0.25', threads=1, est=60),
    # mutations (the checker must move the right way): the TX ground's single via path cut; the VAPWR stripe
    # over the LNA (x 118.1) narrowed from 2 to 1 um; every sheet R doubled
    dict(name='mesh_mut_via', cmd=C + "MUT=mut_via MUT_CUT='233.0,73.8,234.6,74.5' python3 sim/power/mesh.py 0.5",
         threads=1, est=20),
    dict(name='mesh_mut_narrow', cmd=C + "MUT=mut_narrow MUT_NARROW='118.1:1.0' python3 sim/power/mesh.py 0.5",
         threads=1, est=20),
    dict(name='mesh_mut_rs2', cmd=C + "MUT=mut_rs2 MUT_RS=2 python3 sim/power/mesh.py 0.5", threads=1, est=20),
]
for tag, dep in (('p0.5', 'mesh_p0.5'), ('p0.25', 'mesh_p0.25'), ('p0.5_mut_via', 'mesh_mut_via'),
                 ('p0.5_mut_narrow', 'mesh_mut_narrow'), ('p0.5_mut_rs2', 'mesh_mut_rs2')):
    JOBS.append(dict(name='solve_' + tag, cmd=C + f'python3 sim/power/solve.py {tag}', threads=2, est=120,
                     deps=[dep, 'pg_rdson']))
for rs in ('ss', 'ff'):
    JOBS.append(dict(name='solve_p0.5_' + rs, cmd=C + f'python3 sim/power/solve.py p0.5 {rs}', threads=2, est=60,
                     deps=['mesh_p0.5', 'pg_rdson']))
JOBS.append(dict(name='check_stripe', cmd=C + 'python3 sim/power/check_stripe.py', threads=1, est=10,
                 deps=['mesh_p0.5', 'mesh_p0.25']))
