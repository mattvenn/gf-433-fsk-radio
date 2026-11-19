#!/bin/bash
# Checks for one receiver layout cell, with its xschem schematic as the LVS source (modelled on check_tx.sh +
# check_v2.sh; run from the repo root, in the image):
#   1. netlist xschem/<cell>.sch headless (xschem/gen/netlist.sh) -> <outdir>/xsch/<cell>.spice
#   2. magic DRC (full), KLayout DRC (PDK deck, variant D, feol=true beol=true; the summary counts the rules that
#      ran), magic antenna on a flattened copy, netgen LVS (fails on property errors)
#   3. device sizes: layout/gen/rx_sizes.py diffs every MOS W / L and every resistor W / L of the extraction
#      against the sim netlister (netgen black-boxes the PDK resistors)
#   4. mutations: two broken copies of the LVS source (one m / W, one gate connection) must both FAIL
# Usage: bash layout/gen/check_rx_block.sh <cell> [gds] [outdir]     (gds default layout/<cell>.gds)
#   SKIP=klayout,antenna   THREADS=4 (KLayout)   ANT_GDS=<gds with a deliberate antenna violation> (proof run)
# Results: <outdir>/summary.txt (last line CHECK OK / CHECK FAIL)
set -u
B=$1
REPO=$(pwd)
GDS=$(realpath "${2:-layout/$B.gds}")
[ -s "$GDS" ] || { echo "no GDS $GDS"; exit 1; }
OUT=${3:-build/rx_layout/check/$B}
SKIP=${SKIP:-}
THREADS=${THREADS:-4}
mkdir -p "$OUT/xsch"; OUT=$(realpath "$OUT")
export PDK_ROOT=${PDK_ROOT:-/foss/pdks} PDK=gf180mcuD
RC=$PDK_ROOT/$PDK/libs.tech/magic/$PDK.magicrc
SETUP=$PDK_ROOT/$PDK/libs.tech/netgen/${PDK}_setup.tcl
NICE="nice -n 19"

case $B in
  # the I/Q-symmetric split of rx_lsq (layout/gen/rx_lsq.py --part ls / hdr): the source is xschem's rx_lsq cut in two
  # by rx_lsq.split_source() (the level shifter rx_lsq_ls goes into vco_core, the header rx_lsq_hdr stays in the tile)
  rx_lsq_ls|rx_lsq_hdr)
    NL=$(bash xschem/gen/netlist.sh xschem "$OUT/xsch" rx_lsq) || { echo "netlist failed: $NL"; exit 1; }
    python3 -c "import sys; sys.path.insert(0, 'layout/gen'); import rx_lsq; open(sys.argv[2], 'w').write(rx_lsq.split_source(open(sys.argv[1]).read()))" \
      "$OUT/xsch/rx_lsq.spice" "$OUT/xsch/$B.spice" || { echo "split_source failed"; exit 1; }
    NL="$NL; split by rx_lsq.split_source()" ;;
  *) NL=$(bash xschem/gen/netlist.sh xschem "$OUT/xsch" $B) || { echo "netlist failed: $NL"; exit 1; } ;;
esac
SRC=$OUT/xsch/${B}_lvs.spice
# one line per device (for the mutations); lsdiv's level shifter (ls_ac) has "Cc a0 net1 2e-15": Cc is drawn as
# M2 / M3 metal fingers, which extract as parasitic C, not a device, so (as layout/gen/check_lsdiv.sh) the LVS copy
# drops that line (its value is checked by the extraction)
sed -e ':a;N;$!ba;s/\n+/ /g' "$OUT/xsch/$B.spice" | sed -e '/^Cc a0 /d' > "$SRC"
ncc=$(grep -c '^Cc a0 ' "$OUT/xsch/$B.spice")

cd "$OUT"
: > summary.txt
log() { echo "$*" | tee -a summary.txt; }
log "gds $GDS  top $B  source $SRC  magic $(magic --version)  klayout $(klayout -v)  $(date -Iseconds)"
log "== schematic: xschem/$B.sch; $NL; LVS copy: removed $ncc 'Cc a0' metal-finger cap line(s)"

