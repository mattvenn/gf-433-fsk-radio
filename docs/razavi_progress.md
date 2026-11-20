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
| part1-016 | common source, diode-connected load | rx_lim comparator loads C3/C4 | — | | |
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

**Tally:** 1 of 50 tried, 0 at 4/4.

**To ask again:** part1-002.
