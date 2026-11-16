// Pin study: which blocks' pin moves pay off in a given floorplan.
//   node layout/floorplan/page/pinstudy.js [variants.json] <variant id> [--min <um>] [--out <variant id>]
// Starts from the variant's placement with every pin where its GDS has it (estimated pins, which have no GDS
// position yet, and the macro's re-harden pins keep the variant's positions). Then, block by block, fits only that
// block's pins (FP.fitPins) and reports what each moved pin saves: wire length, wires routed round the receiver,
// and pins that face away from what they connect to (the wire has to wrap round its own block). Blocks are ranked
// by weighted saving. --out writes a new variant with the moves of every block above --min (default 30 um).
const fs = require('fs'), path = require('path');
require('./engine.js');
const FP = globalThis.FP;
const dir = path.join(__dirname, '..');
const data = { tile: JSON.parse(fs.readFileSync(path.join(dir, 'tile.json'))), cells: JSON.parse(fs.readFileSync(path.join(dir, 'blocks.json'))) };
const cat = FP.buildCatalog(data);
const args = process.argv.slice(2), file = args.find(a => a.endsWith('.json')) || path.join(dir, 'variants.json');
const id = args.filter(a => !a.endsWith('.json') && !a.startsWith('--'))[0];
const opt = (k, d) => args.includes(k) ? args[args.indexOf(k) + 1] : d;
const MIN = +opt('--min', 30), OUT = opt('--out', null);
const j = JSON.parse(fs.readFileSync(file));
const src = j.variants.find(v => v.id === id);
if (!src) { console.error('no variant', id); process.exit(1); }
const clone = o => JSON.parse(JSON.stringify(o));

// how much a wire matters: the LO, RF and bias wires most; the static enables least
const W = { lo: 4, rfin: 4, rx: 2, ana: 2, fine: 0.3, clk: 1, dig: 0.5, en: 0.3, tx: 2, rxout: 0.3, dbg: 0.5 };
const NETW = { a2: 10, 'ls rx': 4, 'ls tx': 2, 'vbnf ref': 6, 'vctrl ring': 4, vg: 4, vbnf: 3 };
const wOf = n => NETW[n.name] !== undefined ? NETW[n.name] : W[n.cls] || 1;

// base: GDS pins, except the macro's (its pin order is redone at the re-harden anyway) and the debug switches'
// (an estimated cell)
const base = clone(src);
base.pins = {};
for (const [n, ps] of Object.entries(src.pins || {})) if (n === 'xmac' || n.startsWith('xdbg_')) base.pins[n] = ps;
const ev = v => FP.evaluate(data, cat, v);
const R0 = FP.resolve(cat, base), E0 = ev(base);

// a pin "faces away" when its wire's first segment runs back across its own block
function facesAway(R, n, ref) {
  const own = ref.slice(0, ref.lastIndexOf('.')), i = R.inst[own];
  if (!i || !n.segs) return false;
  const p = ref === n.a ? n.pa : n.pb, other = ref === n.a ? n.pb : n.pa, r = i.rect;
  const inside = (x, y) => x > r[0] + 0.5 && x < r[0] + r[2] - 0.5 && y > r[1] + 0.5 && y < r[1] + r[3] - 0.5;
  // sample the route: does it pass through the interior of its own block?
  const segs = n.segs;
  for (const s of segs) for (let t = 0.1; t < 1; t += 0.1) { const x = s[0] + (s[2] - s[0]) * t, y = s[1] + (s[3] - s[1]) * t; if (inside(x, y)) return true; }
  return false && p && other;
}
const awkward = [];
for (const n of E0.nets) {
  if (n.missing) continue;
  for (const ref of [n.a, n.b]) if (!ref.startsWith('pad:') && facesAway(E0.R, n, ref)) awkward.push(`${n.name} (${ref})`);
}

const blocks = Object.keys(R0.inst).filter(n => n !== 'xmac' && !n.startsWith('xdbg_') && !cat[n].glue);
const rows = [];
for (const b of blocks) {
  const v = clone(base);
  v.pins = FP.fitPins(data, cat, v, [b]);
  const E1 = ev(v);
  const mine = E1.nets.filter(n => !n.missing && [n.a, n.b].some(r => r.startsWith(b + '.')));
  let gain = 0, wgain = 0;
  const per = [];
  for (const n1 of mine) {
    const n0 = E0.nets.find(q => q.name === n1.name);
    if (!n0 || n0.missing) continue;
    const d = n0.len - n1.len;
    gain += d; wgain += d * wOf(n1);
    if (Math.abs(d) >= 5) per.push(`${n1.name} ${n0.len.toFixed(0)}→${n1.len.toFixed(0)}`);
  }
  const det0 = E0.nets.filter(n => n.detour !== undefined && mine.some(m => m.name === n.name)).length;
  const det1 = E1.nets.filter(n => n.detour !== undefined && mine.some(m => m.name === n.name)).length;
  const moved = Object.keys((v.pins || {})[b] || {}).length;
  rows.push({ b, cell: cat[b].cell, moved, gain, wgain, per, det: `${det0}→${det1}`, pins: v.pins[b] });
}
rows.sort((p, q) => q.wgain - p.wgain);
console.log(`== ${src.name}: pins where the GDS has them (macro and debug switches as in the variant)`);
console.log(E0.checks.filter(c => typeof c.rule === 'number').map(c => `${c.rule}:${c.status[0].toUpperCase()}`).join(' '));
console.log(`wires that run back across their own block (pin facing away): ${awkward.length ? awkward.join(', ') : 'none'}`);
console.log('\nblock          cell                      pins  saves(µm)  weighted  routed-round  biggest changes');
for (const r of rows) console.log(`${r.b.padEnd(14)} ${String(r.cell).padEnd(25)} ${String(r.moved).padStart(4)}  ${r.gain.toFixed(0).padStart(9)}  ${r.wgain.toFixed(0).padStart(8)}  ${r.det.padStart(12)}  ${r.per.join(', ')}`);
if (OUT) {
  const v = clone(base), pick = rows.filter(r => r.gain >= MIN).map(r => r.b);
  v.pins = FP.fitPins(data, cat, v, pick);
  for (const [n, ps] of Object.entries(base.pins)) v.pins[n] = ps;
  v.id = OUT; v.name = `${src.name}: pins moved on ${pick.length} blocks`; v.order = (src.order || 0) + 0.05;
  v.note = `${src.name} with the pins where the GDS has them, except on the blocks where moving them saves ≥ ${MIN} µm of wire (layout/floorplan/page/pinstudy.js): ${pick.join(', ')}. Every other block keeps its layout.`;
  const E2 = ev(v);
  console.log(`\n${OUT}: moves on ${pick.join(', ')}\n` + E2.checks.filter(c => typeof c.rule === 'number').map(c => `${c.rule}:${c.status[0].toUpperCase()} ${c.value}`).join(' | '));
  j.variants = j.variants.filter(q => q.id !== OUT).concat([v]);
  fs.writeFileSync(file, JSON.stringify(j, null, 1) + '\n');
}
