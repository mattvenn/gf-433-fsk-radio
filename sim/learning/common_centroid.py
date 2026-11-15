"""Learning figure: how placement turns a linear gradient into mismatch (side by side, interleaved, common centroid)."""
import os
import numpy as np, matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
BLUE, ORANGE, INK, MUTED = '#2a78d6', '#eb6834', '#1f1f1e', '#77766f'
plt.rcParams.update({'font.size': 11})
val = 1 + 0.01 * np.arange(1, 5)            # the property rises 1 % per slot, left to right
rows = [('Side by side', 'AABB'), ('Interleaved', 'ABAB'), ('Common centroid', 'ABBA')]
fig, ax = plt.subplots(figsize=(11, 5.2)); ax.axis('off'); ax.set_xlim(-3.2, 9.6); ax.set_ylim(-0.6, 4.6)
for k in range(4):                           # gradient strip
    ax.add_patch(Rectangle((k, 3.6), 0.95, 0.5, fc=plt.cm.Greys(0.15 + 0.15 * k), ec='none'))
    ax.text(k + 0.475, 3.85, f'{val[k]:.2f}', ha='center', va='center', fontsize=10, color='white' if k > 1 else INK)
ax.text(-0.15, 3.85, 'gradient:\nvalue at each slot', ha='right', va='center', fontsize=10, color=INK)
for r, (name, pat) in enumerate(rows):
    y = 2.4 - 1.15 * r
    for k, ch in enumerate(pat):
        ax.add_patch(Rectangle((k, y), 0.95, 0.75, fc=BLUE if ch == 'A' else ORANGE, ec='white', lw=2))
        ax.text(k + 0.475, y + 0.375, ch, ha='center', va='center', color='white', fontweight='bold', fontsize=13)
    a = val[[i for i, c in enumerate(pat) if c == 'A']].mean(); b = val[[i for i, c in enumerate(pat) if c == 'B']].mean()
    ca = np.mean([i for i, c in enumerate(pat) if c == 'A']) + 0.475; cb = np.mean([i for i, c in enumerate(pat) if c == 'B']) + 0.475
    if abs(ca - cb) < 1e-9:
        ax.plot([ca - 0.09], [y - 0.12], '^', color=BLUE, ms=9); ax.plot([cb + 0.09], [y - 0.12], '^', color=ORANGE, ms=9)
        ax.text(ca + 0.3, y - 0.2, 'both centroids here', fontsize=9.5, color=INK, va='center')
    else:
        ax.plot([ca], [y - 0.12], '^', color=BLUE, ms=9); ax.plot([cb], [y - 0.12], '^', color=ORANGE, ms=9)
    ax.text(-0.15, y + 0.375, name, ha='right', va='center', fontsize=11.5, fontweight='bold', color=INK)
    ax.text(4.3, y + 0.375, f'A = {a:.3f}   B = {b:.3f}   →   mismatch {abs(b - a) / a * 100:.1f} %',
            va='center', fontsize=11.5, color=INK)
ax.text(4.3, -0.35, '▲ = each device\'s centroid (centre of gravity)', fontsize=10, color=MUTED)
ax.set_title('A linear gradient cancels only when both devices share a centroid', loc='left', fontweight='bold')
fig.savefig(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'docs', 'img', 'learning', 'common_centroid.png'),
            dpi=150, bbox_inches='tight', facecolor='white')
