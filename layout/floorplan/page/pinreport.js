// Write the chosen floorplan for the tile generator and the block re-layouts:
//   node layout/floorplan/page/pinreport.js <variants.json | floorplan.json> [variant id or name]
// -> layout/floorplan/floorplan.json (placements, supplies, stripes, decap, reserved areas, supply crossings)
// -> layout/floorplan/pins.md (per block: placement, and every pin by edge in the block's own frame)
require('./engine.js');
const fs = require('fs'), path = require('path'), FP = globalThis.FP;
const dir = path.join(__dirname, '..');
const data = { tile: JSON.parse(fs.readFileSync(path.join(dir, 'tile.json'))), cells: JSON.parse(fs.readFileSync(path.join(dir, 'blocks.json'))) };
const cat = FP.buildCatalog(data);
const j = JSON.parse(fs.readFileSync(process.argv[2] || path.join(dir, 'variants.json')));
const sel = process.argv[3];
const v = j.blocks ? FP.importJSON(cat, j) : (j.variants.find(q => q.id === sel || q.name === sel) || j.variants[0]);
const r = FP.evaluate(data, cat, v, j.settings), R = r.R;
fs.writeFileSync(path.join(dir, 'floorplan.json'), JSON.stringify(FP.exportJSON(data, cat, v, j.settings), null, 1) + '\n');

