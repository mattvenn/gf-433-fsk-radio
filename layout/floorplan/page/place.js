// Seed placer for the floorplan variants: anneals the movable blocks of each spec around its fixed anchors (the
// pads, the TT digital pins' channel, whatever the spec pins down), fills the leftover space with decap, picks
// stripe lanes, and writes layout/floorplan/variants.json (which Claude seeds into the page's store).
//   node layout/floorplan/page/place.js [--only <id>]
// The variants are starting points; Matt refines them on the page. "current" is not annealed: it is today's tile
// (layout/floorplan/current.json, from tools/floorplan_current.py) with the largest free rectangle reserved for the
// receiver.
const fs = require('fs');
const path = require('path');
require('./engine.js');
const FP = globalThis.FP;
const dir = path.join(__dirname, '..');
const data = {
  tile: JSON.parse(fs.readFileSync(path.join(dir, 'tile.json'))),
  cells: JSON.parse(fs.readFileSync(path.join(dir, 'blocks.json'))),
};
const CAT = FP.buildCatalog(data), W = data.tile.w, H = data.tile.h, S = FP.DEFAULT_SETTINGS, K = S.keepout;
const ORS = Object.keys(FP.ORIENTS);
const TT_CHAN = [10, H - 14, 330, 14];       // the TT pins' wires along the top edge (x 14.7 ... 320.8)

let seed = 12345;
const rnd = () => ((seed = (seed * 1103515245 + 12345) & 0x7fffffff) / 0x7fffffff);
const gauss = () => Math.sqrt(-2 * Math.log(rnd() + 1e-12)) * Math.cos(2 * Math.PI * rnd());

function geom(n, est, moved) {               // per orientation: placed size and pin offsets from the placed lower-left
  const c = CAT[n], w = est ? est.w : c.w, h = est ? (est.area || c.w * c.h) / est.w : c.h, g = {};
  for (const o of ORS) {
    const pl = { x: 0, y: 0, orient: o }, [pw, ph] = FP.placedSize(o, w, h), pins = {};
    for (const [pn, p] of Object.entries(c.pins)) pins[pn] = moved && moved[pn] ? FP.mapPt(pl, w, h, moved[pn].x, moved[pn].y) : FP.mapPt(pl, w, h, p.x * w / c.w, p.y * h / c.h);
    const zones = {}; for (const [zn, z] of Object.entries(c.zones || {})) zones[zn] = FP.mapRect(pl, w, h, z);
    g[o] = { w: pw, h: ph, pins, zones };
  }
  return g;
}

const WEIGHT = {
  rx_inp: 8, rx_inn: 8, a2: 25, 'ls rx': 6, 'ls tx': 3, lsq: 4, tx_out_n: 3, tx_out_p: 3, vctrl: 0.6, 'vctrl pd': 1.5, vbn: 0.3,
  vg: 4, vbnf: 2, ck: 1, ck_o: 0.3, div16: 0.3, div64: 0.3, div1024: 0.3, rx_en: 0.2, 'rx_en lo_i': 0.1, 'rx_en lo_q': 0.1,
  'vbnf ref': 6, 'vctrl ring': 3, 'VDD_LS decap': 1,
  code: 0.3, bits: 2, en_p: 0.2, en_n: 0.2, q_i: 0.4, q_q: 0.4,
  ri_p: 3, ri_n: 3, rq_p: 3, rq_n: 3, lo_i: 5, lob_i: 5, lo_q: 5, lob_q: 5, bi_p: 2, bi_n: 2, bq_p: 2, bq_n: 2, oi_p: 1, oi_n: 1, oq_p: 1, oq_n: 1,
};
for (let i = 0; i < 37; i++) WEIGHT[i < 31 ? `dac_tn[${i}]` : i < 36 ? `dac_bn[${i - 31}]` : 'dac_sdn'] = 0.4;

