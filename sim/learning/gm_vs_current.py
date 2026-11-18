"""Learning figure: gm against drain current for three W/L ratios (EKV-style interpolation, illustrative,
not a GF180 simulation). Strong inversion: gm = sqrt(2 k' (W/L) I); weak inversion: gm = I / (n Ut)."""
import os
import numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
BLUE, ORANGE, GREEN, INK, MUTED = '#2a78d6', '#eb6834', '#1baf7a', '#1f1f1e', '#77766f'
plt.rcParams.update({'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.edgecolor': MUTED, 'xtick.color': MUTED, 'ytick.color': MUTED,
                     'axes.labelcolor': INK, 'axes.titlecolor': INK})
n, ut, kp = 1.3, 0.0259, 200e-6            # slope factor, kT/q, k' = mu Cox (A/V^2, illustrative)
I = np.logspace(-7, -2, 400)               # 0.1 uA .. 10 mA
fig, ax = plt.subplots(figsize=(10.5, 6))
for wl, c in ((1, ORANGE), (10, BLUE), (100, GREEN)):
    ispec = 2 * n * kp * wl * ut ** 2      # specific current: the weak / strong boundary
    ic = I / ispec
    gm = I / (n * ut) * (1 - np.exp(-np.sqrt(ic))) / np.sqrt(ic)
    ax.loglog(I * 1e6, gm * 1e3, color=c, lw=2.4, label=f'W/L = {wl}')
    ax.plot([ispec * 1e6], [np.interp(ispec, I, gm) * 1e3], 'o', color=c, ms=7, mec='white', mew=1.5)
ax.loglog(I * 1e6, I / (n * ut) * 1e3, color=INK, lw=1.2, ls='--', label='weak-inversion ceiling, I / 34 mV')
ax.annotate('weak inversion:\ngm ∝ I, W/L hardly matters', xy=(0.3, 0.3e-6 / (n * ut) * 1e3 * 0.95), xytext=(0.13, 0.08),
            fontsize=10, color=INK, arrowprops=dict(arrowstyle='-', color=MUTED))
ax.annotate('strong inversion: gm ∝ √I,\nwider device → more gm\nat the same current', xy=(2500, 8.5), xytext=(150, 60),
            fontsize=10, color=INK, arrowprops=dict(arrowstyle='-', color=MUTED))
for x, lab in ((4, 'baseband\nstage 2 (4 µA)'), (1400, 'LNA side\n(1.4 mA)')):
    ax.axvline(x, color=MUTED, lw=0.8, ls=':'); ax.text(x * 1.1, 0.0035, lab, fontsize=9.5, color=INK)
ax.set_xlabel('drain current (µA)'); ax.set_ylabel('gm (mS)')
ax.set_ylim(2e-3, 400); ax.legend(frameon=False, loc='upper left')
ax.set_title('gm is set by current and W/L (illustrative model; dots mark each size\'s weak/strong boundary)', loc='left', fontsize=11.5, fontweight='bold')
fig.savefig(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'docs', 'img', 'learning', 'gm_vs_current.png'),
            dpi=150, bbox_inches='tight', facecolor='white')
