# Razavi-Bench: progress

Matt's aim: answer all 50 questions of Razavi-Bench correctly. As the review sessions reach a circuit, the closely
related questions are tried here and scored the bench's way (0–4 against the golden answer, `evaluation_rubric.md`).

The bench is [github.com/Arcadia-1/razavi-bench](https://github.com/Arcadia-1/razavi-bench) (B. Razavi, "Analog Design
Experiments With AI", Parts 1 and 2, IEEE Solid-State Circuits Magazine). **Its questions, figures and answers may not be
copied or redistributed** (see its LICENSE), so this file keeps only the question IDs, a short topic of our own, and the
scores. To read a question: `git clone https://github.com/Arcadia-1/razavi-bench` and open `tasks/<ID>-*/`.

Score: — = not tried yet; otherwise the best score so far (0–4), with the date. Notes are Matt's own reasoning or what to revisit.

| ID | Topic | Where it shows up in this project | Score | Date | Notes |
|---|---|---|---|---|---|
| part1-001 | intrinsic gain vs L and W | gm·ro; section 19 (gm), long devices in the bias arrays | — | | |
| part1-002 | gm vs overdrive | section 19: gm = 2I/Vov vs √(2βI); what is held constant | 2 | 2026-11-20 | Right conclusion, but no 'why' and no condition (fixed W/L vs fixed current). **Ask again later.** |
| part1-003 | PMOS vs NMOS small-signal model | the receiver's PMOS couplings and loads | — | | |
| part1-004 | I–V sketch of a device connection | diode-connected devices (sections 8, rx_lim) | — | | |
| part1-005 | I–V sketch of a device connection | diode-connected devices, MOS-bipolar pseudo-resistor | — | | |
| part1-006 | can a device act as a current source? | DAC legs, tails, mirrors (sections 8–9) | — | | |
| part1-007 | PMOS common source, source degeneration | — | — | | |
| part1-008 | source follower | — | — | | |
| part1-009 | common gate | — | — | | |
| part1-010 | common gate, source grounded | — | — | | |
| part1-011 | counting poles | Bode slopes (section 17), rx_bb poles | — | | |
| part1-012 | resistive feedback | — | — | | |
| part1-013 | source follower, current-source load | — | — | | |
| part1-014 | CMOS inverter | ring stages, lsdiv, rx_lim output buffers | — | | |
| part1-015 | malformed CMOS inverter | ring stages | — | | |
| part1-016 | common source, diode-connected load | rx_lim comparator loads C3/C4 | 1 | 2026-11-20 | Got the large-signal swing and the inversion; not the stage name or the gain. Talked through: diode load looks like 1/gm2, so gain = −gm1/gm2, set by sizes (then answered the 4× W check: 2×). **Ask again later.** |
| part1-017 | PMOS input, invalid pull-down | — | — | | |
| part1-018 | finding Rout | current-source output resistance | — | | |
| part1-019 | keeping a device in saturation | headroom: DAC legs under vg (section 9) | — | | |
| part1-020 | NMOS cascode gain stage | — | — | | |
| part1-021 | is it a cascode? | — | — | | |
| part1-022 | Miller effect in a cascode | section 18 (Miller effect on the Q tap) | — | | |
| part1-023 | common gate, PMOS load | — | — | | |
| part1-024 | counting poles | Bode slopes (section 17) | — | | |
| part1-025 | series NMOS as a long channel | section 10: the bias reference's 14 × 14 arrays | — | | |
| part1-026 | source follower into common gate | — | — | | |
| part1-027 | inductive output impedance | — | — | | |
| part1-028 | current input, positive feedback | rx_lim comparator C5/C6 (positive feedback) | — | | |
| part1-029 | feedback transimpedance amplifier | — | — | | |
| part1-030 | PMOS current input, feedback | — | — | | |
| part2-001 | ring: fails to oscillate if caps grow? | the VCO ring; section 1 of the notes | — | | |
| part2-002 | ring phase noise vs capacitance | VCO phase noise (docs/pn_results.md) | — | | |
| part2-003 | ring: fails to oscillate if CL grows? | the VCO ring, the a2 load | — | | |
| part2-004 | ring phase noise vs device width | VCO phase noise | — | | |
| part2-005 | resistance into a ring's supply node | current-fed ring: vg node | — | | |
| part2-006 | ring supply-node resistance, critique | current-fed ring: vg node | — | | |
| part2-007 | latch-comparator gain vs device width | rx_lim comparator | — | | |
| part2-008 | latch-comparator gain vs node capacitance | rx_lim comparator | — | | |
| part2-009 | latch speed vs cross-coupled width | rx_lim C5/C6 | — | | |
| part2-010 | clocked latch speed vs clocked widths | lsdiv TSPC | — | | |
| part2-011 | does it give quadrature outputs? | the receiver's 72° I/Q taps (sections 12, 17) | — | | |
| part2-012 | clocked latch speed, another topology | lsdiv TSPC | — | | |
| part2-013 | dynamic latch dividing by two | lsdiv TSPC ÷2 | — | | |
| part2-014 | effect of an added inverter | lsdiv / keeper | — | | |
| part2-015 | keeper inverter critique | lsdiv / keeper | — | | |
| part2-016 | LNA noise figure with Rin = 50 Ω | rx_lna; Friis (section 16) | — | | |
| part2-017 | input impedance | rx_lna input, the pad model | — | | |
| part2-018 | LDO noise to VCO phase noise | VCO supply sensitivity; VAPWR | — | | |
| part2-019 | tail-node capacitance and phase noise | current-fed ring tail (vg decap) | — | | |
| part2-020 | estimating an oscillation frequency | the VCO ring; section 1 | — | | |

**Tally:** 2 of 50 tried, 0 at 4/4.

**To ask again:** part1-002, part1-016.

## Small-signal drills
The shorthand most of the questions lean on. At the start of a session: five quick questions drawn from the list, no
notes, then the score below. Each card is answered in one line; the answers are folded, for self-checking.

1. **gm three ways.** <details><summary>Answer</summary>gm = μC<sub>ox</sub>(W/L)·V<sub>ov</sub> = 2I/V<sub>ov</sub> = √(2μC<sub>ox</sub>(W/L)·I). Which one "applies" depends on what is held fixed (W/L or I).</details>
2. **gm in weak inversion.** <details><summary>Answer</summary>gm ≈ I / (n·kT/q) ≈ I / 34 mV: the most gm per µA, independent of W/L.</details>
3. **Resistance looking into a diode-connected transistor, or into a source.** <details><summary>Answer</summary>About 1/gm.</details>
4. **Resistance looking into a drain.** <details><summary>Answer</summary>r<sub>o</sub> = 1/(λI); with a source resistor R<sub>S</sub>, about r<sub>o</sub>(1 + gm·R<sub>S</sub>).</details>
5. **Intrinsic gain.** <details><summary>Answer</summary>gm·r<sub>o</sub>: the most gain one transistor can give.</details>
6. **Common-source gain** (resistor load, diode load, current-source load). <details><summary>Answer</summary>−gm·(R<sub>D</sub> ∥ r<sub>o</sub>); −gm1/gm2; −gm·(r<sub>o1</sub> ∥ r<sub>o2</sub>).</details>
7. **Source-follower gain and output resistance.** <details><summary>Answer</summary>Gain gm·R/(1 + gm·R), just under 1; output resistance about 1/gm.</details>
8. **Common-gate input resistance and gain.** <details><summary>Answer</summary>Input about 1/gm; gain about +gm·R<sub>D</sub> (non-inverting).</details>
9. **A node's pole.** <details><summary>Answer</summary>f = 1/(2π·R·C), with R and C the total resistance and capacitance at that node; roughly one pole per high-impedance node.</details>
10. **The Miller effect.** <details><summary>Answer</summary>A capacitor C from the input to an output with gain −A looks like C·(1 + A) at the input.</details>
11. **A differential pair's tail limits the output to …** <details><summary>Answer</summary>±I<sub>tail</sub>·R<sub>D</sub> (differential): the whole tail current steered to one side.</details>
12. **gm × R prefixes.** <details><summary>Answer</summary>mS × kΩ is a plain number (8 mS × 1.2 kΩ = 9.6).</details>

| Date | Cards | Score | Slipped on |
|---|---|---|---|
| 2026-11-20 | 3, 10, 9, 11, 6 | 2.5 / 5 | 10: wrote A·C, not C·(1+A); 9: the pole is f = 1/(2πRC); 6: gm × R_D, not ÷ |
| 2026-11-20 (retry) | 10, 9, 6 | 2.5 / 3 | 10: put −10 into C(1 + A); A is the gain's size, so 11 fF. 9 and 6 right (6: remember the minus sign) |