function solve(spec, iters) {
  const v0 = { rx: spec.rx, vco: spec.vco };
  const names = Object.keys(CAT).filter(n => FP.inMode(CAT[n], v0) && (spec.fixed[n] || spec.movable.includes(n)));
  const G = {};
  for (const n of names) G[n] = geom(n, (spec.est || {})[n], (spec.pins || {})[n]);
  const st = {}, mov = spec.movable;
  for (const [n, p] of Object.entries(spec.fixed)) st[n] = Object.assign({}, p);
  for (const n of mov) st[n] = spec.start && spec.start[n] ? Object.assign({}, spec.start[n]) : { x: rnd() * (W - 100), y: rnd() * (H - 60), orient: (spec.orients && spec.orients[n] || ORS)[0] };
  const rect = n => { const g = G[n][st[n].orient]; return [st[n].x, st[n].y, g.w, g.h]; };
  const pin = ref => {
    if (ref.startsWith('pad:')) { const p = data.tile.pins[ref.slice(4)]; return [(p.x0 + p.x1) / 2, p.y0 < 1 ? 0 : H]; }
    const i = ref.lastIndexOf('.'), n = ref.slice(0, i), q = G[n][st[n].orient].pins[ref.slice(i + 1)];
    return [st[n].x + q[0], st[n].y + q[1]];
  };
  const own = r => r.startsWith('pad:') ? null : r.slice(0, r.lastIndexOf('.'));
  const placed = r => r.startsWith('pad:') || own(r) in st;
  const list = FP.NETS.concat(spec.rx === 'cells' ? FP.RX_NETS : [], spec.vco === 'parts' ? FP.VCO_NETS : []);
  const nets = list.map(([nm, cls, a, b]) => [nm, cls, FP.resolveRef(a, spec.rx, spec.vco), FP.resolveRef(b, spec.rx, spec.vco)])
    .filter(([nm, , a, b]) => placed(a) && placed(b) && (mov.includes(own(a)) || mov.includes(own(b))));
  const inter = (r, a) => Math.max(0, Math.min(r[0] + r[2], a[0] + a[2]) - Math.max(r[0], a[0])) * Math.max(0, Math.min(r[1] + r[3], a[1] + a[3]) - Math.max(r[1], a[1]));
  const gap = (a, b) => Math.hypot(Math.max(0, b[0] - a[0] - a[2], a[0] - b[0] - b[2]), Math.max(0, b[1] - a[1] - a[3], a[1] - b[1] - b[3]));
  const crosses = (s, r) => {
    const q = [r[0] + 0.6, r[1] + 0.6, r[2] - 1.2, r[3] - 1.2];
    const x0 = Math.min(s[0], s[2]), x1 = Math.max(s[0], s[2]), y0 = Math.min(s[1], s[3]), y1 = Math.max(s[1], s[3]);
    return x0 < q[0] + q[2] && x1 > q[0] && y0 < q[1] + q[3] && y1 > q[1];
  };
  const rxNames = names.filter(n => CAT[n].group === 'rx');
  const lnaOf = () => spec.rx === 'cells' ? rect('rx.lna') : (() => { const z = G.xrx[st.xrx.orient].zones.lna; return [st.xrx.x + z[0], st.xrx.y + z[1], z[2], z[3]]; })();
  function cost() {
    let c = 0;
    const R = {}; for (const n of names) R[n] = rect(n);
    const mac = st.xmac ? [R.xmac[0] - 5, R.xmac[1] - 5, R.xmac[2] + 10, R.xmac[3] + 10] : null;
    for (const n of mov) {
      const r = R[n];
      c += 5000 * (r[2] * r[3] - inter(r, [0, 0, W, H]));
      if (n !== 'xmac') { c += 5000 * inter(r, TT_CHAN); if (mac) c += 5000 * inter(r, mac); }
      for (const k of spec.keepouts || []) c += 5000 * inter(r, k);
      for (const m of names) {
        if (m === n || m === 'xmac' || (mov.includes(m) && mov.indexOf(m) < mov.indexOf(n))) continue;
        c += 5000 * inter(r, [R[m][0] - K, R[m][1] - K, R[m][2] + 2 * K, R[m][3] + 2 * K]);
      }
      if (n === 'xmac') for (const m of names) if (m !== n) c += 5000 * inter(mac, R[m]);
      const z = (spec.zones || {})[n]; if (z) c += 5000 * (r[2] * r[3] - inter(r, z));
    }
    for (const [nm, cls, a, b] of nets) {
      const pa = pin(a), pb = pin(b);
      c += (WEIGHT[nm] === undefined ? 0.5 : WEIGHT[nm]) * (Math.abs(pa[0] - pb[0]) + Math.abs(pa[1] - pb[1]));
      if (['clk', 'dig', 'fine', 'lo', 'en', 'tx'].includes(cls) && rxNames.length) {
        const s1 = [[pa[0], pa[1], pb[0], pa[1]], [pb[0], pa[1], pb[0], pb[1]]], s2 = [[pa[0], pa[1], pa[0], pb[1]], [pa[0], pb[1], pb[0], pb[1]]];
        const hit = segs => rxNames.filter(m => m !== own(a) && m !== own(b)).filter(m => segs.some(s => crosses(s, R[m]))).length;
        c += (cls === 'fine' ? 60 : 150) * Math.min(hit(s1), hit(s2));
      }
    }
    if (mac && rxNames.length) { const d = gap(lnaOf(), R.xmac); c += 40 * Math.max(0, S.r1 + 50 - d); }
    if (spec.extra) c += spec.extra(R, pin);
    return c;
  }
  let cur = cost(), best = Infinity, bestSt = JSON.parse(JSON.stringify(st));
  // polish: start from spec.start, cooler and with smaller steps, no random jumps
  const T0 = spec.start ? (spec.T0 || 60) : 2000, T1 = 0.05, S0 = spec.start ? (spec.sigma || 12) : 80;
  for (let it = 0; it < iters; it++) {
    const t = it / iters, T = T0 * Math.pow(T1 / T0, t), sig = S0 * Math.pow(0.5 / S0, t);
    const n = mov[(rnd() * mov.length) | 0], old = Object.assign({}, st[n]);
    let other = null, oldO = null;
    const r = rnd();
    if (r < 0.1 && !(spec.start && rnd() < 0.7)) { const os = (spec.orients || {})[n] || ORS; st[n].orient = os[(rnd() * os.length) | 0]; }
    else if (r < 0.16 && mov.length > 1) {
      other = mov[(rnd() * mov.length) | 0]; if (other === n) other = null;
      if (other) { oldO = Object.assign({}, st[other]); [st[n].x, st[other].x] = [st[other].x, st[n].x]; [st[n].y, st[other].y] = [st[other].y, st[n].y]; }
    } else if (r < 0.2 && t < 0.5 && !spec.start) { st[n].x = rnd() * (W - 40); st[n].y = rnd() * (H - 40); }
    else { st[n].x += gauss() * sig; st[n].y += gauss() * sig; }
    if (t > 0.85) { st[n].x = Math.round(st[n].x * 2) / 2; st[n].y = Math.round(st[n].y * 2) / 2; }
    const c = cost();
    if (c <= cur || rnd() < Math.exp((cur - c) / T)) {
      cur = c;
      if (t > 0.85 && c < best) { best = c; bestSt = JSON.parse(JSON.stringify(st)); }
    } else { st[n] = old; if (other) st[other] = oldO; }
  }
  return { place: bestSt, cost: best };
}