# ---- magic DRC + LVS extraction ----
cat > magic.tcl <<EOF
gds read $GDS
load $B
select top cell
drc euclidean on
drc style drc(full)
drc check
drc catchup
set fp [open magic_drc.txt w]
puts \$fp "count [drc list count total]"
set sc [cif scale out]
foreach {why boxes} [drc listall why] {
  set loc {}
  foreach b [lrange \$boxes 0 2] { lappend loc [lmap v \$b {format %.2f [expr {\$v * \$sc}]}] }
  puts \$fp "[llength \$boxes]  \$why   at \$loc"
}
close \$fp
extract do local
extract unique notopports
extract all
ext2spice lvs
ext2spice cthresh infinite
ext2spice -o ${B}_lay.spice
feedback save extract_feedback.txt
quit -noprompt
EOF
t0=$(date +%s)
$NICE magic -dnull -noconsole -rcfile $RC magic.tcl > magic.log 2>&1
log "== magic DRC ($(( $(date +%s) - t0 )) s): $(head -1 magic_drc.txt)"; tail -n +2 magic_drc.txt | head -20 | tee -a summary.txt

# ---- antenna: flattened copy, fresh session ----
antenna() {   # $1 gds, $2 outdir
mkdir -p $2; ( cd $2
cat > ant.tcl <<EOF
gds read $1
load $B
flatten ${B}_flat
load ${B}_flat
select top cell
extract do local
extract all
puts "ANTENNA_BEGIN"
antennacheck debug
antennacheck
puts "FEEDBACK [feedback count]"
puts "ANTENNA_END"
quit -noprompt
EOF
$NICE magic -dnull -noconsole -rcfile $RC ant.tcl > antenna.log 2>&1
sed -n '/ANTENNA_BEGIN/,/ANTENNA_END/p' antenna.log > antenna.txt )
}
if [[ $SKIP != *antenna* ]]; then
  t0=$(date +%s)
  antenna $GDS ant; cp ant/antenna.txt antenna.txt
  log "== antenna ($(( $(date +%s) - t0 )) s): violations $(grep -ci 'violation' antenna.txt), feedback $(grep FEEDBACK antenna.txt | cut -d' ' -f2)"
  grep -i -A1 'violation' antenna.txt | head -8 | tee -a summary.txt
  if [ -n "${ANT_GDS:-}" ]; then
    antenna $(realpath $ANT_GDS) ant_proof
    log "== antenna proof run on $(basename $ANT_GDS) (a deliberate violation): violations $(grep -ci 'violation' ant_proof/antenna.txt)"
  fi
fi

# ---- KLayout DRC ----
if [[ $SKIP != *klayout* ]]; then
  t0=$(date +%s)
  $NICE klayout -b -r $PDK_ROOT/$PDK/libs.tech/klayout/tech/drc/gf180mcu.drc -rd input=$GDS -rd topcell=$B \
    -rd report=$OUT/klayout_drc.lyrdb -rd variant=D -rd run_mode=deep -rd threads=$THREADS \
    -rd decks=${KLDECKS:-all,-density} -rd feol=true -rd beol=true > klayout_drc.log 2>&1
  python3 - "$OUT/klayout_drc.lyrdb" <<'PYEOF' | tee klayout_drc_summary.txt
import sys, xml.etree.ElementTree as ET, collections
r = ET.parse(sys.argv[1]).getroot()
c = collections.Counter(i.findtext('category') for i in r.iter('item'))
print('count', sum(c.values()))
for k, v in c.most_common(): print(' ', v, k)
PYEOF
  log "== KLayout DRC ($(( $(date +%s) - t0 )) s), decks ${KLDECKS:-all,-density}, rules run $(grep -c 'Executing rule' klayout_drc.log): $(head -1 klayout_drc_summary.txt)"
  tail -n +2 klayout_drc_summary.txt | head -20 >> summary.txt
fi

# ---- netgen LVS ----
lvs() {
  $NICE netgen -batch lvs "$1 $2" "$3 $4" $SETUP $5.report > $5.log 2>&1
  grep -q "Final result: Circuits match uniquely" $5.report && ! grep -qi "property errors" $5.report \
    && ! grep -qi "do not match" $5.report
}
why() { grep -E "Final result|roperty errors|do not match" $1.report | sort -u | tr '\n' ' '; }
t0=$(date +%s)
if lvs ${B}_lay.spice $B $SRC $B lvs; then log "LVS PASS ($(( $(date +%s) - t0 )) s): $(why lvs)"
else log "LVS FAIL ($(( $(date +%s) - t0 )) s): $(why lvs)"; fi

# ---- device sizes vs the sim netlister ----
python3 $REPO/layout/gen/rx_sizes.py ${B}_lay.spice $B > sizes.txt 2>&1
log "== sizes: $(tail -1 sizes.txt)"

