import numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
BLUE, ORANGE, INK, MUTED, GREEN = '#2a78d6', '#eb6834', '#1f1f1e', '#77766f', '#1baf7a'
plt.rcParams.update({'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.edgecolor': MUTED, 'xtick.color': MUTED, 'ytick.color': MUTED,
                     'axes.labelcolor': INK, 'axes.titlecolor': INK})
v = np.linspace(-2, 3.3, 600)
vfb, vth, cmin = -0.9, 0.7, 0.28          # illustrative shape only
s1 = 1/(1+np.exp(-(v - (vfb-0.15))/0.12))   # leaving accumulation
s2 = 1/(1+np.exp(-(v - (vth+0.1))/0.10))    # entering inversion
c = 1 - (1-cmin)*s1 + (1-cmin)*s2*s1
fig, ax = plt.subplots(figsize=(11, 5.2))
for a, b, col, lab in ((-2, vfb, BLUE, 'accumulation'), (vfb, vth, MUTED, 'depletion'), (vth, 3.3, GREEN, 'inversion')):
    ax.axvspan(a, b, color=col, alpha=0.07, lw=0)
    ax.text((a+b)/2, 1.12, lab, ha='center', color=INK, fontsize=11, fontweight='bold')
ax.plot(v, c, color=INK, lw=2.4)
ax.set_ylim(0, 1.2); ax.set_xlim(-2, 3.3)
ax.set_xlabel('gate voltage relative to source / drain / body (V)'); ax.set_ylabel('capacitance / Cox')
ax.text(-1.95, 0.80, 'holes pile up\nright under the oxide:\nbottom plate at the surface\n→ full C', fontsize=10, color=INK, va='top')
ax.text(-0.05, 0.62, 'holes pushed away,\nonly fixed ions left:\nthe moving charge is at the\nbottom of a depletion layer,\nfar from the gate → small C', fontsize=10, color=INK, va='top', ha='center')
ax.text(1.2, 0.80, 'electrons from source / drain\nform a channel right under\nthe oxide: bottom plate back\nat the surface → full C', fontsize=10, color=INK, va='top')
ax.annotate('our hold caps: gate at ~2.5 V', xy=(2.5, 1.0), xytext=(2.0, 0.42), fontsize=10.5, color=ORANGE, fontweight='bold',
            arrowprops=dict(arrowstyle='-|>', color=ORANGE, lw=1.4))
ax.plot([2.5], [1.0], 'o', ms=9, color=ORANGE, mec='white', mew=2, zorder=5)
ax.annotate('if the node sat near 0 V', xy=(0.0, cmin+0.005), xytext=(-1.6, 0.12), fontsize=10.5, color=INK,
            arrowprops=dict(arrowstyle='-|>', color=MUTED, lw=1.2))
ax.axvline(vth, color=MUTED, lw=0.8, ls='--'); ax.text(vth+0.04, 0.03, 'Vth', color=MUTED)
ax.set_title('NMOS gate capacitor: capacitance against gate voltage (textbook shape, not simulated)', loc='left', fontweight='bold')
import os; fig.savefig(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'docs', 'img', 'learning', 'mos_cv.png'), dpi=150, bbox_inches='tight', facecolor='white')
