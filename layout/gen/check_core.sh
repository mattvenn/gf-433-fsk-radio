#!/bin/bash
# vco_core (ring_core_v3 + lsdiv + the Q-tap level shifter rx_lsq_ls + the VDD_LS decap fingers; the tile's split of
# vco_top) checks. A copy of check_top.sh with the LVS source cut down from the same xschem vco_top netlist:
#   1. netlist xschem/vco_top.sch and xschem/rx_lsq.sch headless -> <outdir>/xsch/; LVS source vco_core_lvs.spice =
#      vco_top's netlist with the vco_top subckt replaced by vco_core (ports VDD VDD_LS VSS vctrl bit0-4 bitb0-4 ck vg
#      ls vbnf lsq vq; xcore and xls as in vco_top; xlsq = rx_lsq_ls on a2 (rx_lsq.split_source()); the VDD_LS
#      decap as drawn, 6 x W 13.0 / L 10 um: XDCU m=6; no xref, no main decap group), the cgm_ref subckt dropped, and
#      ls_ac's "Cc a0 net1 2e-15" removed (metal fingers, parasitic C; check_lsdiv.sh). No n-well resistor here.
#   2. magic DRC (hierarchical), flattened LVS extraction (flatten -dotoplabels: only vco_core's labels, so the blocks'
#      VDD labels can't merge VDD and VDD_LS), antenna on a flattened copy, KLayout DRC (feol + beol, rules run > 0).
#   3. netgen LVS; 4. lsdiv R1 size; 5. no Metal4/5;
#   6. mutations (each must FAIL): XDCU m 6 -> 5, xls supply VDD_LS -> VDD, xls ck <-> ls, xcore vbnf <-> vctrl,
#      xlsq vq <-> lsq, XR1 r_length 159.125 -> 140 um (resistor check);
#   7. the block port map from a hierarchical extraction (the Q level shifter's aq on the ring's a2, lsdiv's a0
#      abutment, supplies), with six wrong expectations that must FAIL. netgen can't place a2: without ls_ac's Cc the
#      ring is rotation-symmetric (no device of either level shifter is on its input).
# Usage: bash layout/gen/check_core.sh [gds] [outdir]     defaults: layout/vco_core.gds build/vco_tile/check_core
set -u
REPO=$(pwd)
GDS=$(realpath "${1:-layout/vco_core.gds}")
OUT=${2:-build/vco_tile/check_core}
B=vco_core
SKIP=${SKIP:-}
mkdir -p "$OUT/xsch"; OUT=$(realpath "$OUT")
export PDK_ROOT=${PDK_ROOT:-/foss/pdks} PDK=gf180mcuD
SETUP=$PDK_ROOT/$PDK/libs.tech/netgen/${PDK}_setup.tcl
RC=$PDK_ROOT/$PDK/libs.tech/magic/$PDK.magicrc

# ---- 1. schematic netlist + LVS copy ----
NL=$(bash xschem/gen/netlist.sh xschem "$OUT/xsch" vco_top rx_lsq) || { echo "netlist failed: $NL"; exit 1; }
SRC0=$OUT/xsch/vco_top.spice
SRC=$OUT/xsch/vco_core_lvs.spice
python3 -c "import sys; sys.path.insert(0, 'layout/gen'); import vco_core; open(sys.argv[3], 'w').write(vco_core.lvs_source(open(sys.argv[1]).read(), open(sys.argv[2]).read()))" "$SRC0" "$OUT/xsch/rx_lsq.spice" "$SRC"
[ $? -eq 0 ] || { echo "LVS copy edits did not apply"; exit 1; }

cd "$OUT"
: > summary.txt
log() { echo "$*" | tee -a summary.txt; }
log "gds $GDS  top $B  magic $(magic --version)  netgen $(netgen -batch quit 2>/dev/null | grep -o 'Netgen [0-9.]*' | head -1)  klayout $(klayout -v)"
log "== schematic: xschem/vco_top.sch + rx_lsq.sch; $NL; LVS source: vco_core cut from vco_top ($(grep -c '^Cc a0 ' "$SRC") Cc lines left, $(grep -c '^xref' "$SRC") xref, $(grep -c '^XDCU' "$SRC") XDCU, $(grep -c '^xlsq' "$SRC") xlsq)"

echo "load vco_core" > rnwfix.tcl   # (no rnw here; makes vco_core the current cell after gds read)

