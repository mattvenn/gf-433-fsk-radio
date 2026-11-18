"""Learning figure: why sqrt(N) appears in processing gain, mismatch (Pelgrom) and flicker noise.
Left: N coherent steps add to N, N random +-1 steps spread as sqrt(N). Right: three Monte Carlo experiments
(quadrature-count noise, a device made of N random unit cells, a channel with N random traps) all give a relative
fluctuation of 1/sqrt(N)."""
import os
import numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
BLUE, ORANGE, GREEN, INK, MUTED = '#2a78d6', '#eb6834', '#1baf7a', '#1f1f1e', '#77766f'
plt.rcParams.update({'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.edgecolor': MUTED, 'xtick.color': MUTED, 'ytick.color': MUTED,
                     'axes.labelcolor': INK, 'axes.titlecolor': INK})
rng = np.random.default_rng(3)
fig, (a, b) = plt.subplots(1, 2, figsize=(14, 6), gridspec_kw=dict(width_ratios=[1.15, 1], wspace=0.25))
# left: coherent vs random sums
N = 400; k = np.arange(1, N + 1)
walks = np.cumsum(rng.choice([-1, 1], size=(60, N)), axis=1)
for w in walks: a.plot(k, w, color=MUTED, lw=0.6, alpha=0.35)
a.plot(k, k, color=BLUE, lw=2.6, label='N coherent steps (all +1): grows as N')
a.plot(k, np.sqrt(k), color=ORANGE, lw=2.4, label='typical size of N random ±1 steps: √N')
a.plot(k, -np.sqrt(k), color=ORANGE, lw=2.4)
a.text(300, -72, '60 random walks', color=MUTED, fontsize=10)
a.annotate('at N = 100:\nsignal 100, noise ≈ 10', xy=(100, 100), xytext=(15, 230), fontsize=10, color=INK,
           arrowprops=dict(arrowstyle='-', color=MUTED))
a.set_xlabel('N (steps, unit cells, traps …)'); a.set_ylabel('sum')
a.set_ylim(-80, 400); a.legend(frameon=False, loc='upper left', fontsize=10)
a.set_title('Things that add in step grow as N; random things grow as √N', loc='left', fontweight='bold')
# right: three Monte Carlo experiments, relative fluctuation vs N
Ns = np.array([4, 16, 64, 256, 1024, 4096]); trials = 4000
def rel(samples): return samples.std() / abs(samples.mean())
proc = [rel(rng.choice([-1, 1], size=(trials, n)).sum(1) + n) for n in Ns]           # signal n + noise walk
mism = [rel(rng.normal(1.0, 0.2, size=(trials, n)).sum(1)) for n in Ns]               # n unit cells, 20 % each
trap = [rel((n * 10 - rng.binomial(n, 0.5, size=trials)).astype(float)) for n in Ns]  # 10 carriers per cell, n traps
ref = 1 / np.sqrt(Ns)
b.loglog(Ns, ref * proc[0] / ref[0], color=INK, lw=1.2, ls='--', label='1 / √N')
for y, c, m, lab in ((proc, BLUE, 'o', 'processing gain: noise / signal of an N-step count'),
                     (mism, ORANGE, 's', 'mismatch: spread of a device made of N unit cells'),
                     (trap, GREEN, '^', 'flicker: current fluctuation of a channel with N traps')):
    b.loglog(Ns, y, m, color=c, ms=9, mec='white', mew=1.5, label=lab)
    b.loglog(Ns, ref * y[0] / ref[0], color=c, lw=1, alpha=0.5)
b.set_ylim(5e-4, 4); b.set_xlabel('N  (bit length, device area, gate area)'); b.set_ylabel('relative fluctuation (σ / mean)')
b.legend(frameon=False, loc='upper right', fontsize=9.5)
b.set_title('Three experiments, one slope: 4× N → ½ the relative error', loc='left', fontweight='bold')
fig.savefig(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'docs', 'img', 'learning', 'sqrt_n.png'),
            dpi=150, bbox_inches='tight', facecolor='white')
for nm, y in (('proc', proc), ('mism', mism), ('trap', trap)):
    print(nm, 'slope', np.polyfit(np.log(Ns), np.log(y), 1)[0].round(3))
