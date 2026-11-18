"""Learning figure: why the first stage's noise counts in full and later stages' noise is divided by the gain in
front of them (Friis). Two identical-noise stages, the first with a gain of 5.6 (15 dB); noise voltages add in power."""
import os
import numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
BLUE, ORANGE, GREEN, INK, MUTED = '#2a78d6', '#eb6834', '#1baf7a', '#1f1f1e', '#77766f'
plt.rcParams.update({'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False,
                     'axes.edgecolor': MUTED, 'xtick.color': MUTED, 'ytick.color': MUTED,
                     'axes.labelcolor': INK, 'axes.titlecolor': INK})
sig, n1, n2, G = 10.0, 1.0, 1.0, 5.6
fig, ax = plt.subplots(1, 2, figsize=(13, 5.4), gridspec_kw=dict(wspace=0.35))
def bars(a, vals, title, note):
    labels = ['signal', 'stage 1\'s noise', 'stage 2\'s noise']
    cols = [BLUE, ORANGE, GREEN]
    b = a.bar(labels, vals, color=cols, width=0.6, edgecolor='white', lw=2)
    for r, v in zip(b, vals):
        a.text(r.get_x() + r.get_width() / 2, v + max(vals) * 0.02, f'{v:.2g}', ha='center', va='bottom', fontsize=12, color=INK)
    a.set_title(title, loc='left', fontweight='bold'); a.set_ylabel('size (arbitrary units)')
    a.text(0.98, 0.95, note, transform=a.transAxes, ha='right', va='top', fontsize=10.5, color=INK)
    a.set_ylim(0, max(vals) * 1.18)
bars(ax[0], [sig * G, n1 * G, n2], 'Where stage 2 adds its noise (after ×5.6)',
     'signal and stage 1\'s noise\nhave both been amplified ×5.6;\nstage 2\'s own noise has not')
bars(ax[1], [sig, n1, n2 / G], 'The same, referred back to the input (÷5.6)',
     f'stage 2\'s noise looks 5.6× smaller:\n1 / 5.6 = {n2 / G:.2f}\n\ntotal noise √(1² + 0.18²) = {np.hypot(n1, n2 / G):.3f}\n'
     '→ stage 2 adds only 1.6 %')
fig.suptitle('Friis: noise added after a gain stage is divided by that gain (two stages with equal noise, stage 1 gain 5.6 = 15 dB)',
             x=0.06, ha='left', fontsize=12.5, fontweight='bold', color=INK)
fig.savefig(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'docs', 'img', 'learning', 'friis.png'),
            dpi=150, bbox_inches='tight', facecolor='white')