// Fill free space with decap rectangles (1 um grid, largest first); each takes the supply of its nearest block.
function freeRects(v, extra, minA) {
  const R = FP.resolve(CAT, v), nx = Math.floor(W), ny = Math.floor(H), occ = new Uint8Array(nx * ny);
  const mark = (r, pad) => {
    const x0 = Math.max(0, Math.floor(r[0] - pad)), x1 = Math.min(nx, Math.ceil(r[0] + r[2] + pad));
    const y0 = Math.max(0, Math.floor(r[1] - pad)), y1 = Math.min(ny, Math.ceil(r[1] + r[3] + pad));
    for (let y = y0; y < y1; y++) for (let x = x0; x < x1; x++) occ[y * nx + x] = 1;
  };
  for (const i of Object.values(R.inst)) mark(i.halo || i.rect, i.halo ? 0 : K);
  for (const r of R.reserved) mark(r.rect, 0);
  for (const k of extra || []) mark(k, 0);
  mark([0, 0, W, 3], 0); mark(TT_CHAN, 0); mark([0, H - 3, W, 3], 0);
  const rects = [];
  for (;;) {
    const hgt = new Int32Array(nx); let best = null;
    for (let y = 0; y < ny; y++) {
      for (let x = 0; x < nx; x++) hgt[x] = occ[y * nx + x] ? 0 : hgt[x] + 1;
      const stack = [];
      for (let x = 0; x <= nx; x++) {
        const hh = x < nx ? hgt[x] : 0; let start = x;
        while (stack.length && stack[stack.length - 1][1] >= hh) {
          const [sx, sh] = stack.pop(), w = x - sx;
          if (sh >= 8 && w >= 8 && (!best || w * sh > best[2] * best[3])) best = [sx, y - sh + 1, w, sh];
          start = sx;
        }
        stack.push([start, hh]);
      }
    }
    if (!best || best[2] * best[3] < (minA || 300)) break;
    rects.push(best);
    mark(best, K);
  }
  return rects;
}
function fillDecap(v, extra) {
  const R = FP.resolve(CAT, v), out = { deca: [], decd: [] };
  for (const r of freeRects(v, extra)) {
    let bd = Infinity, sup = 'VAPWR';
    for (const i of Object.values(R.inst)) { const d = FP.rectGap(r, i.rect); if (d < bd) { bd = d; sup = i.supply; } }
    out[sup === 'VDPWR' ? 'decd' : 'deca'].push({ x: r[0], y: r[1], w: r[2], h: r[3] });
  }
  return out;
}