# ---- 5. no Metal4 / Metal5 ----
m45=$(python3 - "$GDS" <<'PYEOF'
import sys, klayout.db as db
ly = db.Layout(); ly.read(sys.argv[1]); t = ly.top_cell()
bad = []
for li in ly.layer_indexes():
    i = ly.get_info(li)
    if (i.layer, i.datatype) in ((46, 0), (81, 0), (41, 0), (82, 0)) and not db.Region(t.begin_shapes_rec(li)).is_empty():
        bad.append(f"{i.layer}/{i.datatype}")
print("none" if not bad else "FOUND " + " ".join(bad))
PYEOF
)
log "== Metal4 (46/0), via3 (41/0), Metal5 (81/0), via4 (82/0) in the GDS: $m45"
m45_ok=0; [ "$m45" = none ] && m45_ok=1

# ---- 2a. magic DRC (hierarchical) + flattened LVS extraction ----
{
echo "gds read $GDS"
cat rnwfix.tcl
cat <<'TCL'
select top cell
drc euclidean on
drc style drc(full)
drc check
drc catchup
set fp [open magic_drc.txt w]
puts $fp "count [drc list count total]"
set sc [cif scale out]
foreach {why boxes} [drc listall why] {
  set loc {}
  foreach b [lrange $boxes 0 2] { lappend loc [lmap v $b {format %.2f [expr {$v * $sc}]}] }
  puts $fp "[llength $boxes]  $why   at $loc"
}
close $fp
flatten -dotoplabels vco_core_flat
load vco_core_flat
cellname delete vco_core
cellname rename vco_core_flat vco_core
select top cell
extract do local
extract all
ext2spice lvs
ext2spice cthresh infinite
ext2spice -o vco_core_lay.spice
feedback save extract_feedback.txt
quit -noprompt
TCL
} > magic.tcl
t0=$(date +%s)
magic -dnull -noconsole -rcfile $RC magic.tcl > magic.log 2>&1
log "== magic DRC ($(( $(date +%s) - t0 )) s incl. extraction): $(head -1 magic_drc.txt)"; tail -n +2 magic_drc.txt | head -20 | tee -a summary.txt
log "   layout netlist: $(grep -c '^X' vco_core_lay.spice) X devices; ports: $(grep -m1 '^.subckt' vco_core_lay.spice | cut -d' ' -f3- )"

# ---- 2b. antenna: flattened copy, fresh session ----
if [[ $SKIP != *antenna* ]]; then
mkdir -p ant
{
echo "gds read $GDS"
cat rnwfix.tcl
cat <<'TCL'
flatten vco_core_flat
load vco_core_flat
select top cell
extract do local
extract all
puts "ANTENNA_BEGIN"
antennacheck debug
antennacheck
puts "FEEDBACK [feedback count]"
puts "ANTENNA_END"
quit -noprompt
TCL
} > ant/ant.tcl
t0=$(date +%s)
(cd ant && magic -dnull -noconsole -rcfile $RC ant.tcl > ../antenna.log 2>&1)
sed -n '/ANTENNA_BEGIN/,/ANTENNA_END/p' antenna.log > antenna.txt
log "== antenna ($(( $(date +%s) - t0 )) s): violations $(grep -ci 'violation' antenna.txt), feedback $(grep FEEDBACK antenna.txt | cut -d' ' -f2)"
grep -i -A1 'violation' antenna.txt | head -8 | tee -a summary.txt
fi

# ---- 2c. KLayout DRC (PDK deck, FEOL + BEOL) ----
if [[ $SKIP != *klayout* ]]; then
t0=$(date +%s)
klayout -b -r $PDK_ROOT/$PDK/libs.tech/klayout/tech/drc/gf180mcu.drc -rd input=$GDS -rd topcell=$B \
  -rd report=$OUT/klayout_drc.lyrdb -rd variant=D -rd run_mode=deep -rd threads=8 -rd decks=${KLDECKS:-all,-density} -rd feol=true -rd beol=true \
  > klayout_drc.log 2>&1
python3 - "$OUT/klayout_drc.lyrdb" <<'PYEOF' | tee klayout_drc_summary.txt
import sys, xml.etree.ElementTree as ET, collections
r = ET.parse(sys.argv[1]).getroot()
c = collections.Counter(i.findtext('category') for i in r.iter('item'))
print('count', sum(c.values()))
for k, v in c.most_common(): print(' ', v, k)
PYEOF
log "== KLayout DRC ($(( $(date +%s) - t0 )) s), decks ${KLDECKS:-all,-density}, $(grep -o 'executing [0-9]* deck(s)\|Running all [A-Z]* rules' klayout_drc.log | tr '\n' ' ') rules run $(grep -c 'Executing rule' klayout_drc.log): $(head -1 klayout_drc_summary.txt)"
tail -n +2 klayout_drc_summary.txt | head -20 >> summary.txt
fi

