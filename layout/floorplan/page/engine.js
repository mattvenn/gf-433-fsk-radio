// Floorplan engine for the gf-433-oscillator tile (2x2 GF180 analog, VAPWR template): instances, orientations,
// pins, nets, supply domains and the ranked-rule checks (docs/floorplan_spec.md). Ported from the OOK radio's
// floorplan page (github.com/mattvenn/ook-asic-radio, layout/floorplan/page/engine.js).
// Pure functions, no DOM: the page inlines this file, and `node layout/floorplan/page/check.js` runs the same
// checks on layout/floorplan/variants.json.
// Units: um, tile origin at its lower-left. A placement {x, y, orient} puts the lower-left corner of the
// transformed bbox at (x, y), as in floorplan.json.
(function (root) {
  'use strict';

  // GDS orientations as (rotation k * 90 deg CCW, mirror about the x axis first), the same decomposition as
  // KLayout's DCplxTrans(mag, rot, mirror, u). MY = x -> -x (tt_wrapper's vco_top), MX = y -> -y (its tx_drv).
  const ORIENTS = {
    R0: [0, false], R90: [1, false], R180: [2, false], R270: [3, false],
    MX: [0, true], MXR90: [1, true], MY: [2, true], MYR90: [3, true],
  };
  const ORIENT_OF = {};
  for (const [n, [k, m]] of Object.entries(ORIENTS)) ORIENT_OF[k + (m ? 'm' : '')] = n;
  function rotPt(k, m, x, y) {
    if (m) y = -y;
    for (let i = 0; i < k; i++) [x, y] = [-y, x];
    return [x, y];
  }
  function placedSize(orient, w, h) { return ORIENTS[orient][0] % 2 ? [h, w] : [w, h]; }
  function mapPt(pl, w, h, x, y) {           // cell-local point (bbox lower-left = 0, 0) -> tile
    const [k, m] = ORIENTS[pl.orient];
    const cs = [[0, 0], [w, 0], [0, h], [w, h]].map(([a, b]) => rotPt(k, m, a, b));
    const mx = Math.min(...cs.map(c => c[0])), my = Math.min(...cs.map(c => c[1]));
    const [px, py] = rotPt(k, m, x, y);
    return [pl.x + px - mx, pl.y + py - my];
  }
  function mapRect(pl, w, h, r) {
    const a = mapPt(pl, w, h, r[0], r[1]), b = mapPt(pl, w, h, r[0] + r[2], r[1] + r[3]);
    return [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.abs(a[0] - b[0]), Math.abs(a[1] - b[1])];
  }
  function compose(orient, op) {            // rotate 90 CCW / flip top-bottom (MX) / flip left-right (MY) on screen
    let [k, m] = ORIENTS[orient];
    if (op === 'rot') k = (k + 1) % 4;
    else if (op === 'mx') { k = (4 - k) % 4; m = !m; }
    else if (op === 'my') { k = (6 - k) % 4; m = !m; }
    return ORIENT_OF[k + (m ? 'm' : '')];
  }

  // ---- the tile's contents (docs/floorplan_spec.md, "What goes in the tile")
  // supply: the block's rail (Matt 2026-11-16): the quiet analog and the receiver on VAPWR, tx_drv and tx_fine on VDPWR.
  const RX_CELLS = [                         // [inst, cell, label, index of the cell in rx_top's instance list]
    ['rx.lna', 'rx_lna', 'LNA', 'rx_lna'], ['rx.bias', 'rx_bias', 'bias', 'rx_bias'], ['rx.lsq', 'rx_lsq', 'Q level shift', 'rx_lsq'],
    ['rx.lobuf_q', 'rx_lobuf', 'LO buf Q', 'rx_lobuf#0'], ['rx.mix_q', 'rx_mix', 'mixer Q', 'rx_mix#0'],
    ['rx.lobuf_i', 'rx_lobuf', 'LO buf I', 'rx_lobuf#1'], ['rx.mix_i', 'rx_mix', 'mixer I', 'rx_mix#1'],
    ['rx.bb_i', 'rx_bb', 'baseband I', 'rx_bb#0'], ['rx.bb_q', 'rx_bb', 'baseband Q', 'rx_bb#1'],
    ['rx.lim_i', 'rx_lim', 'limiter I', 'rx_lim#1'], ['rx.lim_q', 'rx_lim', 'limiter Q', 'rx_lim#0'],
    ['rx.decap', 'rx_decap', 'RX decap', 'rx_decap'],
  ];
  // where vco_top's sub-blocks sit, in its own bbox frame (docs/top_layout.md "Floorplan"; vco_top.py)
  const VCO_ZONES = { decap_ls: [0, 0, 37.2, 70.8], lsdiv: [37.23, 33.06, 40.49, 36.7], ring: [77.72, 0, 70.09, 51.88], cgm_ref: [148.81, 1.6, 237.75, 69.2] };
  const VCO_A2 = { layer: 'Metal2', x: 89.89, y: 41.17, est: true };     // the ring's a2 node (ring_core_v3 label); no pin yet
  // vco_top's parts, from vco_top.gds: ring_core at (77.72, 0) 70.09 x 51.875, lsdiv at (37.23, 33.055) 40.49 x 36.705,
  // cgm_ref at (147.81, 1.6) 238.75 x 69.195, decap_ls at (0, 1.6) 78.62 x 59.955 (L-shaped: its left 37.2 um, and
  // three short fingers under lsdiv, which stay with the core unit). Pins from the cells' own labels.
  const VCO_PARTS = {
    'vco.core': { cell: 'ring_core_v3 + lsdiv', label: 'ring + lsdiv', w: 110.58, h: 69.76, inVco: [37.23, 0],
      zones: { lsdiv: [0, 33.055, 40.49, 36.705], ring: [40.49, 0, 70.09, 51.875] },
      pins: { ck: { layer: 'Metal2', x: 0.15, y: 38.4 }, ls: { layer: 'Metal3', x: 20.98, y: 69.56 }, a2: { layer: 'Metal2', x: 52.66, y: 41.17, est: true },
        vg: { layer: 'Metal3', x: 72.58, y: 0.3 }, bit2: { layer: 'Metal3', x: 84.07, y: 51.58 }, vbnf: { layer: 'Metal2', x: 110.38, y: 46.67 },
        vctrl: { layer: 'Metal2', x: 110.38, y: 16.94 }, VDD: { layer: 'Metal2', x: 42.47, y: 48.36 }, VDD_LS: { layer: 'Metal2', x: 1.3, y: 46.37 } } },
    'vco.ref': { cell: 'cgm_ref', label: 'cgm_ref (bias + 1 MΩ / 20 pF)', w: 238.75, h: 69.195, inVco: [147.81, 1.6],
      pins: { vbnf: { layer: 'Metal2', x: 0.1, y: 45.065 }, vctrl_l: { layer: 'Metal2', x: 0.1, y: 15.335, est: true },
        vctrl: { layer: 'Metal2', x: 238.65, y: 15.335 }, vbn: { layer: 'Metal2', x: 238.65, y: 48.605 }, VDD: { layer: 'Metal2', x: 116.24, y: 66.48 } } },
    'vco.decap': { cell: 'decap_ls', label: 'VDD_LS decap 10 pF', w: 37.23, h: 59.955, inVco: [0, 1.6],
      pins: { VDD_LS: { layer: 'Metal2', x: 18.6, y: 59.9, est: true } } },
  };
  const MAC_RXEN = { layer: 'Metal3', x: 170, y: 256.7, est: true };      // tx_fine rx_en: not hardened yet (integration prep)

  function buildCatalog(data) {
    const C = data.cells, cat = {};
    const real = (inst, cell, extra) => Object.assign({ inst, cell, w: C[cell].w, h: C[cell].h, pins: C[cell].pins, m4: C[cell].m4 || [] }, extra || {});
    cat.xvco = real('xvco', 'vco_top', { supply: 'VAPWR', group: 'vco', label: 'vco_top', zones: VCO_ZONES,
      pins: Object.assign({}, C.vco_top.pins, C.vco_top.pins.a2 ? {} : { a2: VCO_A2 }) });
    // vco_top as its parts (the same layout, cut along its own sub-cells: vco_top.gds instance boxes). The ring and
    // lsdiv stay one unit: their a0 pins abut with no wire (a0 is 5.83 fF in all). Own frames: lower-left = 0, 0.
    for (const [n, p] of Object.entries(VCO_PARTS)) cat[n] = Object.assign({ inst: n, supply: 'VAPWR', group: 'vco', vco: 'parts', m4: [] }, p);
    cat.xvco.vco = 'block';
    cat.xmdac = real('xmdac', 'mdac', { supply: 'VAPWR', group: 'fine', label: 'mdac' });
    cat.xvpd = real('xvpd', 'vctrl_pd', { supply: 'VAPWR', group: 'vco', label: 'vctrl_pd' });
    cat.xbits = { inst: 'xbits', cell: 'bits_inv', w: 20.16, h: 7.84, supply: 'VAPWR', group: 'vco', label: 'code inverters', glue: true,
      pins: { in: { layer: 'Metal3', x: 10.08, y: 7.84 }, out: { layer: 'Metal3', x: 10.08, y: 0 } }, m4: [],
      note: 'tt_wrapper.py: five inv_1 (bitb = not ui_in) and five antenna diodes, two std-cell rows (20.16 x 7.84 um)' };
    cat.xtxd = real('xtxd', 'tx_drv', { supply: 'VDPWR', group: 'tx', label: 'tx_drv' });
    cat.xmac = real('xmac', 'tx_fine', { supply: 'VDPWR', group: 'dig', label: 'tx_fine (macro)', halo: 5, reshape: true,
      pins: Object.assign({}, C.tx_fine.pins, C.tx_fine.pins.rx_en ? {} : { rx_en: MAC_RXEN }),
      m4: [[0, 0, C.tx_fine.w, C.tx_fine.h]], straps: C.tx_fine.straps || [] });
    // the receiver as one block, with its cells' outlines as zones (rx_top's own placement)
    const rinst = {}, seen = {};
    for (const i of C.rx_top.inst || []) { const k = seen[i.cell] === undefined ? (seen[i.cell] = 0) : ++seen[i.cell]; rinst[`${i.cell}#${k}`] = i; if (k === 0) rinst[i.cell] = i; }
    const zones = {};
    for (const [inst, , , key] of RX_CELLS) { const i = rinst[key]; if (i) zones[inst.slice(3)] = [i.x, i.y, i.w, i.h]; }
    cat.xrx = real('xrx', 'rx_top', { supply: 'VAPWR', group: 'rx', label: 'rx_top', rx: 'block', zones });
    for (const [inst, cell, label, key] of RX_CELLS) {
      const i = rinst[key];
      cat[inst] = real(inst, cell, { supply: 'VAPWR', group: 'rx', label, rx: 'cells', inRxTop: i ? [i.x, i.y] : null });
    }
    return cat;
  }
  const rxMode = v => (v && v.rx === 'cells' ? 'cells' : 'block');
  const vcoMode = v => (v && v.vco === 'parts' ? 'parts' : 'block');
  const inMode = (c, v) => (!c.rx || c.rx === rxMode(v)) && (!c.vco || c.vco === vcoMode(v));

  const MIM_FF = 0;                          // no MIM in this design (gf180mcuD here: no MIM layer used)
  const DECAP_FF = 2.4;                      // fF / um2 of decap tile: nfet_03v3 gate cap 4.07 fF/um2 (top_layout.md) at ~60 % fill
  const DECAPS = {
    deca: { cell: 'decap_vapwr', net: 'VAPWR', label: 'decap VAPWR' },
    decd: { cell: 'decap_vdpwr', net: 'VDPWR', label: 'decap VDPWR' },
  };

  // ---- nets: [name, class, from, to]; endpoints "inst.pin", "pad:<tile pin>", or "RX.<port>" (the receiver's port,
  // on rx_top or on the cell that has it, by the variant's receiver mode)
  const VCO_PORT = { ls: 'vco.core.ls', a2: 'vco.core.a2', ck: 'vco.core.ck', vg: 'vco.core.vg', vbnf: 'vco.core.vbnf', bit2: 'vco.core.bit2',
    vctrl: 'vco.ref.vctrl', vbn: 'vco.ref.vbn' };
  // inside vco_top, only when it is placed as parts: the wires its abutments made unnecessary
  const VCO_NETS = [['vbnf ref', 'ana', 'vco.ref.vbnf', 'vco.core.vbnf'], ['vctrl ring', 'ana', 'vco.ref.vctrl_l', 'vco.core.vctrl'],
    ['VDD_LS decap', 'ana', 'vco.decap.VDD_LS', 'vco.core.VDD_LS']];
  const RX_PORT = { inp: 'rx.lna.inp', inn: 'rx.lna.inn', ls: 'rx.lobuf_i.in', aq: 'rx.lsq.aq', en: 'rx.bias.en', q_i: 'rx.lim_i.q', q_q: 'rx.lim_q.q' };
  const DACN = [];
  for (let i = 0; i < 31; i++) DACN.push([`dac_tn[${i}]`, 'fine', `xmac.dac_tn[${i}]`, `xmdac.ns${i + 1}`]);
  for (let b = 0; b < 5; b++) DACN.push([`dac_bn[${b}]`, 'fine', `xmac.dac_bn[${b}]`, `xmdac.nb${b}`]);
  DACN.push(['dac_sdn', 'fine', 'xmac.dac_sdn', 'xmdac.nsd']);
  const NETS = [
    ['rx_inp', 'rfin', 'pad:ua[4]', 'RX.inp'], ['rx_inn', 'rfin', 'pad:ua[5]', 'RX.inn'],
    ['tx_out_n', 'tx', 'xtxd.out_n', 'pad:ua[2]'], ['tx_out_p', 'tx', 'xtxd.out_p', 'pad:ua[3]'],
    ['vctrl', 'ana', 'pad:ua[0]', 'VCO.vctrl'], ['vctrl pd', 'ana', 'xvpd.a', 'VCO.vctrl'], ['vbn', 'ana', 'pad:ua[1]', 'VCO.vbn'],
    ['ls rx', 'lo', 'VCO.ls', 'RX.ls'], ['ls tx', 'lo', 'VCO.ls', 'xtxd.ls'], ['a2', 'lo', 'VCO.a2', 'RX.aq'],
    ['vg', 'ana', 'xmdac.vg', 'VCO.vg'], ['vbnf', 'ana', 'VCO.vbnf', 'xmdac.vbnf'],
    ['ck', 'clk', 'VCO.ck', 'xmac.ck'],
    ['ck_o', 'clk', 'xmac.ck_o', 'pad:uo_out[0]'], ['div16', 'clk', 'xmac.div16', 'pad:uo_out[1]'],
    ['div64', 'clk', 'xmac.div64', 'pad:uo_out[2]'], ['div1024', 'clk', 'xmac.div1024', 'pad:uo_out[3]'],
    ['clk', 'dig', 'pad:clk', 'xmac.clk'], ['rst_n', 'dig', 'pad:rst_n', 'xmac.rst_n'],
    ['sclk', 'dig', 'pad:uio_in[0]', 'xmac.sclk'], ['mosi', 'dig', 'pad:uio_in[1]', 'xmac.mosi'], ['cs_n', 'dig', 'pad:uio_in[2]', 'xmac.cs_n'],
    ['miso', 'dig', 'xmac.miso', 'pad:uio_out[3]'], ['fsk', 'dig', 'pad:ui_in[7]', 'xmac.fsk'],
    ['rx_en', 'en', 'xmac.rx_en', 'RX.en'],
    ['code', 'en', 'pad:ui_in[2]', 'xbits.in'], ['bits', 'en', 'xbits.out', 'VCO.bit2'],
    ['en_p', 'en', 'pad:ui_in[5]', 'xtxd.en_p'], ['en_n', 'en', 'pad:ui_in[6]', 'xtxd.en_n'],
    ['q_i', 'rxout', 'RX.q_i', 'pad:uo_out[4]'], ['q_q', 'rxout', 'RX.q_q', 'pad:uo_out[5]'],
  ].concat(DACN);
  // inside the receiver, only when it is placed as cells (layout/gen/rx_top.py, its `nets`)
  const RX_NETS = [
    ['ri_p', 'rx', 'rx.lna.oip', 'rx.mix_i.rfp'], ['ri_n', 'rx', 'rx.lna.oin', 'rx.mix_i.rfn'],
    ['rq_p', 'rx', 'rx.lna.oqp', 'rx.mix_q.rfp'], ['rq_n', 'rx', 'rx.lna.oqn', 'rx.mix_q.rfn'],
    ['lsq', 'lo', 'rx.lsq.lsq', 'rx.lobuf_q.in'],
    ['lo_i', 'lo', 'rx.lobuf_i.lo', 'rx.mix_i.lo'], ['lob_i', 'lo', 'rx.lobuf_i.lob', 'rx.mix_i.lob'],
    ['lo_q', 'lo', 'rx.lobuf_q.lo', 'rx.mix_q.lo'], ['lob_q', 'lo', 'rx.lobuf_q.lob', 'rx.mix_q.lob'],
    ['bi_p', 'rx', 'rx.mix_i.bbp', 'rx.bb_i.inp'], ['bi_n', 'rx', 'rx.mix_i.bbn', 'rx.bb_i.inn'],
    ['bq_p', 'rx', 'rx.mix_q.bbp', 'rx.bb_q.inp'], ['bq_n', 'rx', 'rx.mix_q.bbn', 'rx.bb_q.inn'],
    ['oi_p', 'rx', 'rx.bb_i.outp', 'rx.lim_i.inp'], ['oi_n', 'rx', 'rx.bb_i.outn', 'rx.lim_i.inn'],
    ['oq_p', 'rx', 'rx.bb_q.outp', 'rx.lim_q.inp'], ['oq_n', 'rx', 'rx.bb_q.outn', 'rx.lim_q.inn'],
    ['rx_en lo_i', 'en', 'xmac.rx_en', 'rx.lobuf_i.en'], ['rx_en lo_q', 'en', 'xmac.rx_en', 'rx.lobuf_q.en'],
  ].concat(['lna', 'bb_i', 'bb_q', 'lim_i', 'lim_q'].flatMap(c => [[`nb ${c}`, 'ana', 'rx.bias.nb', `rx.${c}.nb`], [`enb ${c}`, 'en', 'rx.bias.enb', `rx.${c}.enb`]]));
  const NET_CLASSES = {
    rfin: 'RX input', rx: 'RX signal', rxout: 'RX outputs', lo: 'LO', clk: 'ring-derived clock', dig: '25 MHz / SPI', fine: 'fine-tune bus',
    en: 'enable / code (static)', tx: 'TX output', ana: 'analog DC',
  };
  // aggressors for the RX input (rule 1), and what may not run over the receiver (rule 6)
  const AGGR = ['clk', 'dig', 'fine'];
  const NOT_OVER_RX = ['clk', 'dig', 'fine', 'lo', 'en', 'tx'];

  const DEFAULT_SETTINGS = {
    keepout: 2.5,          // um between blocks (guard rings)
    track: 0.8,            // um per wire in the top routing channel (tt_wrapper: 0.8 um M2 tracks)
    r1: 150,               // 1. RX input <-> macro and ring-derived / digital wires >= (um)
    r2a: 40, r2b: 120, r2m: 150,   // 2. a2 wire <=, ls -> rx <=, ls load - lsq load <=
    r3: 40,                // 3. ua[4] / ua[5] -> LNA <=
    r4: 80,                // 4. tx_drv -> ua[2] / ua[3] <=
    r7: 200, r7b: 60,      // 7. DAC line (longest) <=, mdac.vg -> vco_top.vg <=
    r8: 40,                // 8. macro top <-> tile top <=
    r11: 40, r11d: 50,     // 11. (vco_top split) cgm_ref -> ring vbnf / vctrl <=, and their distance from aggressor wires >=
    lsq: 43.5,             // um: rx_top's lsq wire (the Q LO level shifter output, rx_layout.md), used in block mode
  };

  // ---- geometry
  const area = r => r[2] * r[3];
  function rectGap(a, b) {
    const dx = Math.max(0, b[0] - (a[0] + a[2]), a[0] - (b[0] + b[2]));
    const dy = Math.max(0, b[1] - (a[1] + a[3]), a[1] - (b[1] + b[3]));
    return Math.hypot(dx, dy);
  }
  function overlap(a, b) {
    const w = Math.min(a[0] + a[2], b[0] + b[2]) - Math.max(a[0], b[0]);
    const h = Math.min(a[1] + a[3], b[1] + b[3]) - Math.max(a[1], b[1]);
    return w > 1e-6 && h > 1e-6 ? w * h : 0;
  }
  const segRect = s => [Math.min(s[0], s[2]), Math.min(s[1], s[3]), Math.abs(s[2] - s[0]), Math.abs(s[3] - s[1])];
  function segCrosses(s, r, margin) {
    const m = margin || 0, q = [r[0] + m, r[1] + m, r[2] - 2 * m, r[3] - 2 * m];
    if (q[2] <= 0 || q[3] <= 0) return false;
    const sr = segRect(s);
    return sr[0] < q[0] + q[2] && sr[0] + sr[2] > q[0] && sr[1] < q[1] + q[3] && sr[1] + sr[3] > q[1];
  }
  const manhattan = (a, b) => Math.abs(a[0] - b[0]) + Math.abs(a[1] - b[1]);
  function lRoute(a, b, obstacles) {         // two L routes; the one crossing fewer blocks (ties: horizontal first)
    const r1 = [[a[0], a[1], b[0], a[1]], [b[0], a[1], b[0], b[1]]];
    const r2 = [[a[0], a[1], a[0], b[1]], [a[0], b[1], b[0], b[1]]];
    if (!obstacles || !obstacles.length) return r1;
    const hits = r => obstacles.filter(o => r.some(s => segCrosses(s, o, 0.6))).length;
    return hits(r2) < hits(r1) ? r2 : r1;
  }

  // ---- placement. A variant: {name, note, rx: 'block'|'cells', place: {inst: {x, y, orient}},
  //   decaps: {deca: [{x,y,w,h}], decd: [...]}, straps: [{net, x, w}], est: {xmac: {w, area?}},
  //   reserved: [{x, y, w, h, label}]}
  function resolve(cat, v) {
    const inst = {};
    for (const [n, c] of Object.entries(cat)) {
      const p = (v.place || {})[n];
      if (!p || !inMode(c, v)) continue;
      let w = c.w, h = c.h;
      if (!c.glue && v.est && v.est[n]) { w = v.est[n].w; h = (v.est[n].area || c.w * c.h) / w; }   // reshaped (a re-layout / re-harden)
      const pl = { x: p.x, y: p.y, orient: p.orient || 'R0' };
      const [pw, ph] = placedSize(pl.orient, w, h);
      const rect = [pl.x, pl.y, pw, ph];
      const sx = w / c.w, sy = h / c.h, pins = {};
      const mv = (v.pins || {})[n] || {};
      for (const [pn, pp] of Object.entries(c.pins)) {
        const m = mv[pn];
        pins[pn] = Object.assign({}, pp, m ? { x: m.x, y: m.y, moved: true, at: mapPt(pl, w, h, m.x, m.y) } : { at: mapPt(pl, w, h, pp.x * sx, pp.y * sy) });
      }
      const m4 = (c.m4 || []).map(r => c.reshape ? [0, 0, w, h] : r).map(r => mapRect(pl, w, h, r));
      const straps = (c.straps || []).map(s => ({ net: s.net === 'VDD' ? 'VDPWR' : 'VGND', r: mapRect(pl, w, h, [s.x * sx, 0, s.w, h]) }));
      const zones = {};
      for (const [zn, z] of Object.entries(c.zones || {})) zones[zn] = mapRect(pl, w, h, [z[0] * sx, z[1] * sy, z[2] * sx, z[3] * sy]);
      const reshaped = Math.abs(w - c.w) > 1e-6 || Math.abs(h - c.h) > 1e-6;
      inst[n] = { name: n, cat: c, pl, w, h, rect, pins, m4, straps, zones, supply: c.supply, reshaped,
        halo: c.halo ? [rect[0] - c.halo, rect[1] - c.halo, rect[2] + 2 * c.halo, rect[3] + 2 * c.halo] : null };
    }
    const decaps = [];
    for (const [n, d] of Object.entries(DECAPS)) ((v.decaps || {})[n] || []).forEach((r, i) =>
      decaps.push({ name: `${n}.${i + 1}`, base: n, idx: i, def: d, rect: [r.x, r.y, r.w, r.h] }));
    const reserved = (v.reserved || []).map((r, i) => ({ name: `reserved.${i + 1}`, idx: i, label: r.label || 'reserved', rect: [r.x, r.y, r.w, r.h] }));
    return { inst, decaps, reserved, mode: rxMode(v), vmode: vcoMode(v) };
  }

  const isTopPad = (tile, n) => tile.pins[n] && tile.pins[n].y0 > 1;
  function resolveRef(ref, mode, vmode) {
    if (ref.startsWith('VCO.')) return vmode === 'parts' ? VCO_PORT[ref.slice(4)] : 'xvco.' + ref.slice(4);
    return ref.startsWith('RX.') ? (mode === 'cells' ? RX_PORT[ref.slice(3)] : 'xrx.' + ref.slice(3)) : ref;
  }
  function pinAt(tile, R, ref) {
    if (ref.startsWith('pad:')) {
      const p = tile.pins[ref.slice(4)];
      if (!p) return null;
      return [(p.x0 + p.x1) / 2, p.y0 < 1 ? 0 : tile.h];
    }
    const i = ref.lastIndexOf('.'), ins = R.inst[ref.slice(0, i)];
    if (!ins) return null;
    const p = ins.pins[ref.slice(i + 1)];
    return p ? p.at : null;
  }
  const ownerOf = ref => ref.startsWith('pad:') ? null : ref.slice(0, ref.lastIndexOf('.'));
  function netList(mode, vmode) { return NETS.concat(mode === 'cells' ? RX_NETS : [], vmode === 'parts' ? VCO_NETS : []); }

  function routeNets(tile, R) {
    const out = [];
    for (const [name, cls, a0, b0] of netList(R.mode, R.vmode)) {
      const a = resolveRef(a0, R.mode, R.vmode), b = resolveRef(b0, R.mode, R.vmode);
      const pa = pinAt(tile, R, a), pb = pinAt(tile, R, b);
      if (!pa || !pb) { out.push({ name, cls, a, b, missing: true }); continue; }
      const ownA = ownerOf(a), ownB = ownerOf(b);
      const others = Object.values(R.inst).filter(i => i.name !== ownA && i.name !== ownB).map(i => i.rect);
      const est = [a, b].some(r => { const o = ownerOf(r); return o && R.inst[o] && (R.inst[o].pins[r.slice(o.length + 1)] || {}).est; });
      out.push({ name, cls, a, b, pa, pb, len: manhattan(pa, pb), segs: lRoute(pa, pb, others), est });
    }
    return out;
  }

  // The routing channel along the top: every net with a top-edge TT pin runs horizontally there, between the pin's
  // x and the block pin's x; at each x it is as tall as the number of wires crossing it times the track pitch.
  function channelShapes(tile, nets, s) {
    const spans = [];
    for (const n of nets) {
      if (n.missing) continue;
      const pad = [n.a, n.b].find(r => r.startsWith('pad:') && isTopPad(tile, r.slice(4)));
      if (!pad) continue;
      const other = pad === n.a ? n.pb : n.pa, px = pad === n.a ? n.pa[0] : n.pb[0];
      spans.push([Math.min(px, other[0]) - 0.4, Math.max(px, other[0]) + 0.4]);
    }
    if (!spans.length) return [];
    const xs = [...new Set(spans.flat())].sort((a, b) => a - b), out = [];
    for (let i = 0; i < xs.length - 1; i++) {
      const a = xs[i], b = xs[i + 1], mid = (a + b) / 2, k = spans.filter(([p, q]) => p <= mid && q >= mid).length;
      if (!k) continue;
      const h = k * s.track, last = out[out.length - 1];
      if (last && Math.abs(last[3] - h) < 1e-9 && Math.abs(last[0] + last[2] - a) < 1e-9) last[2] = b - last[0];
      else out.push([a, tile.h - h, b - a, h]);
    }
    return out;
  }

  const fmt = (x, d) => (x === Infinity || x === -Infinity || x === undefined || isNaN(x) ? '-' : x.toFixed(d === undefined ? 0 : d));
  function minGapShapes(A, B) { let d = Infinity; for (const a of A) for (const b of B) d = Math.min(d, rectGap(a, b)); return d; }

  // Supply crossings: nets between blocks on different rails, and the TT pins' wires into VAPWR blocks.
  function crossings(tile, R, nets) {
    const out = [];
    for (const n of nets) {
      if (n.missing) continue;
      const sup = r => { if (r.startsWith('pad:')) return r.startsWith('pad:ua') ? null : 'VDPWR'; const o = ownerOf(r); return R.inst[o] ? R.inst[o].supply : null; };
      const sa = sup(n.a), sb = sup(n.b);
      if (sa && sb && sa !== sb) out.push({ net: n.name, cls: n.cls, from: `${n.a.replace('pad:', '')} (${sa})`, to: `${n.b.replace('pad:', '')} (${sb})` });
    }
    return out;
  }

  // ---- checks: [{rule, title, status: pass|warn|fail|info, value, detail}]
  function evaluate(data, cat, v, settings) {
    const s = Object.assign({}, DEFAULT_SETTINGS, settings || {});
    const tile = data.tile, R = resolve(cat, v), nets = routeNets(tile, R);
    const I = R.inst, res = [], mode = R.mode;
    const add = (rule, title, status, value, detail) => res.push({ rule, title, status, value, detail: detail || '' });
    const netBy = n => nets.find(x => x.name === n);
    const ok = n => n && !n.missing;
    const segsOf = list => list.filter(ok).flatMap(n => n.segs.map(segRect));
    const lvl = (x, pass, warn, higher) => higher ? (x >= pass ? 'pass' : x >= warn ? 'warn' : 'fail') : (x <= pass ? 'pass' : x <= warn ? 'warn' : 'fail');
    const chanSh = channelShapes(tile, nets, s);
    const missing = Object.entries(cat).filter(([n, c]) => inMode(c, v) && !I[n]).map(([n]) => n);
    const M = I.xmac, V = I.xvco || I['vco.core'];
    const rxInst = Object.values(I).filter(i => i.cat.group === 'rx');
    const lna = mode === 'cells' ? (I['rx.lna'] && I['rx.lna'].rect) : (I.xrx && I.xrx.zones.lna);
    const estNote = list => { const e = list.filter(n => ok(n) && n.est).map(n => n.name); return e.length ? ` Estimated pin position: ${e.join(', ')}.` : ''; };

    // 1. RX input far from the macro and from everything the ring clocks
    if (lna && M) {
      const inZone = [lna].concat(segsOf([netBy('rx_inp'), netBy('rx_inn')]));
      const aggrNets = nets.filter(n => ok(n) && AGGR.includes(n.cls));
      const dM = minGapShapes(inZone, [M.halo]);
      const dW = minGapShapes(inZone, segsOf(aggrNets));
      const dC = minGapShapes(inZone, chanSh);
      const near = aggrNets.map(n => [n.name, minGapShapes(inZone, n.segs.map(segRect))]).sort((a, b) => a[1] - b[1]).slice(0, 3);
      const over = aggrNets.filter(n => n.segs.some(sg => segCrosses(sg, lna, 0.6)));
      const dLs = V ? minGapShapes(inZone, [V.zones.lsdiv]) : Infinity, dRing = V ? minGapShapes(inZone, [V.zones.ring]) : Infinity;
      const d = Math.min(dM, dW, dC);
      add(1, 'RX input far from the macro and clocks', over.length ? 'fail' : lvl(d, s.r1, s.r1 / 2, true), `${fmt(d)} µm`,
        `LNA + ua[4] / ua[5] wires ↔ macro halo ${fmt(dM)} µm, ↔ ck / dividers / 25 MHz / SPI / DAC wires ${fmt(dW)} µm (closest: ${near.map(([n, x]) => `${n} ${fmt(x)}`).join(', ')}), ↔ top channel ${fmt(dC)} µm (want ≥ ${s.r1}). ` +
        (over.length ? `Over the LNA: ${over.map(n => n.name).join(', ')}. ` : '') +
        `lsdiv ↔ LNA ${fmt(dLs)} µm, ring ↔ LNA ${fmt(dRing)} µm (LO-locked, land at DC). Open question: gate ck and the dividers during RX (and when).`);
    } else add(1, 'RX input far from the macro and clocks', 'info', '-', 'Place the receiver (or its LNA) and the macro.');

    // 2. LO wires: a2 -> aq short, ls -> rx short, the two LO loads matched
    {
      const a2 = netBy('a2'), lr = netBy('ls rx'), lt = netBy('ls tx'), lq = netBy('lsq');
      if (ok(a2) && ok(lr)) {
        const lsTot = lr.len + (ok(lt) ? lt.len : 0), lsqLen = ok(lq) ? lq.len : s.lsq, mm = lsTot - lsqLen;
        const st = [lvl(a2.len, s.r2a, 2 * s.r2a), lvl(lr.len, s.r2b, 2 * s.r2b), Math.abs(mm) <= s.r2m ? 'pass' : 'warn'];
        const worst = st.includes('fail') ? 'fail' : st.includes('warn') ? 'warn' : 'pass';
        add(2, 'LO wires short and matched', worst, `a2 ${fmt(a2.len)} µm`,
          `a2 → rx aq ${fmt(a2.len)} µm (want ≤ ${s.r2a}: every fF on a2 slows the ring and shifts the I/Q phase); ls → rx ${fmt(lr.len)} µm (want ≤ ${s.r2b}). ` +
          `I load: ls drives ${fmt(lsTot)} µm (rx ${fmt(lr.len)} + tx_drv ${ok(lt) ? fmt(lt.len) : '-'}); Q load: lsq ${fmt(lsqLen)} µm${ok(lq) ? '' : ' (inside rx_top)'}; difference ${fmt(mm)} µm (want |Δ| ≤ ${s.r2m}).` + estNote([a2]));
      } else add(2, 'LO wires short and matched', 'info', '-', 'Place vco_top and the receiver.');
    }

    // 3. LNA at ua[4] / ua[5], short and symmetric
    {
      const p = netBy('rx_inp'), n = netBy('rx_inn');
      if (ok(p) && ok(n)) {
        const m = Math.max(p.len, n.len), asym = Math.abs(p.len - n.len);
        const st = lvl(m, s.r3, 2 * s.r3);
        add(3, 'LNA at ua[4] / ua[5]', st === 'pass' && asym > 10 ? 'warn' : st, `${fmt(m)} µm`,
          `ua[4] → inp ${fmt(p.len, 1)}, ua[5] → inn ${fmt(n.len, 1)} µm (want ≤ ${s.r3}, and equal: Δ ${fmt(asym, 1)} µm).`);
      } else add(3, 'LNA at ua[4] / ua[5]', 'info', '-', 'Place the receiver.');
    }

    // 4. TX driver at ua[2] / ua[3]
    {
      const n_ = netBy('tx_out_n'), p_ = netBy('tx_out_p');
      if (ok(n_) && ok(p_)) {
        const m = Math.max(n_.len, p_.len);
        const rin = segsOf([netBy('rx_inp'), netBy('rx_inn')]).concat(lna ? [lna] : []);
        const dRx = minGapShapes(segsOf([n_, p_]), rin);
        add(4, 'TX driver at ua[2] / ua[3]', lvl(m, s.r4, 2.5 * s.r4), `${fmt(m)} µm`,
          `out_n → ua[2] ${fmt(n_.len)}, out_p → ua[3] ${fmt(p_.len)} µm (12.6 mA: short and wide; want ≤ ${s.r4}). TX out wires ↔ RX input ${fmt(dRx)} µm (soft: the TX is off in RX; ua[3] is the pad next to ua[4]).`);
      } else add(4, 'TX driver at ua[2] / ua[3]', 'info', '-', 'Place tx_drv.');
    }

    // 5. supply domains
    const cross = crossings(tile, R, nets);
    {
      const straps = (v.straps || []).filter(st => st.net !== 'VGND');
      const bad = [], noStrap = [];
      for (const i of Object.values(I)) {
        if (!i.supply) continue;
        const cx0 = i.rect[0], cx1 = i.rect[0] + i.rect[2];
        let best = null, bd = Infinity;
        for (const st of straps) { const d = Math.max(0, st.x - cx1, cx0 - (st.x + st.w)); if (d < bd) { bd = d; best = st; } }
        if (!best) continue;
        if (best.net !== i.supply) bad.push(`${i.name} (${i.supply}) nearest ${best.net} @ ${fmt(best.x, 1)}`);
      }
      for (const net of ['VAPWR', 'VDPWR']) if (Object.values(I).some(i => i.supply === net) && !straps.some(st => st.net === net)) noStrap.push(net);
      const ap = Object.values(I).filter(i => i.supply === 'VAPWR'), dp = Object.values(I).filter(i => i.supply === 'VDPWR');
      const sep = minGapShapes(ap.map(i => i.rect), dp.map(i => i.halo || i.rect));
      add(5, 'Supply domains', noStrap.length ? 'fail' : bad.length ? 'warn' : 'pass', `${cross.length} crossing${cross.length === 1 ? '' : 's'}`,
        (noStrap.length ? `No stripe for ${noStrap.join(', ')}. ` : '') +
        (bad.length ? `Nearest stripe on the other rail: ${bad.join('; ')}. ` : 'Every block\'s nearest supply stripe is its own rail. ') +
        `${cross.length} signals cross VAPWR ↔ VDPWR (3.3 V both, no level shifters; listed under Nets). Closest VAPWR ↔ VDPWR blocks ${fmt(sep, 1)} µm.`);
    }

    // 6. no digital or LO wire over the receiver
    if (rxInst.length) {
      const over = [];
      for (const n of nets) {
        if (!ok(n) || !NOT_OVER_RX.includes(n.cls)) continue;
        const own = [ownerOf(n.a), ownerOf(n.b)];
        for (const ri of rxInst) {
          if (own.includes(ri.name)) continue;
          if (n.segs.some(sg => segCrosses(sg, ri.rect, 0.6))) { over.push(`${n.name} over ${ri.cat.label || ri.name}`); break; }
        }
      }
      const ch = rxInst.filter(ri => chanSh.some(c => overlap(c, ri.rect) > 0)).map(ri => ri.cat.label || ri.name);
      add(6, 'No digital or LO wire over the RX', over.length || ch.length ? 'fail' : 'pass', over.length + ch.length ? `${over.length + ch.length}` : 'none',
        (over.length ? `Flylines over receiver blocks: ${over.slice(0, 12).join(', ')}${over.length > 12 ? ` and ${over.length - 12} more` : ''}. ` : 'No clock, digital, DAC, enable, TX or LO flyline crosses a receiver block (its own wires excepted). ') +
        (ch.length ? `The top channel runs over: ${ch.join(', ')}. ` : '') + 'The baseband and limiter AC-coupling nodes are ~60 MΩ.');
    } else add(6, 'No digital or LO wire over the RX', 'info', '-', 'Place the receiver.');

    // 7. short fine-tune bus
    {
      const d = DACN.map(q => netBy(q[0])).filter(ok), vg = netBy('vg'), vb = netBy('vbnf');
      if (d.length && ok(vg)) {
        const mx = Math.max(...d.map(n => n.len)), mean = d.reduce((t, n) => t + n.len, 0) / d.length;
        const st = [lvl(mx, s.r7, 2 * s.r7), lvl(vg.len, s.r7b, 3 * s.r7b)];
        add(7, 'Short fine-tune bus', st.includes('fail') ? 'fail' : st.includes('warn') ? 'warn' : 'pass', `${fmt(mx)} µm`,
          `37 DAC lines tx_fine → mdac: longest ${fmt(mx)}, mean ${fmt(mean)} µm (want ≤ ${s.r7}); mdac.vg → vco_top.vg ${fmt(vg.len)} µm (want ≤ ${s.r7b}); vbnf ${ok(vb) ? fmt(vb.len) : '-'} µm.`);
      } else add(7, 'Short fine-tune bus', 'info', '-', 'Place tx_fine, mdac and vco_top.');
    }

    // 8. the macro near the top edge, with a channel for the TT pins
    if (M) {
      const top = M.rect[1] + M.rect[3], gap = tile.h - top;
      const need = Math.max(0, ...chanSh.filter(c => c[0] < M.rect[0] + M.rect[2] && c[0] + c[2] > M.rect[0]).map(c => c[3]));
      const full = chanSh.length ? Math.max(...chanSh.map(c => c[3])) : 0;
      const inChan = Object.values(I).filter(i => i.name !== 'xmac' && chanSh.some(c => overlap(i.rect, c) > 0)).map(i => i.name);
      const st = inChan.length || gap + 1e-6 < need ? 'fail' : gap <= s.r8 ? 'pass' : 'warn';
      add(8, 'Macro near the top edge', st, `${fmt(gap, 1)} µm`,
        `Macro top ↔ tile top ${fmt(gap, 1)} µm (want ≤ ${s.r8}, and ≥ the channel over it, ${fmt(need, 1)} µm). The top channel is ${fmt(full, 1)} µm at its widest (${Math.round(full / s.track)} wires at ${s.track} µm).` +
        (inChan.length ? ` Blocks in the channel: ${inChan.join(', ')}.` : ''));
    }

    // 9. fit and spacing
    {
      const boxes = Object.values(I).map(i => ({ n: i.name, r: i.rect, halo: i.halo }))
        .concat(R.decaps.map(d => ({ n: d.name, r: d.rect, decap: true })), R.reserved.map(d => ({ n: d.label, r: d.rect, res: true })));
      const over = [], tight = [], outside = [];
      for (let i = 0; i < boxes.length; i++) {
        const a = boxes[i], r = a.r;
        if (!a.res && (r[0] < -1e-6 || r[1] < -1e-6 || r[0] + r[2] > tile.w + 1e-6 || r[1] + r[3] > tile.h + 1e-6)) outside.push(a.n);
        for (let j = i + 1; j < boxes.length; j++) {
          const b = boxes[j];
          if (a.res && b.res) continue;
          const ra = a.halo || r, rb = b.halo || b.r;
          if (overlap(ra, rb) > 0.01) over.push(`${a.n} / ${b.n}`);
          else if (!a.halo && !b.halo && !a.res && !b.res && rectGap(r, b.r) < s.keepout - 1e-3) tight.push(`${a.n} / ${b.n} ${fmt(rectGap(r, b.r), 1)}`);
        }
      }
      add(9, 'Fit and spacing', over.length || outside.length ? 'fail' : tight.length ? 'warn' : 'pass',
        over.length ? `${over.length} overlap${over.length > 1 ? 's' : ''}` : outside.length ? `${outside.length} outside` : tight.length ? `${tight.length} tight` : 'none',
        (over.length ? `Overlapping (macro halo counts): ${over.join(', ')}. ` : 'Overlaps: none. ') +
        (outside.length ? `Outside the tile: ${outside.join(', ')}. ` : '') +
        (tight.length ? `Closer than ${s.keepout} µm: ${tight.join(', ')}.` : `All gaps ≥ ${s.keepout} µm.`));
    }

    // 10. power stripes: clear Metal4 lanes; over the macro only on its own straps
    {
      const [y0, y1] = tile.stripe_y || [5, tile.h - 5], wmin = tile.stripe_min_w || 0.8;
      const issues = [], have = new Set();
      (v.straps || []).forEach((st, i) => {
        have.add(st.net);
        const lane = [st.x, y0, st.w, y1 - y0];
        for (const ins of Object.values(I)) {
          if (!ins.m4.some(r => overlap(lane, r) > 0)) continue;
          const onStrap = ins.straps.some(q => q.net === st.net && q.r[2] < 5 && st.x >= q.r[0] - 0.05 && st.x + st.w <= q.r[0] + q.r[2] + 0.05);
          if (!onStrap) issues.push(`${st.net} @ ${fmt(st.x, 1)} crosses ${ins.name}'s Metal4`);
        }
        if (st.w < wmin) issues.push(`${st.net} @ ${fmt(st.x, 1)} narrower than ${wmin} µm`);
        (v.straps || []).slice(i + 1).forEach(o => { if (rectGap([st.x, 0, st.w, 1], [o.x, 0, o.w, 1]) < 0.3) issues.push(`${st.net} / ${o.net} stripes touch`); });
      });
      const miss = ['VDPWR', 'VAPWR', 'VGND'].filter(n => !have.has(n));
      add(10, 'Power stripes', issues.length ? 'fail' : miss.length ? 'warn' : 'pass',
        issues.length ? `${issues.length} blocked` : miss.length ? `no ${miss.join(', ')}` : `${(v.straps || []).length} clear`,
        issues.length ? issues.join('; ') + '.' : `${(v.straps || []).length} Metal4 stripe(s) (y ${y0}–${y1}), every lane clear; over the macro only on its own straps.` + (miss.length ? ` No stripe for ${miss.join(', ')}.` : ''));
    }

    // 11. vco_top split: its bias wires (vbnf: the filtered DAC-gate bias; vctrl: the fine-tune node) are short and
    // away from the macro and the clocks. Inside vco_top they are abutments, with no wire.
    if (R.vmode === 'parts') {
      const vb = netBy('vbnf ref'), vc = netBy('vctrl ring');
      if (ok(vb) && ok(vc)) {
        const m = Math.max(vb.len, vc.len), aggr = nets.filter(n => ok(n) && AGGR.includes(n.cls));
        const d = Math.min(minGapShapes(segsOf([vb, vc]), segsOf(aggr)), M ? minGapShapes(segsOf([vb, vc]), [M.halo]) : Infinity);
        const st = lvl(m, s.r11, 3 * s.r11);
        add(11, 'VCO bias wires (vco_top split)', st === 'pass' && d < s.r11d ? 'warn' : st, `${fmt(m)} µm`,
          `cgm_ref → ring: vbnf ${fmt(vb.len)} µm, vctrl ${fmt(vc.len)} µm (want ≤ ${s.r11}); closest macro / clock / DAC wire ${fmt(d)} µm (want ≥ ${s.r11d}). Inside vco_top both are abutments with no wire; noise on them is FM.` + estNote([vc]));
      } else add(11, 'VCO bias wires (vco_top split)', 'info', '-', 'Place the ring + lsdiv unit and cgm_ref.');
    }

    // decap (info: no target set yet)
    for (const [n, d] of Object.entries(DECAPS)) {
      const ds = R.decaps.filter(x => x.base === n), a = ds.reduce((t, x) => t + area(x.rect), 0);
      add('D', `Decap ${d.net}`, 'info', `≈ ${fmt(DECAP_FF * a / 1000, 1)} pF`, `${fmt(a)} µm² in ${ds.length} rectangle(s), at ~${DECAP_FF} fF/µm² (nfet gate cap). Blocks carry their own: vco_top 10 pF on VDD_LS, rx_decap in the receiver.`);
    }
    if (missing.length) add('-', 'Unplaced blocks', 'warn', `${missing.length}`, missing.join(', '));

    const tileA = tile.w * tile.h;
    const blocks = Object.values(I).reduce((t, i) => t + i.w * i.h, 0);
    const macro = M ? M.w * M.h : 0, rx = rxInst.reduce((t, i) => t + i.w * i.h, 0);
    const dec = R.decaps.reduce((t, d) => t + area(d.rect), 0);
    const areaInfo = { tile: tileA, macro, rx, other: blocks - macro - rx, decap: dec, spacing: 0.1 * blocks, free: tileA - blocks - dec };
    return { checks: res, nets, R, area: areaInfo, settings: s, channelShapes: chanSh, crossings: cross };
  }

  // Pin fitting (ported from the OOK page's pinfit.js): move a block's signal pins to the point of its edge facing
  // what they connect to, spread them >= 1 um apart along each edge, and order each edge like the pins at the other
  // end, so the flylines don't cross. Returns a new v.pins for the named blocks (others keep theirs). Floorplanning
  // only: a moved pin needs the block re-laid out (the macro: a new pin_order.cfg).
  function fitPins(data, cat, v, names) {
    const tile = data.tile, out = JSON.parse(JSON.stringify(v.pins || {})), vv = Object.assign({}, v, { pins: out });
    const R0 = resolve(cat, v), sel = new Set(names.filter(n => R0.inst[n]));
    for (const n of sel) out[n] = {};
    const split = ref => { const i = ref.lastIndexOf('.'); return [ref.slice(0, i), ref.slice(i + 1)]; };
    const peers = {};
    for (const [, , a0, b0] of netList(R0.mode, R0.vmode)) {
      const a = resolveRef(a0, R0.mode, R0.vmode), b = resolveRef(b0, R0.mode, R0.vmode);
      (peers[a] = peers[a] || []).push(b); (peers[b] = peers[b] || []).push(a);
    }
    const pos = (R, ref) => { if (ref.startsWith('pad:')) { const p = tile.pins[ref.slice(4)]; return p ? [(p.x0 + p.x1) / 2, p.y0 < 1 ? 0 : tile.h] : null; }
      const [n, p] = split(ref), i = R.inst[n]; return i && i.pins[p] ? i.pins[p].at : null; };
    const toLocal = (ins, pt) => {
      const o = mapPt(ins.pl, ins.w, ins.h, 0, 0), ex = mapPt(ins.pl, ins.w, ins.h, 1, 0), ey = mapPt(ins.pl, ins.w, ins.h, 0, 1);
      const a = ex[0] - o[0], b = ey[0] - o[0], c = ex[1] - o[1], d = ey[1] - o[1], det = a * d - b * c, dx = pt[0] - o[0], dy = pt[1] - o[1];
      return [(d * dx - b * dy) / det, (-c * dx + a * dy) / det];
    };
    const refs = Object.keys(peers).filter(r => !r.startsWith('pad:') && sel.has(split(r)[0]) && !PWR_PIN.test(split(r)[1]));
    for (let pass = 0; pass < 4; pass++) for (const ref of refs) {
      const R = resolve(cat, vv), [n, p] = split(ref), ins = R.inst[n];
      const ts = peers[ref].map(q => pos(R, q)).filter(Boolean);
      if (!ts.length) continue;
      const t = [ts.reduce((s, q) => s + q[0], 0) / ts.length, ts.reduce((s, q) => s + q[1], 0) / ts.length];
      const [lx, ly] = toLocal(ins, t), w = ins.w, h = ins.h, in_ = 0.25, cm = 1.0;
      const ox = lx < 0 ? -lx : lx > w ? lx - w : 0, oy = ly < 0 ? -ly : ly > h ? ly - h : 0;
      let x = Math.min(w - cm, Math.max(cm, lx)), y = Math.min(h - cm, Math.max(cm, ly));
      if (oy > 0 && oy >= ox) y = ly < 0 ? in_ : h - in_;
      else if (ox > 0) x = lx < 0 ? in_ : w - in_;
      else { const m = Math.min(lx, w - lx, ly, h - ly); if (m === lx) x = in_; else if (m === w - lx) x = w - in_; else if (m === ly) y = in_; else y = h - in_; }
      out[n][p] = { x, y };
    }
    const R = resolve(cat, vv);
    for (const n of sel) {
      const ins = R.inst[n], ps = out[n], groups = {};
      for (const [p, q] of Object.entries(ps)) { const e = q.y <= 0.3 ? 'S' : q.y >= ins.h - 0.3 ? 'N' : q.x <= 0.3 ? 'W' : 'E'; (groups[e] = groups[e] || []).push(p); }
      for (const [e, arr] of Object.entries(groups)) {
        const k = e === 'W' || e === 'E' ? 'y' : 'x', ki = k === 'x' ? 0 : 1, L = k === 'x' ? ins.w : ins.h;
        // order along the edge like the far ends, then spread >= 1 um apart and keep inside the edge
        const key = p => { const ts = (peers[`${n}.${p}`] || []).map(q => pos(R, q)).filter(Boolean).map(q => toLocal(ins, q)[ki]); return ts.length ? ts.reduce((a, b) => a + b, 0) / ts.length : ps[p][k]; };
        const slots = arr.map(p => ps[p][k]).sort((a, b) => a - b), order = arr.slice().sort((a, b) => key(a) - key(b));
        order.forEach((p, i) => { ps[p][k] = slots[i]; });
        for (let i = 1; i < order.length; i++) if (ps[order[i]][k] < ps[order[i - 1]][k] + 1) ps[order[i]][k] = ps[order[i - 1]][k] + 1;
        const over = order.length ? ps[order[order.length - 1]][k] - (L - 1) : 0;
        if (over > 0) for (const p of order) ps[p][k] -= over;
        for (const p of order) { ps[p].x = +ps[p].x.toFixed(2); ps[p].y = +ps[p].y.toFixed(2); }
      }
    }
    return out;
  }
  const PWR_PIN = /^(VDD|VSS|VDD_LS|VAPWR|VDPWR|VGND)$/;

  // floorplan.json
  function exportJSON(data, cat, v, settings) {
    const ev = evaluate(data, cat, v, settings), R = ev.R, blocks = [];
    for (const i of Object.values(R.inst)) {
      const [k, m] = ORIENTS[i.pl.orient];
      const b = { inst: i.name, cell: i.cat.cell, x: +i.rect[0].toFixed(3), y: +i.rect[1].toFixed(3), orient: i.pl.orient,
        rot: k * 90, mirror: m, w: +i.rect[2].toFixed(3), h: +i.rect[3].toFixed(3), supply: i.supply };
      if (i.cat.glue) b.note = i.cat.note;
      if (i.reshaped) { b.own_w = +i.w.toFixed(3); b.own_h = +i.h.toFixed(3); b.note = `${i.cat.reshape ? 're-harden' : 're-layout'} at ${i.w.toFixed(2)} x ${i.h.toFixed(2)} um (now ${i.cat.w} x ${i.cat.h})`; }
      blocks.push(b);
    }
    for (const d of R.decaps) blocks.push({ inst: d.base, part: d.idx + 1, cell: d.def.cell, x: d.rect[0], y: d.rect[1], w: d.rect[2], h: d.rect[3], orient: 'R0', rot: 0, mirror: false, estimate: true, supply: d.def.net });
    return {
      variant: v.name, note: v.note || '', tile: { w: data.tile.w, h: data.tile.h, source: data.tile.source }, rx: R.mode, vco: R.vmode, blocks,
      reserved: (v.reserved || []).map(r => Object.assign({}, r)),
      pins_moved: Object.fromEntries(Object.entries(v.pins || {}).filter(([, ps]) => Object.keys(ps).length).map(([i, ps]) => [i, Object.fromEntries(Object.entries(ps).map(([p, q]) => [p, [+q.x.toFixed(2), +q.y.toFixed(2)]]))])),
      straps: (v.straps || []).map(s => ({ net: s.net, x: s.x, w: s.w })),
      crossings: ev.crossings,
      transform: 'x, y = lower-left of the placed bbox. KLayout: t = DCplxTrans(1, rot, mirror, 0, 0); bb = cell.dbbox().transformed(t); place with DCplxTrans(1, rot, mirror, x - bb.left, y - bb.bottom).',
    };
  }
  function importJSON(cat, j) {
    const v = { name: j.variant || 'Imported', note: j.note || '', rx: j.rx === 'cells' ? 'cells' : 'block', vco: j.vco === 'parts' ? 'parts' : 'block', place: {}, decaps: {}, est: {},
      straps: (j.straps || []).map(s => ({ net: s.net, x: +s.x, w: +s.w })), reserved: (j.reserved || []).map(r => Object.assign({}, r)) };
    if (j.pins_moved) { v.pins = {}; for (const [i, ps] of Object.entries(j.pins_moved)) { if (!cat[i]) continue; v.pins[i] = {}; for (const [p, xy] of Object.entries(ps)) v.pins[i][p] = { x: +xy[0], y: +xy[1] }; } }
    for (const b of j.blocks || []) {
      if (DECAPS[b.inst]) { (v.decaps[b.inst] = v.decaps[b.inst] || []).push({ x: +b.x, y: +b.y, w: +b.w, h: +b.h }); continue; }
      const n = b.inst, c = cat[n];
      if (!c) continue;
      v.place[n] = { x: +b.x, y: +b.y, orient: ORIENTS[b.orient] ? b.orient : 'R0' };
      if (!c.glue && b.w && b.h) {
        const [w, h] = ORIENTS[v.place[n].orient][0] % 2 ? [+b.h, +b.w] : [+b.w, +b.h];
        if (Math.abs(w - c.w) > 1e-3 || Math.abs(h - c.h) > 1e-3) { v.est[n] = { w }; if (Math.abs(w * h - c.w * c.h) > 1) v.est[n].area = w * h; }
      }
    }
    return v;
  }

  root.FP = { ORIENTS, placedSize, mapPt, mapRect, compose, buildCatalog, DECAPS, DECAP_FF, NETS, RX_NETS, NET_CLASSES, DEFAULT_SETTINGS,
    resolve, routeNets, evaluate, exportJSON, importJSON, rectGap, overlap, channelShapes, rxMode, vcoMode, inMode, resolveRef, RX_CELLS, VCO_NETS, fitPins };
})(typeof window !== 'undefined' ? window : globalThis);