// Stripe lanes: [net, wanted x]; over the macro a stripe must sit on one of its own straps of that net.
function stripes(v, want) {
  const R = FP.resolve(CAT, v), out = [];
  const okAt = (net, x, w) => Object.values(R.inst).every(i => !i.m4.some(r => r[0] < x + w && r[0] + r[2] > x) ||
    i.straps.some(q => q.net === net && q.r[2] < 5 && x >= q.r[0] - 0.05 && x + w <= q.r[0] + q.r[2] + 0.05));
  for (const [net, x0, w0] of want) {
    const w = w0 || 2;
    let bx = null;
    for (let d = 0; d < 80 && bx === null; d += 0.04) for (const x of [x0 + d, x0 - d]) {
      const xr = Math.round(x * 100) / 100;
      if (xr >= 0.5 && xr + w <= W - 0.5 && okAt(net, xr, w) && !out.some(s => xr < s.x + s.w + 1 && xr + w > s.x - 1)) { bx = xr; break; }
    }
    if (bx !== null) out.push({ net, x: bx, w });
  }
  return out;
}
// Stripes for a variant: the macro's own straps, and over every other block wider than 50 um a stripe of its
// supply plus a VGND beside it (one pair per ~60 um of x), each moved to the nearest clear lane.
function autoStripes(v) {
  const R = FP.resolve(CAT, v), want = macroStripes(v), used = [];
  const blocks = Object.values(R.inst).filter(i => i.name !== 'xmac' && i.rect[2] > 50).sort((a, b) => b.rect[2] * b.rect[3] - a.rect[2] * a.rect[3]);
  for (const i of blocks) {
    const x = i.rect[0] + i.rect[2] / 2;
    if (used.some(u => Math.abs(u - x) < 60)) continue;
    used.push(x); want.push([i.supply, +(x - 2.5).toFixed(2)], ['VGND', +(x + 0.5).toFixed(2)]);
  }
  for (const net of ['VAPWR', 'VDPWR']) {         // every rail in use gets at least one stripe, over its largest block
    if (want.some(q => q[0] === net)) continue;
    const i = blocks.find(q => q.supply === net) || Object.values(R.inst).find(q => q.supply === net);
    if (i) want.push([net, +(i.rect[0] + i.rect[2] / 2 - 4).toFixed(2)]);
  }
  return want;
}
// The macro's own strap pairs as tile stripes (VDD -> VDPWR, VSS -> VGND), when it is placed upright
function macroStripes(v) {
  const R = FP.resolve(CAT, v), m = R.inst.xmac;
  return m ? m.straps.filter(q => q.r[2] < 5).map(q => [q.net, +q.r[0].toFixed(3), +q.r[2].toFixed(3)]) : [];
}