# ---- mutations ----
python3 - "$SRC" "$B" <<'PYEOF'
import re, sys
src, top = sys.argv[1], sys.argv[2]
lines = open(src).read().splitlines()
# the top subckt's device lines
inside, idx = False, []
for i, l in enumerate(lines):
    t = l.split()
    if t and t[0].lower() == '.subckt':
        inside = t[1] == top
    elif t and t[0].lower() == '.ends':
        inside = False
    elif inside and t and t[0][0] in 'Xx' and re.search(r'[np]fet_03v3', l):
        idx.append(i)
if not idx:     # a cell with only subcircuit instances: mutate inside the first subckt that has MOS devices
    for i, l in enumerate(lines):
        if l.split() and l.split()[0][0] in 'Xx' and re.search(r'[np]fet_03v3', l):
            idx.append(i)
def save(name, ls, what):
    open(name, 'w').write('\n'.join(ls) + '\n')
    open(name + '.what', 'w').write(what)
# 1: m (or W) of the first device with m > 1
ls = list(lines)
for i in idx:
    m = re.search(r'\bm=(\d+)', ls[i])
    if m and int(m.group(1)) > 1:
        k = int(m.group(1))
        ls[i] = ls[i][:m.start()] + f'm={k - 1}' + ls[i][m.end():]
        what = f'{ls[i].split()[0]} m {k} -> {k - 1}'
        break
else:
    i = idx[0]
    w = re.search(r'\bW=([\d.]+)u', ls[i])
    ls[i] = ls[i][:w.start()] + f'W={float(w.group(1)) * 0.9:.4f}u' + ls[i][w.end():]
    what = f'{ls[i].split()[0]} W x 0.9'
save('xsch/mut_m.spice', ls, what)
# 2: the gate of the first top-level device whose gate is not a supply -> VSS; for a cell of instances only
#    (rx_top), two nets of its first instance line swapped (a wrong connection between blocks)
ls = list(lines)
what = None
for i in idx:
    t = ls[i].split()
    if t[2] not in ('VSS', 'VDD') and any(l.split()[0] == t[0] for l in lines if l.split()):
        new = 'VSS'
        what = f'{t[0]} gate {t[2]} -> {new}'
        t[2] = new
        ls[i] = ' '.join(t)
        break
inside = False
top_insts = []
for i, l in enumerate(lines):
    t = l.split()
    if t and t[0].lower() == '.subckt':
        inside = t[1] == top
    elif t and t[0].lower() == '.ends':
        inside = False
    elif inside and t and t[0][0] in 'xX' and not re.search(r'[np]fet_03v3|ppolyf', l):
        top_insts.append(i)
if top_insts:
    ls = list(lines)
    i = top_insts[0]
    t = ls[i].split()
    sig = [k for k in range(1, len(t) - 1) if t[k] not in ('VDD', 'VSS')]
    a, b = sig[0], sig[1]
    what = f'{t[0]} nets {t[a]} <-> {t[b]}'
    t[a], t[b] = t[b], t[a]
    ls[i] = ' '.join(t)
save('xsch/mut_g.spice', ls, what)
PYEOF
mut_ok=1
for mm in mut_m mut_g; do
  if lvs ${B}_lay.spice $B xsch/$mm.spice $B lvs_$mm; then
    log "== mutation $(cat xsch/$mm.spice.what): PASS (BAD: not caught)"; mut_ok=0
  elif ! grep -q "Final result" lvs_$mm.report 2>/dev/null; then
    log "== mutation $(cat xsch/$mm.spice.what): NO RESULT (BAD: netgen did not run)"; mut_ok=0
  else log "== mutation $(cat xsch/$mm.spice.what): FAIL (expected)  [$(why lvs_$mm)]"; fi
done

lvs_ok=0; grep -q "^LVS PASS" summary.txt && lvs_ok=1
drc_ok=0; grep -q "^== magic DRC.*: count 0$" summary.txt && grep -q "^== KLayout DRC.*rules run [1-9][0-9]*: count 0$" summary.txt && drc_ok=1
[[ $SKIP == *klayout* ]] && grep -q "^== magic DRC.*: count 0$" summary.txt && drc_ok=1
ant_ok=1; [[ $SKIP != *antenna* ]] && ! grep -q "^== antenna.*violations 0," summary.txt && ant_ok=0
siz_ok=0; grep -q "^== sizes: SIZES OK" summary.txt && siz_ok=1
log "CHECK $([ $lvs_ok$drc_ok$ant_ok$mut_ok$siz_ok = 11111 ] && echo OK || echo FAIL)  (LVS vs xschem $lvs_ok, DRC $drc_ok, antenna $ant_ok, mutations caught $mut_ok, sizes $siz_ok)"