const f = (x) => (+x).toFixed(2);
const edgeOf = (x, y, w, h) => { const d = { W: x, E: w - x, S: y, N: h - y }; return Object.entries(d).sort((a, b) => a[1] - b[1])[0][0]; };
const SIDE_IN_TILE = (ins, e) => {            // which way a block's own edge faces once placed
  const c = [ins.w / 2, ins.h / 2], p = { W: [0, c[1]], E: [ins.w, c[1]], S: [c[0], 0], N: [c[0], ins.h] }[e];
  const a = FP.mapPt(ins.pl, ins.w, ins.h, c[0], c[1]), b = FP.mapPt(ins.pl, ins.w, ins.h, p[0], p[1]);
  const dx = b[0] - a[0], dy = b[1] - a[1];
  return Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? 'east' : 'west') : (dy > 0 ? 'north' : 'south');
};
const out = [];
out.push('# Floorplan: block positions and pin positions');
out.push('');
out.push(`Generated from the floorplan page's variant **${v.name}** by \`layout/floorplan/page/pinreport.js\`; the placements are also in \`floorplan.json\` next to this file. Receiver: ${R.mode === 'cells' ? 'placed as its cells (the brief for an rx_top re-layout)' : 'rx_top as one block'}.`);
out.push('');
out.push('- Coordinates in µm, tile origin at its lower-left. **Placement**: lower-left of the placed (transformed) bbox, and the GDS orientation (KLayout `DCplxTrans(1, rot, mirror, …)`, mirror about x first).');
out.push('- **Pins**: in each block\'s *own* frame (its bbox lower-left = 0, 0, before the orientation), grouped by the block\'s own edge; the tile direction each edge faces after placement is in brackets. "est." = not in the GDS yet (vco_top a2, tx_fine rx_en).');
out.push('');
out.push('## Checks');
out.push('');
out.push('| rule | status | value |'); out.push('|---|---|---|');
for (const c of r.checks) out.push(`| ${c.rule}. ${c.title} | ${c.status} | ${c.value} |`);
out.push('');
for (const ins of Object.values(R.inst)) {
  const n = ins.name, c = ins.cat, [k, m] = FP.ORIENTS[ins.pl.orient];
  out.push(`## ${n} (${c.cell}, ${ins.supply})`);
  out.push('');
  const reshaped = c.reshape && (Math.abs(ins.w - c.w) > 1e-6 || Math.abs(ins.h - c.h) > 1e-6);
  out.push(`- Size: ${f(ins.w)} × ${f(ins.h)}${reshaped ? ` (reshaped from ${c.w} × ${c.h}: re-harden at this size; pin positions scaled)` : c.glue ? ' (standard cells, tt_wrapper.py)' : ' (GDS)'}`);
  out.push(`- Placement: x ${f(ins.rect[0])}, y ${f(ins.rect[1])}, ${ins.pl.orient} (rot ${k * 90}, mirror ${m})`);
  out.push('');
  const groups = {};
  const nMoved = Object.values(ins.pins).filter(q => q.moved).length;
  out.push(`- Pins moved: ${nMoved ? nMoved + ' (marked; a re-layout' + (c.reshape ? ', for the macro a new pin_order.cfg' : '') + ')' : 'none: keeps its layout'}`);
  out.push('');
  for (const [pn, p] of Object.entries(c.pins)) {
    if (n === 'xmac' && /^dac_/.test(pn)) continue;
    if (/^(VDD|VSS|VDD_LS)$/.test(pn)) continue;
    const q = ins.pins[pn], x = q.moved ? q.x : p.x * ins.w / c.w, y = q.moved ? q.y : p.y * ins.h / c.h, e = edgeOf(x, y, ins.w, ins.h);
    const gx = c.pins[pn].x * ins.w / c.w, gy = c.pins[pn].y * ins.h / c.h;
    (groups[e] = groups[e] || []).push([pn, x, y, p.est, q.moved, edgeOf(gx, gy, ins.w, ins.h)]);
  }
  if (n === 'xmac') { const dm = Object.entries(ins.pins).filter(([k, q]) => /^dac_/.test(k) && q.moved).map(([, q]) => q); out.push(dm.length ? `The 37 DAC lines (dac_sdn, dac_bn[0:4], dac_tn[0:30], in that order) **moved**: ${edgeOf(dm[0].x, dm[0].y, ins.w, ins.h)} edge of its own frame, ${f(Math.min(...dm.map(q => edgeOf(q.x, q.y, ins.w, ins.h) === 'E' || edgeOf(q.x, q.y, ins.w, ins.h) === 'W' ? q.y : q.x)))} … ${f(Math.max(...dm.map(q => edgeOf(q.x, q.y, ins.w, ins.h) === 'E' || edgeOf(q.x, q.y, ins.w, ins.h) === 'W' ? q.y : q.x)))} µm along it (the full list is in floorplan.json, pins_moved).\n` : 'The 37 DAC lines (dac_tn[0:30], dac_bn[0:4], dac_sdn) are on its own east edge, y 8.1 … 250.0 (as hardened).\n'); }
  for (const e of ['N', 'S', 'W', 'E']) {
    if (!groups[e]) continue;
    const along = e === 'N' || e === 'S' ? 1 : 2;
    groups[e].sort((a, b) => a[along] - b[along]);
    out.push(`**${e} edge** (faces ${SIDE_IN_TILE(ins, e)} in the tile; ${along === 1 ? 'left → right, x' : 'bottom → top, y'}):`);
    out.push('');
    out.push('| pin | x | y | |'); out.push('|---|---|---|---|');
    for (const [pn, x, y, est, mv, e0] of groups[e]) out.push(`| ${pn} | ${f(x)} | ${f(y)} | ${mv ? `**moved**${e0 !== e ? ` (was ${e0} edge)` : ''}` : est ? 'est. (not in the GDS yet)' : ''} |`);
    out.push('');
  }
}
out.push('## Stripes, decap, reserved areas');
out.push('');
for (const s of v.straps || []) out.push(`- ${s.net} stripe: x ${f(s.x)}, w ${f(s.w)} (Metal4, y 5 … 320.36)`);
for (const [b, rs] of Object.entries(v.decaps || {})) rs.forEach((q, i) => out.push(`- ${FP.DECAPS[b].label} ${i + 1}: x ${f(q.x)}, y ${f(q.y)}, ${f(q.w)} × ${f(q.h)}`));
for (const q of v.reserved || []) out.push(`- reserved (${q.label}): x ${f(q.x)}, y ${f(q.y)}, ${f(q.w)} × ${f(q.h)}`);
out.push('');
out.push('## Supply crossings (VAPWR ↔ VDPWR)');
out.push('');
for (const c of r.crossings.filter(q => q.cls !== 'fine')) out.push(`- ${c.net}: ${c.from} → ${c.to}`);
const dac = r.crossings.filter(q => q.cls === 'fine');
if (dac.length) out.push(`- the ${dac.length} DAC lines: tx_fine (VDPWR) → mdac (VAPWR)`);
out.push('');
fs.writeFileSync(path.join(dir, 'pins.md'), out.join('\n'));
console.log('wrote floorplan.json and pins.md for', v.name);
