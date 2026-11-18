import numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
BLUE, ORANGE, INK, MUTED = '#2a78d6', '#eb6834', '#1f1f1e', '#77766f'
plt.rcParams.update({'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.edgecolor': MUTED, 'xtick.color': MUTED, 'ytick.color': MUTED,
                     'axes.labelcolor': INK, 'axes.titlecolor': INK})
ph = np.linspace(0, 720, 4001)                 # degrees of the LO cycle
def sq(delay): return (np.mod(ph - delay, 360) < 180).astype(float)
cases = [('At the ring: a2 lags a0 by 72°', 0, 72),
         ('Matched paths: both delayed by 119° — the gap is still 72°', 119, 72 + 119),
         ('First attempt: I delayed 119°, Q only 55° — the gap shrinks to 72 + 55 − 119 = 8°', 119, 72 + 55)]
fig, ax = plt.subplots(3, 1, figsize=(12, 7.2), sharex=True, gridspec_kw=dict(hspace=0.75))
for a, (title, di, dq) in zip(ax, cases):
    a.plot(ph, sq(di) + 1.4, color=BLUE, lw=2); a.plot(ph, sq(dq), color=ORANGE, lw=2)
    a.text(-8, 1.9, 'I', color=BLUE, ha='right', va='center', fontweight='bold')
    a.text(-8, 0.5, 'Q', color=ORANGE, ha='right', va='center', fontweight='bold')
    e1, e2 = di % 360, dq % 360
    a.annotate('', xy=(e2, 1.2), xytext=(e1, 1.2), arrowprops=dict(arrowstyle='<|-|>', color=INK, lw=1.3, shrinkA=0, shrinkB=0))
    a.text((e1 + e2) / 2, 1.27, f'{(dq - di):.0f}°', ha='center', va='bottom', fontsize=10, color=INK,
           bbox=dict(fc='white', ec='none', pad=0.5))
    for x in (e1, e2): a.axvline(x, color=MUTED, lw=0.6, ls=':')
    a.set_yticks([]); a.spines['left'].set_visible(False); a.set_ylim(-0.2, 2.6); a.set_xlim(-20, 720)
    a.set_title(title, loc='left')
ax[-1].set_xlabel('phase of the LO cycle (degrees; 360° = 2.3 ns at 434 MHz)')
ax[-1].set_xticks(range(0, 721, 90))
fig.suptitle('Only the difference in delay between the I and Q paths matters', x=0.06, ha='left', fontsize=13, fontweight='bold', color=INK)
import os; fig.savefig(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'docs', 'img', 'learning', 'lo_delay.png'), dpi=150, bbox_inches='tight', facecolor='white')
