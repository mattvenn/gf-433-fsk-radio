import numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
BLUE, ORANGE, INK, MUTED = '#2a78d6', '#eb6834', '#1f1f1e', '#77766f'
plt.rcParams.update({'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.edgecolor': MUTED, 'xtick.color': MUTED, 'ytick.color': MUTED,
                     'axes.labelcolor': INK, 'axes.titlecolor': INK})
fl = 20.0
t = np.linspace(0, 1, 40001)
n = int(len(t)/fl); k = np.ones(n)/n
def avg(x): return np.convolve(np.concatenate([x[-n:], x, x[:n]]), k, mode='same')[n:-n]
def sq(ph): s = np.sign(np.cos(2*np.pi*fl*t - ph)); s[s == 0] = 1; return s
fig = plt.figure(figsize=(13, 7.5))
gs = fig.add_gridspec(2, 2, width_ratios=[2.3, 1], hspace=0.5, wspace=0.18)
for row, (fr, name) in enumerate(((21.0, 'a "1": RF 100 kHz ABOVE the LO (drawn as 21 vs 20 cycles)'),
                                  (19.0, 'a "0": RF 100 kHz BELOW the LO (drawn as 19 vs 20 cycles)'))):
    rf = np.cos(2*np.pi*fr*t)
    i = avg(rf*sq(0)); q = avg(rf*sq(-np.pi/2))
    a = fig.add_subplot(gs[row, 0])
    a.plot(t, i, color=BLUE, lw=2.4, label='I (LO)')
    a.plot(t, q, color=ORANGE, lw=2.4, label='Q (LO shifted a quarter cycle)')
    a.axhline(0, color=MUTED, lw=0.6); a.set_ylim(-0.9, 0.9)
    a.set_title(name, loc='left')
    ang = np.unwrap(np.arctan2(q, i)); assert (ang[-1] - ang[0] > 0) == (fr > fl)
    a.text(0.995, 0.97, 'Q is ' + ('a quarter cycle BEHIND I' if fr > fl else 'a quarter cycle AHEAD of I'),
           transform=a.transAxes, ha='right', va='top', color=INK, fontsize=10)
    if row == 1: a.set_xlabel('time (one difference-frequency cycle = 10 µs on chip)')
    b = fig.add_subplot(gs[row, 1]); b.set_aspect('equal')
    b.plot(i, q, color=INK, lw=1.0, alpha=0.35)
    idx = np.linspace(0, len(t)-1, 9).astype(int)[:-1]
    for j in range(len(idx)):
        s, e = idx[j], idx[j] + 1500
        b.annotate('', xy=(i[e], q[e]), xytext=(i[s], q[s]),
                   arrowprops=dict(arrowstyle='-|>', color=INK, lw=1.6, mutation_scale=16))
    b.plot([i[0]], [q[0]], 'o', ms=8, color=INK, mec='white', mew=2)
    b.axhline(0, color=MUTED, lw=0.6); b.axvline(0, color=MUTED, lw=0.6)
    b.set_xlim(-0.85, 0.85); b.set_ylim(-0.85, 0.85); b.set_xlabel('I'); b.set_ylabel('Q')
    b.set_title('I against Q: ' + ('anticlockwise' if fr > fl else 'clockwise'), loc='left')
fig.legend(*fig.axes[0].get_legend_handles_labels(), loc='upper left', bbox_to_anchor=(0.06, 0.965), frameon=False, ncol=2, fontsize=10)
fig.suptitle('Same speed, opposite direction: why the receiver needs both I and Q',
             x=0.06, y=1.0, ha='left', fontsize=13, fontweight='bold', color=INK)
import os; fig.savefig(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'docs', 'img', 'learning', 'iq_direction.png'), dpi=150, bbox_inches='tight', facecolor='white')
