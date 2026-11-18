"""Learning figure: the three frequency effects of the receiver's Q tap on the ring (tt, code 9, docs/rx_design.md Table II)."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
BLUE, ORANGE, INK, MUTED, GREEN = '#2a78d6', '#eb6834', '#1f1f1e', '#77766f', '#1baf7a'
plt.rcParams.update({'font.size': 11, 'axes.spines.top': False, 'axes.spines.right': False, 'axes.spines.left': False,
                     'axes.edgecolor': MUTED, 'xtick.color': MUTED, 'axes.labelcolor': INK})
f0, fon = 417.16, 409.60            # tt code 9: no RX; Q copy on a2, powered
foff = fon + 0.567                  # Q copy's supply gated (rx_en = 0, option A)
fig, ax = plt.subplots(figsize=(12, 3.6))
pts = [(f0, 'ring alone\n(no receiver)', INK), (fon, 'Q copy on a2,\npowered', BLUE), (foff, 'Q copy unpowered\n(option A, rx_en = 0)', ORANGE)]
for f, lab, c in pts:
    ax.plot([f], [0], 'o', ms=11, color=c, mec='white', mew=2, zorder=5)
for f, lab, c, dy, ha in ((f0, pts[0][1], INK, 0.5, 'center'), (fon, pts[1][1], BLUE, -0.75, 'right'), (foff, pts[2][1], ORANGE, 0.5, 'left')):
    ax.text(f, dy, f'{lab}\n{f:.2f} MHz', ha=ha, va='center', fontsize=10, color=INK)
ax.annotate('', xy=(fon, 1.35), xytext=(f0, 1.35), arrowprops=dict(arrowstyle='-|>', color=BLUE, lw=1.6))
ax.text((f0 + fon) / 2, 1.5, '① adding the Q tap: −7.56 MHz = −1.8 %  (permanent, always there)', ha='center', fontsize=10.5, color=INK)
ax.annotate('', xy=(foff, -1.35), xytext=(fon, -1.35), arrowprops=dict(arrowstyle='-|>', color=ORANGE, lw=1.6))
ax.text(fon + 0.1, -1.6, '② option A: unpowering the copy, +0.57 MHz = 18 fine steps (at every TX/RX switch)', ha='left', fontsize=10.5, color=INK)
ax.text(fon + 0.1, -2.15, '③ option B (copy stays powered): the blue dot does not move, under 7 kHz', ha='left', fontsize=10.5, color=INK)
ax.axhline(0, color=MUTED, lw=0.8, zorder=0)
ax.set_yticks([]); ax.set_ylim(-2.5, 1.9); ax.set_xlim(408.0, 418.6)
ax.set_xlabel('ring frequency (MHz), tt, code 9, schematic ring')
ax.set_title('Three different frequency effects of the receiver\'s Q tap', loc='left', fontweight='bold', color=INK)
import os; fig.savefig(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'docs', 'img', 'learning', 'q_tap_shifts.png'), dpi=150, bbox_inches='tight', facecolor='white')
