import numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
BLUE, ORANGE, INK, MUTED = '#2a78d6', '#eb6834', '#1f1f1e', '#77766f'
plt.rcParams.update({'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.edgecolor': MUTED, 'xtick.color': MUTED, 'ytick.color': MUTED,
                     'axes.labelcolor': INK, 'axes.titlecolor': INK})
fl, fr = 20.0, 21.0                       # LO 20 cycles, RF 21 cycles: the difference is 1 cycle
t = np.linspace(0, 1, 40001)
rf = np.cos(2*np.pi*fr*t)
lo = np.sign(np.cos(2*np.pi*fl*t)); lo[lo == 0] = 1
out = rf*lo
n = int(len(t)/fl)                         # average over one LO cycle (the filter)
k = np.ones(n)/n; avg = np.convolve(np.concatenate([out[-n:], out, out[:n]]), k, mode='same')[n:-n]   # periodic: no edge droop
fig, ax = plt.subplots(4, 1, figsize=(12, 9), sharex=True, gridspec_kw=dict(hspace=0.55))
ax[0].plot(t, rf, color=BLUE, lw=1.6); ax[0].set_title('1. RF: the incoming signal (21 cycles)', loc='left')
ax[1].plot(t, lo, color=ORANGE, lw=1.6); ax[1].set_title('2. LO as a switch: +1 = straight through (S1, S2), −1 = crossed over (S3, S4)  (20 cycles)', loc='left')
ax[1].set_yticks([-1, 1])
ax[2].plot(t, out, color=BLUE, lw=1.2); ax[2].set_title('3. Mixer output = RF × LO: the RF chopped, every other half flipped', loc='left')
ax[3].plot(t, out, color=BLUE, lw=0.8, alpha=0.25)
ax[3].plot(t, avg, color=INK, lw=2.4)
ax[3].set_title('4. After the hold caps and low-pass filter: the average is a slow wave at 21 − 20 = 1 cycle', loc='left')
for x, lab in ((0.0, 'in step:\naverage +'), (0.25, 'a quarter cycle out:\naverage 0'), (0.5, 'opposite:\naverage −'), (0.75, 'a quarter cycle out:\naverage 0')):
    yv = np.interp(x, t, avg)
    ax[3].plot([x], [yv], 'o', ms=8, color=INK, mec='white', mew=2, zorder=5)
    ax[3].annotate(lab, (x, yv), xytext=(x + 0.015, 0.95 if yv < 0.3 else -0.95), fontsize=10, color=INK,
                   va='center', arrowprops=dict(arrowstyle='-', color=MUTED, lw=0.8))
for a in ax:
    a.set_ylim(-1.25, 1.25); a.axhline(0, color=MUTED, lw=0.6, zorder=0); a.grid(axis='x', color='#e6e5e0', lw=0.6)
ax[3].set_xlabel('time (one difference-frequency cycle; on chip this is 10 µs)')
fig.suptitle('How chopping mixes: LO 433.92 MHz, RF 434.02 MHz, difference 100 kHz (drawn as 20 and 21 cycles, not to scale)',
             x=0.06, ha='left', fontsize=13, fontweight='bold', color=INK)
import os; fig.savefig(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'docs', 'img', 'learning', 'chopping_mixer.png'), dpi=150, bbox_inches='tight', facecolor='white')