const RXC = FP.RX_CELLS.map(r => r[0]);
// The 37 DAC pins moved to the macro's own south edge (a pin_order.cfg change at the re-harden), spread over the
// middle of the edge: {pin: {x, y}} in its own frame at the reshaped width w.
function dacSouth(w) {
  const names = ['dac_sdn'].concat([0, 1, 2, 3, 4].map(b => `dac_bn[${b}]`), Array.from({ length: 31 }, (_, i) => `dac_tn[${i}]`));
  const x0 = 0.3 * w, x1 = 0.7 * w, out = {};
  names.forEach((n, i) => { out[n] = { x: +(x0 + (x1 - x0) * i / (names.length - 1)).toFixed(2), y: 0 }; });
  return out;
}
function startFrom(file) {
  const d = JSON.parse(fs.readFileSync(file)), out = {};
  for (const [n, i] of Object.entries(d.inst)) out[n] = { x: +i.rect[0].toFixed(2), y: +i.rect[1].toFixed(2), orient: i.orient };
  return out;
}
const START = process.argv.includes('--start') ? startFrom(process.argv[process.argv.indexOf('--start') + 1]) : null;
// Each spec: anneal from scratch, then (fit) move the listed blocks' pins to the edges facing what they connect to
// and polish with those pins, twice. fit: 'analog' = every block but the macro (no re-harden), 'all' = the macro too.
const ALLMOV = RXC.filter(n => n !== 'rx.lna').concat(['vco.core', 'vco.ref', 'vco.decap', 'xmdac', 'xvpd', 'xtxd', 'xbits']);
const SPECS = [
  {
    id: 'A', name: 'A: no re-harden: macro as it is on the right edge, vco_top split', rx: 'cells', vco: 'parts', runs: 5, iters: 200000, fit: 'analog', base: 'seeds/P4.json',
    fixed: { xmac: { x: 517.5, y: 53, orient: 'MY' }, 'rx.lna': { x: 76.5, y: 3, orient: 'R90' } },
    movable: ALLMOV,
  },
  {
    id: 'B', name: 'B: squarish macro top right (250 × 177), vco_top split, every pin fitted', rx: 'cells', vco: 'parts', runs: 5, iters: 200000, fit: 'all', base: 'seeds/P4.json',
    est: { xmac: { w: 250 } },
    fixed: { xmac: { x: 438, y: 136, orient: 'MY' }, 'rx.lna': { x: 76.5, y: 3, orient: 'R90' } },
    movable: ALLMOV,
  },
  {
    id: 'C', name: 'C: macro as hardened but turned 90° (260 × 170) top right, pins re-ordered', rx: 'cells', vco: 'parts', runs: 5, iters: 200000, fit: 'all', base: 'seeds/P4.json',
    fixed: { xmac: { x: 428.3, y: 143, orient: 'R90' }, 'rx.lna': { x: 76.5, y: 3, orient: 'R90' } },
    movable: ALLMOV,
  },
];