# ---- 3. netgen LVS ----
lvs() {  # lvs <a> <cell_a> <b> <cell_b> <tag>  -> 0 if "match uniquely" with no property errors
  netgen -batch lvs "$1 $2" "$3 $4" $SETUP $5.report > $5.log 2>&1
  grep -q "Final result: Circuits match uniquely" $5.report && ! grep -qi "property errors" $5.report \
    && ! grep -qi "do not match" $5.report && ! grep -qi "failed pin matching" $5.report
}
why() { grep -E "Final result|roperty errors|do not match|pin matching" $1.report | sort -u | tr '\n' ' '; }
t0=$(date +%s)
if lvs vco_core_lay.spice $B "$SRC" vco_core lvs; then r=PASS; else r=FAIL; fi
log "== LVS ($(( $(date +%s) - t0 )) s):"
grep -E "Circuits match|do not match|Netlists match|Final result|roperty errors|failed pin|disconnected" lvs.report | sort -u | tail -6 | tee -a summary.txt
log "LVS $r"

# ---- 4. resistor sizes (black boxes in netgen) ----
rsize() {  # rsize <source.spice> -> PASS/FAIL line
python3 - "$1" vco_core_lay.spice <<'PYEOF'
import re, sys
SUF = dict(m=1e-3, u=1e-6, n=1e-9, p=1e-12, f=1e-15)
MODELS = ("nwell", "nplus_u", "ppolyf_u_1k")
def num(v):
    m = re.fullmatch(r"([-+\d.eE]+?)([munpf]?)", v.strip())
    return float(m.group(1)) * SUF.get(m.group(2), 1)
def res(path):
    """Every resistor of the netlist, flattened from its first .subckt named vco_core (each subckt instance counts:
    lsdiv and the Q level shifter rx_lsq_ls each hold one ls_ac with its R1)."""
    txt = re.sub(r"\n\+", " ", open(path).read())
    subs, cur = {}, None
    for ln in txt.splitlines():
        t = ln.split()
        if t and t[0].lower() == ".subckt":
            cur = subs.setdefault(t[1], [])
        elif t and t[0].lower() == ".ends":
            cur = None
        elif cur is not None and t and t[0][:1] in "Xx":
            cur.append(t)
    def walk(name):
        out = []
        for t in subs.get(name, []):
            model = [x for x in t[1:] if "=" not in x][-1]
            if model in MODELS:
                kv = dict(x.split("=", 1) for x in t if "=" in x)
                out.append((model, num(kv["r_width"]), num(kv["r_length"])))
            elif model in subs:
                out += walk(model)
        return out
    return sorted(walk("vco_core"))
src, lay = res(sys.argv[1]), res(sys.argv[2])
ok = len(src) == len(lay)
txt = []
for s, l in zip(src, lay):
    good = s[0] == l[0] and abs(s[1] / l[1] - 1) < 1e-3 and abs(s[2] / l[2] - 1) < 0.01
    ok &= good
    txt.append(f"{s[0]} src {s[1]*1e6:.4g}/{s[2]*1e6:.6g} lay {l[1]*1e6:.4g}/{l[2]*1e6:.6g} um ({(l[2]/s[2]-1)*100:+.3f} % L)"
               + ("" if good else " BAD"))
print(("PASS" if ok else "FAIL") + f"  {len(src)} source / {len(lay)} layout: " + "; ".join(txt))
PYEOF
}
rs=$(rsize "$SRC")
log "== resistor size check (w/l): $rs"
rs_ok=0; [[ $rs == PASS* ]] && rs_ok=1

# ---- 6. mutation tests (reuse the layout extraction) ----
mut_ok=1
mutate() {  # mutate <tag> <sed expr> <description>
  sed -e "$2" "$SRC" > xsch/$1.spice
  if cmp -s "$SRC" xsch/$1.spice; then log "== mutation $3: NOT APPLIED (BAD)"; mut_ok=0; return; fi
  if lvs vco_core_lay.spice $B xsch/$1.spice vco_core $1; then
    log "== mutation $3: PASS (BAD: not caught)"; mut_ok=0
  else log "== mutation $3: FAIL (expected)  [$(why $1)]"; fi
}
mutate lvs_mut_m   '/^XDCU /s/m=6$/m=5/'                      "XDCU m 6 -> 5 (one VDD_LS decap finger)"
mutate lvs_mut_q   '/^xlsq /s/^xlsq vq VSS a2 lsq /xlsq lsq VSS a2 vq /' "xlsq vq <-> lsq (Q level shifter supply / output)"
mutate lvs_mut_sup '/^xls /s/^xls VDD_LS /xls VDD /'          "xls supply VDD_LS -> VDD (supplies merged)"
mutate lvs_mut_a2  '/^xls /s/ a0 ck ls lsdiv$/ a0 ls ck lsdiv/' "xls ck <-> ls"
mutate lvs_mut_vb  '/^xcore /s/^xcore VDD VSS vbnf vctrl /xcore VDD VSS vctrl vbnf /' "xcore vbnf <-> vctrl"
sed -e '/^XR1 /s/r_length=159.125e-6/r_length=140.0e-6/' "$SRC" > xsch/res_mut.spice
if cmp -s "$SRC" xsch/res_mut.spice; then log "== mutation XR1 L 159.125 -> 140: NOT APPLIED (BAD)"; mut_ok=0
else
  r=$(rsize xsch/res_mut.spice)
  if [[ $r == PASS* ]]; then log "== mutation XR1 r_length 159.125 -> 140 um: PASS (BAD: not caught)"; mut_ok=0
  else log "== mutation XR1 r_length 159.125 -> 140 um: FAIL (expected)  [${r:0:200}]"; fi
