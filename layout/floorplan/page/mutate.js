// Mutation tests for the rule checks: break a copy of a variant in a known way and require the matching rule to
// get worse (pass -> warn/fail, or warn -> fail), and the untouched variant to stay as it was.
//   node layout/floorplan/page/mutate.js [variants.json] [variant id]
// Exit code 1 if any mutation is not caught.
const fs = require('fs'), path = require('path');
require('./engine.js');
const FP = globalThis.FP;
const dir = path.join(__dirname, '..');
const data = { tile: JSON.parse(fs.readFileSync(path.join(dir, 'tile.json'))), cells: JSON.parse(fs.readFileSync(path.join(dir, 'blocks.json'))) };
const cat = FP.buildCatalog(data);
const j = JSON.parse(fs.readFileSync(process.argv[2] || path.join(dir, 'variants.json')));
// each mutation starts from the first variant (the named one first) in which its rule does not already fail
const named = j.variants.find(v => v.id === process.argv[3]);
const pool = (named ? [named] : []).concat(j.variants.filter(v => v !== named && v.rx === 'cells'));
const clone = o => JSON.parse(JSON.stringify(o));
const RANK = { pass: 0, info: 0, warn: 1, fail: 2 };
const st = (v, rule) => { const c = FP.evaluate(data, cat, v).checks.find(q => q.rule === rule); return c ? [c.status, c.value, c.detail] : ['-', '-', '']; };
const lna = v => (v.rx === 'cells' ? 'rx.lna' : 'xrx');
const MUT = [
  ['LNA moved away from ua[4] / ua[5] (+300 µm in x)', 3, v => { v.place[lna(v)].x += 300; }],
  ['a2 the long way: the Q level shifter (or rx_top) moved 250 µm away', 2, v => { if (v.rx === 'cells') { v.place['rx.lsq'].x += 250; v.place['rx.lsq'].y += 150; } else v.place.xrx.x += 250; }],
  ['two blocks overlapped (mdac onto vco_top)', 9, v => { v.place.xmdac = Object.assign({}, v.place.xvco); }],
  ['a block pushed outside the tile', 9, v => { v.place.xvpd.x = data.tile.w - 5; }],
  ['the macro next to the LNA', 1, v => { const l = FP.resolve(cat, v).inst[lna(v)].rect; v.place.xmac = { x: l[0] + l[2] + 6, y: 3, orient: 'R0' }; }],
  ['a VAPWR stripe moved onto the macro, off its straps', 10, v => { const m = FP.resolve(cat, v).inst.xmac.rect; v.straps.push({ net: 'VAPWR', x: m[0] + m[2] / 2 + 7.3, w: 2 }); }],
  ['every VAPWR stripe renamed VDPWR', 5, v => { v.straps.forEach(s => { if (s.net === 'VAPWR') s.net = 'VDPWR'; }); }],
  ['tx_drv moved 300 µm from ua[2] / ua[3]', 4, v => { v.place.xtxd.x = 600; v.place.xtxd.y = 200; }],
  ['mdac moved to the far corner from the macro', 7, v => { const m = FP.resolve(cat, v).inst.xmac.rect; v.place.xmdac = { x: m[0] > 300 ? 3 : 530, y: 3, orient: 'R0' }; }],
  ['the macro dropped to the bottom (far from the top edge)', 8, v => { v.place.xmac.y = 3; }],
  ['ck routed straight through the largest receiver block (macro above it, vco_top below it)', 6, v => {
    const R = FP.resolve(cat, v), big = Object.values(R.inst).filter(i => i.cat.group === 'rx').sort((a, b) => b.rect[2] * b.rect[3] - a.rect[2] * a.rect[3])[0].rect;
    const cx = big[0] + big[2] / 2, mck = cat.xmac.pins.ck, vck = cat.xvco.pins.ck;
    v.est = {}; v.place.xmac = { x: cx - mck.x, y: big[1] + big[3] + 10, orient: 'R0' };   // ck on its south edge
    v.place.xvco = { x: cx - vck.x, y: big[1] - 80, orient: 'R0' };                         // ck on its north edge
  }, 'ck over'],
  ['vco_top split: cgm_ref moved 200 µm from the ring', 11, v => { v.place['vco.ref'].y += 150; v.place['vco.ref'].x -= 50; }],
];
let bad = 0;
for (const [what, rule, f, expect] of MUT) {
  const base = pool.find(b => !['fail', '-'].includes(st(b, rule)[0])) || pool[0];
  const v = clone(base), [s0, v0] = st(base, rule);
  f(v);
  const [s1, v1, d1] = st(v, rule);
  const caught = expect ? s1 === 'fail' && d1.includes(expect) : RANK[s1] > RANK[s0];
  console.log(`${caught ? 'caught ' : 'MISSED '} rule ${String(rule).padEnd(2)} ${s0.padEnd(4)} ${String(v0).padEnd(14)} -> ${s1.padEnd(4)} ${String(v1).padEnd(14)} ${what}  [on ${base.id}]`);
  if (!caught) bad++;
}
process.exitCode = bad ? 1 : 0;