function current() {
  const c = JSON.parse(fs.readFileSync(path.join(dir, 'current.json')));
  const v = { id: 'current', name: 'current (tt_wrapper.py on the VAPWR tile, receiver area reserved)', rx: 'block', order: 0, place: {}, decaps: {}, est: {}, straps: c.straps, reserved: [] };
  for (const [n, p] of Object.entries(c.place)) v.place[n] = Object.assign({}, p);
  // the routes tt_wrapper draws, so the reserved area stays off them (out_n / out_p bars, the ua[0..3] drops, the
  // bit / ck / top-pin tracks): rough keep-out boxes, in the wrapper's tile, moved with the blocks
  const routes = [[178, 228, 520, 28], [178, 0, 15, 260], [233, 0, 15, 245], [250, 0, 60, 16], [170, 98, 450, 16], [170, 302, 160, 23]]
    .map(r => [r[0] - 17.92, r[1], r[2], r[3]]);
  const r = freeRects(v, routes, 2000)[0];
  v.reserved.push({ x: r[0], y: r[1], w: r[2], h: r[3], label: `receiver (reserved, ${r[2]} x ${r[3]} µm)` });
  v.note = `Today's tile from layout/gen/tt_wrapper.py, moved onto the VAPWR template (tt_analog_2x2_pgvaa.def, 693.28 µm wide, every pin 17.92 µm further left than in the wrapper's 711.20 µm tile): every block and stripe shifted 17.92 µm left with the pins, except the macro, which stays at x 0.6 (it would leave the tile). The stripes that fed vco_top, mdac and the code inverters are VAPWR now; tx_drv's and the macro's stay VDPWR. Positions: node layout/floorplan/page/check.js --current.\n` +
    `The largest free rectangle off the wrapper's routes is reserved for the receiver: ${r[2]} × ${r[3]} µm at (${r[0]}, ${r[1]}). The receiver (rx_top, 299.4 × 370.6 µm, or 70.4k µm² of cells) fits nowhere in this tile as it is.`;
  return v;
}

const NOTES = {
 "A": "No re-harden: the macro as it is (170 × 260 µm), mirrored onto the right edge so its DAC pins face west. vco_top split: cgm_ref stands on end (MXR90) between mdac and the macro, the ring + lsdiv unit at the bottom next to the receiver's Q level shifter (a2 → aq 3 µm). The analog blocks' pins are fitted to this placement (a re-layout each); the macro's are not.\nNumbers: RX input 212 µm from the macro and clocks; LNA inputs 3 µm; tx_drv on its pads; longest DAC line 196 µm; vg 18 µm.\nOpen: vbnf / vctrl from cgm_ref 51 / 52 µm and close to the DAC lines (rule 11); ls → rx 121 µm; vctrl → ua[0] 268 µm; ls, ck and the enables cross the receiver's LO end (rule 6).",
 "B": "A squarish re-harden (250 × 177 µm, 1.4:1, against 1.5:1 as hardened) in the top-right corner, its DAC pins on the west edge right against mdac (longest DAC line 16 µm). vco_top split: the ring + lsdiv unit in the middle, cgm_ref flat under the macro. Every pin fitted (the macro's: a new pin_order.cfg).\nNumbers: RX input 210 µm from the macro and clocks; a2 → aq 10 µm, ls → rx 63 µm; LNA inputs 3 µm; tx_drv on its pads; vg 3 µm.\nOpen: rx_bias ended up at the far right (nb / enb run across the tile) and q_i / q_q are 389 / 334 µm to uo[4] / uo[5]: drag the bias and the limiters back; vbnf 47 µm (rule 11); en_p / en_n and rx_en cross the receiver (rule 6).",
 "C": "The macro at its hardened size but turned 90° (260 × 170 µm) in the top-right corner: only the pin order changes at the re-harden, not the shape. DAC pins against mdac (16 µm). vco_top split with cgm_ref abutting the ring unit again (vbnf 11 µm, vctrl 5 µm). Every pin fitted.\nNumbers: RX input 210 µm from the macro and clocks; a2 → aq 3 µm, ls → rx 64 µm; LNA inputs 3 µm; tx_drv on its pads.\nOpen: limiter I ended up at the far right edge (q_i 669 µm to uo[4]): drag it back next to baseband I; mdac.vg → ring 134 µm (rule 7); the enables cross the receiver (rule 6)."
};