fi

# ---- 7. which ring node is the a2 pin? (LVS can't tell: with lsdiv's Cc removed from the source, the 5-stage ring
#      is rotation-symmetric and netgen resolves the symmetry by pin name; a2 <-> a0 / a1 / a3 / a4 swaps all "match").
#      A hierarchical magic extraction gives each block instance's port -> top-level net map; check it.
mkdir -p hier
cat > hier/h.tcl <<TCL
gds read $GDS
load vco_core
select top cell
extract all
ext2spice lvs
ext2spice hierarchy on
ext2spice -o hier.spice
quit -noprompt
TCL
(cd hier && magic -dnull -noconsole -rcfile $RC h.tcl > h.log 2>&1)
pmap() {  # pmap <expect "inst.port=net ..."> -> PASS/FAIL line
python3 - hier/hier.spice "$1" <<'PYEOF'
import re, sys
t = re.sub(r"\n\+", " ", open(sys.argv[1]).read())
ports = {m.group(1): m.group(2).split() for m in re.finditer(r"^\.subckt (\S+) (.*)$", t, flags=re.M)}
top = re.search(r"^\.subckt vco_core .*?^\.ends", t, flags=re.M | re.S).group(0)
conn = {}
for ln in top.splitlines():
    if ln.startswith("X"):
        f = ln.split(); cell = f[-1]; nets = f[1:-1]
        conn[cell] = dict(zip(ports[cell], nets))
bad = []
for e in sys.argv[2].split():
    k, net = e.split("="); cell, port = k.split(".")
    got = conn.get(cell, {}).get(port)
    if got != net:
        bad.append(f"{k}: {got} (want {net})")
print(("PASS" if not bad else "FAIL") + "  " + ("; ".join(bad) if bad else sys.argv[2]))
PYEOF
}
EXP="ring_core.a2=a2 rx_lsq_ls.aq=a2 ring_core.a0=a0 lsdiv.a0=a0 rx_lsq_ls.vq=vq rx_lsq_ls.lsq=lsq rx_lsq_ls.VSS=VSS ring_core.vctrl=vctrl ring_core.vbn=vbnf ring_core.vg=vg ring_core.VDD=VDD lsdiv.VDD=VDD_LS lsdiv.ck=ck lsdiv.ls=ls ring_core.bit2=bit2 ring_core.bitb2=bitb2"
pm=$(pmap "$EXP")
log "== block port map (hierarchical extraction): $pm"
pm_ok=0; [[ $pm == PASS* ]] && pm_ok=1
for wrong in "ring_core.a1=a2" "ring_core.a3=a2" "ring_core.a4=a2" "lsdiv.VDD=VDD" "rx_lsq_ls.aq=a0" "rx_lsq_ls.vq=VDD_LS"; do
  r=$(pmap "$wrong")
  if [[ $r == PASS* ]]; then log "== mutation port map $wrong: PASS (BAD: not caught)"; mut_ok=0
  else log "== mutation port map $wrong: FAIL (expected)  [$r]"; fi
done

lvs_ok=0; grep -q "^LVS PASS" summary.txt && lvs_ok=1
drc_ok=0; grep -q "^== magic DRC.*: count 0$" summary.txt && grep -q "^== KLayout DRC.*rules run [1-9][0-9]*: count 0$" summary.txt && drc_ok=1
[[ ${SKIP:-} == *klayout* ]] && grep -q "^== magic DRC.*: count 0$" summary.txt && drc_ok=1
ant_ok=1; [[ ${SKIP:-} != *antenna* ]] && ! grep -q "^== antenna.*violations 0," summary.txt && ant_ok=0
log "CHECK $([ $lvs_ok$drc_ok$ant_ok$rs_ok$mut_ok$m45_ok$pm_ok = 1111111 ] && echo OK || echo FAIL)  (LVS vs xschem $lvs_ok, DRC $drc_ok, antenna $ant_ok, resistor sizes $rs_ok, mutations caught $mut_ok, no Metal4/5 $m45_ok, block port map $pm_ok)"
