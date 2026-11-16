// Run the floorplan page's rule checks from the command line:
//   node layout/floorplan/page/check.js [variants.json | floorplan.json] [--current]
// Default: layout/floorplan/variants.json (the variants Claude seeds into the page).
// --current also checks that the "current" variant's blocks sit where tt_wrapper.py puts them (current.json,
// computed with KLayout from the wrapper's own transformations), moved by current.json's x shift onto the VAPWR tile,
// to 0.01 um. Exit code 1 if that fails.
const fs = require('fs');
const path = require('path');
require('./engine.js');
const FP = globalThis.FP;
const dir = path.join(__dirname, '..');
const data = {
  tile: JSON.parse(fs.readFileSync(path.join(dir, 'tile.json'))),
  cells: JSON.parse(fs.readFileSync(path.join(dir, 'blocks.json'))),
};
const cat = FP.buildCatalog(data);
const args = process.argv.slice(2), file = args.find(a => !a.startsWith('--')) || path.join(dir, 'variants.json');
const j = JSON.parse(fs.readFileSync(file));
const variants = j.blocks ? [FP.importJSON(cat, j)] : j.variants;
const mark = { pass: 'ok  ', warn: 'WARN', fail: 'FAIL', info: '  - ' };
let bad = 0;
for (const v of variants) {
  const r = FP.evaluate(data, cat, v, j.settings);
  console.log(`\n== ${v.name}  (receiver: ${r.R.mode})`);
  for (const c of r.checks) console.log(`${mark[c.status]} ${String(c.rule).padEnd(2)} ${c.title.padEnd(38)} ${String(c.value).padEnd(14)} ${c.detail}`);
  const a = r.area, k = x => (x / 1e3).toFixed(1) + 'k';
  console.log(`area: tile ${k(a.tile)}, macro ${k(a.macro)}, receiver ${k(a.rx)}, other blocks ${k(a.other)}, decap ${k(a.decap)}, free ${k(a.free)} µm²`);
  if (args.includes('--current') && v.id === 'current') {
    const cur = JSON.parse(fs.readFileSync(path.join(dir, 'current.json')));
    for (const [n, b] of Object.entries(cur.bbox)) {
      const sh = (cur.shift || {})[n] || 0, i = r.R.inst[n], d = i ? Math.max(...i.rect.map((q, k) => Math.abs(q - (k === 0 ? b[0] + sh : b[k])))) : Infinity;
      console.log(`${d <= 0.01 ? 'ok  ' : 'FAIL'} current ${n.padEnd(6)} engine [${i ? i.rect.map(q => q.toFixed(3)).join(', ') : '-'}] vs tt_wrapper [${b.join(', ')}] shifted ${sh}  max |Δ| ${d.toFixed(4)} µm`);
      if (!(d <= 0.01)) bad++;
    }
  }
}
process.exitCode = bad ? 1 : 0;