const outArg = process.argv.includes('--out') ? process.argv[process.argv.indexOf('--out') + 1] : null;
if (process.argv.includes('--merge')) {
  const vs = process.argv.slice(process.argv.indexOf('--merge') + 1).map(f => JSON.parse(fs.readFileSync(f)));
  const cur = current();
  vs.forEach((v, i) => { v.order = i + 1; });
  fs.writeFileSync(path.join(dir, 'variants.json'), JSON.stringify({ variants: [cur].concat(vs) }, null, 1) + '\n');
  process.exit(0);
}
if (process.argv.includes('--restripe')) {        // new stripes and decap fill for the seeded variants, placements kept
  const f = path.join(dir, 'variants.json'), j = JSON.parse(fs.readFileSync(f));
  for (const v of j.variants) if (v.id !== 'current') { v.straps = stripes(v, autoStripes(v)); v.decaps = fillDecap(v); }
  fs.writeFileSync(f, JSON.stringify(j, null, 1) + '\n');
  process.exit(0);
}
const only = process.argv.includes('--only') ? process.argv[process.argv.indexOf('--only') + 1] : null;
const file = path.join(dir, 'variants.json');
const prev = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file)).variants : [];
const out = [];
out.push(only && only !== 'current' ? prev.find(q => q.id === 'current') : current());
for (const spec of SPECS) {
  if (only && only !== spec.id) { const p = prev.find(q => q.id === spec.id); if (p) out.push(p); continue; }
  let best = null;
  for (let run = 0; run < (spec.runs || 4); run++) {
    seed = 1000 + run * 7919 + spec.id.charCodeAt(1);
    const base = spec.base ? JSON.parse(fs.readFileSync(path.join(dir, spec.base))).place : null;
    const r = solve(START ? Object.assign({}, spec, { start: START }) : base ? Object.assign({}, spec, { start: base, sigma: 40, T0: 400 }) : spec, START ? 120000 : spec.iters || 60000);
    if (!best || r.cost < best.cost) best = r;
    console.error(spec.id, 'run', run, r.cost.toFixed(0));
  }
  let v = { id: spec.id, name: spec.name, note: NOTES[spec.id] || '', rx: spec.rx, vco: spec.vco || 'block', order: out.length, place: best.place, est: spec.est || {}, pins: spec.pins || {}, decaps: {}, straps: [], reserved: [] };
  for (let k = 0; spec.fit && k < 2; k++) {        // fit the pins to this placement, then polish with them
    const names = Object.keys(FP.resolve(CAT, v).inst).filter(n => spec.fit === 'all' || n !== 'xmac');
    v.pins = FP.fitPins(data, CAT, v, names);
    let pol = null;
    for (let run = 0; run < 3; run++) {
      seed = 5000 + run * 131 + k;
      const r = solve(Object.assign({}, spec, { pins: v.pins, start: v.place }), 100000);
      if (!pol || r.cost < pol.cost) pol = r;
    }
    console.error(spec.id, 'fit + polish', k, pol.cost.toFixed(0));
    v.place = pol.place;
  }
  if (spec.fit) v.pins = FP.fitPins(data, CAT, v, Object.keys(FP.resolve(CAT, v).inst).filter(n => spec.fit === 'all' || n !== 'xmac'));
  v.straps = stripes(v, autoStripes(v));
  v.decaps = fillDecap(v);
  out.push(v);
  if (outArg) fs.writeFileSync(outArg, JSON.stringify(v, null, 1));
}
if (outArg) process.exit(0);
fs.writeFileSync(file, JSON.stringify({ variants: out.filter(Boolean) }, null, 1) + '\n');
