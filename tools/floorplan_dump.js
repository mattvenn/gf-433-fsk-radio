// node tools/floorplan_dump.js [variants.json | floorplan.json] [variant id or name] -> JSON for floorplan_draw.py:
// placed rects, zones, pins, nets (with their L routes), decaps, stripes, the top channel and the checks.
const path = require('path'), fs = require('fs');
const dir = path.resolve(__dirname, '../layout/floorplan');
require(path.join(dir, 'page/engine.js'));
const FP = globalThis.FP;
const data = { tile: JSON.parse(fs.readFileSync(path.join(dir, 'tile.json'))), cells: JSON.parse(fs.readFileSync(path.join(dir, 'blocks.json'))) };
const cat = FP.buildCatalog(data);
const j = JSON.parse(fs.readFileSync(process.argv[2] || path.join(dir, 'variants.json')));
const sel = process.argv[3];
const v = j.blocks ? FP.importJSON(cat, j) : (j.variants.find(q => q.id === sel || q.name === sel) || j.variants[0]);
const ev = FP.evaluate(data, cat, v, j.settings), R = ev.R;
const out = { name: v.name, tile: data.tile, inst: {}, decaps: R.decaps.map(d => ({ name: d.name, net: d.def.net, rect: d.rect })),
  reserved: R.reserved.map(r => ({ label: r.label, rect: r.rect })), straps: v.straps || [], channel: ev.channelShapes,
  nets: ev.nets.filter(n => !n.missing).map(n => ({ name: n.name, cls: n.cls, pa: n.pa, pb: n.pb, segs: n.segs, len: n.len })),
  checks: ev.checks.map(c => [c.rule, c.title, c.status, c.value]) };
for (const [n, i] of Object.entries(R.inst)) out.inst[n] = { rect: i.rect, halo: i.halo, orient: i.pl.orient, label: i.cat.label || i.cat.cell, supply: i.supply, group: i.cat.group, zones: i.zones,
  pins: Object.fromEntries(Object.entries(i.pins).filter(([k]) => !/^(VDD|VSS|VDD_LS)$/.test(k)).map(([k, p]) => [k, [p.at[0], p.at[1], !!p.est]])) };
console.log(JSON.stringify(out));
