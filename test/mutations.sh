#!/bin/bash
# Mutation tests of tools/check_pinout.py and the TT-level cocotb tests (test/test.py): each mutant is one planted
# bug in a temporary copy of the LVS source, info.yaml or the RTL; the check must FAIL on every one.
#   bash test/mutations.sh            all (about 30 s)
# Work files in build/mut/. docs/verification_digital.md, "Mutation tests".
set -u
ROOT=$(cd "$(dirname "$0")/.." && pwd)
B=$ROOT/build/mut
rm -rf "$B"; mkdir -p "$B"
SP=$ROOT/lvs/tt_um_mattvenn_gf433_vco.spice
fail=0

# ---- pinout check: mutant spice / info.yaml -> check_pinout.py must exit 1
pin() {   # name, sed script, file (spice|info)
    local name=$1 sedx=$2 kind=$3 s=$SP i=$ROOT/info.yaml
    if [ "$kind" = info ]; then i=$B/$name.yaml; sed "$sedx" "$ROOT/info.yaml" > "$i"; cmp -s "$i" "$ROOT/info.yaml" && { echo "  $name: EDIT DID NOT APPLY"; fail=1; return; }
    else s=$B/$name.spice; sed "$sedx" "$SP" > "$s"; cmp -s "$s" "$SP" && { echo "  $name: EDIT DID NOT APPLY"; fail=1; return; }; fi
    if python3 "$ROOT/tools/check_pinout.py" --spice "$s" --info "$i" > "$B/$name.log" 2>&1; then
        echo "pinout $name: NOT CAUGHT"; fail=1
    else echo "pinout $name: caught: $(grep -m1 ERROR "$B/$name.log" | cut -c8-150)"; fi
}
pin swap_ua23   's/^\(xxtxd .*\) ua\[3\] ua\[2\] tx_drv/\1 ua[2] ua[3] tx_drv/' spice
pin swap_dbg01  's/^xxdbg_bbi VAPWR VGND dbg_sel\[0\]/xxdbg_bbi VAPWR VGND dbg_sel[1]/; s/^xxdbg_bbq VAPWR VGND dbg_sel\[1\]/xxdbg_bbq VAPWR VGND dbg_sel[0]/' spice
pin oe3_low     's/^xtie_uio_oe_3 \(.*\)__tieh/xtie_uio_oe_3 \1__tiel/' spice
pin dac_rev     's/^\(xxmdac VAPWR VGND vg vbnf\) dac_tn\[29\] dac_tn\[27\]/\1 dac_tn[27] dac_tn[29]/' spice
pin ua1_open    's/^Rshort_ua1 .*//' spice
pin rx_en_open  's/^\(xrx_lobuf_q VAPWR VGND lsq\) rx_en/\1 nc_lobuf_q_en/' spice
pin label       's/^  uo\[1\]: "f \/ 16 (27 MHz)"/  uo[1]: "f \/ 64 (6.8 MHz)"/' info
pin analog_pins 's/^  analog_pins: 6 /  analog_pins: 4 /' info

# ---- TT-level cocotb: a mutant spice (wrapper) or RTL -> test.py must report a failure
tt() {    # name, sed script, file (spice|rtl)
    local name=$1 sedx=$2 kind=$3 sb=$B/sb_$1 extra=()
    mkdir -p "$sb"
    if [ "$kind" = rtl ]; then
        sed "$sedx" "$ROOT/src/tx_fine.v" > "$B/$name.v"; cmp -s "$B/$name.v" "$ROOT/src/tx_fine.v" && { echo "  $name: EDIT DID NOT APPLY"; fail=1; return; }
        python3 "$ROOT/tools/check_pinout.py" --verilog "$sb/tt_um_mattvenn_gf433_vco.v" --no-fail > /dev/null
        extra=(RTL="$B/$name.v")
    else
        sed "$sedx" "$SP" > "$B/$name.spice"; cmp -s "$B/$name.spice" "$SP" && { echo "  $name: EDIT DID NOT APPLY"; fail=1; return; }
        python3 "$ROOT/tools/check_pinout.py" --spice "$B/$name.spice" --verilog "$sb/tt_um_mattvenn_gf433_vco.v" --no-fail > /dev/null
    fi
    make -C "$ROOT/test" TB=tt SIM_BUILD="$sb" COCOTB_RESULTS_FILE="$B/$name.xml" "${extra[@]}" > "$B/$name.log" 2>&1
    local nf; nf=$(grep -c "<failure" "$B/$name.xml" 2>/dev/null || echo 0)
    if [ ! -s "$B/$name.xml" ]; then echo "tt $name: NO RESULTS ($B/$name.log)"; fail=1
    elif [ "$nf" -gt 0 ]; then echo "tt $name: caught, failing: $(python3 -c 'import sys, xml.etree.ElementTree as E; print(" ".join(t.get("name") for t in E.parse(sys.argv[1]).iter("testcase") if t.find("failure") is not None))' "$B/$name.xml")"
    else echo "tt $name: NOT CAUGHT"; fail=1; fi
}
tt swap_dbg01   's/^xxdbg_bbi VAPWR VGND dbg_sel\[0\]/xxdbg_bbi VAPWR VGND dbg_sel[1]/; s/^xxdbg_bbq VAPWR VGND dbg_sel\[1\]/xxdbg_bbq VAPWR VGND dbg_sel[0]/' spice
tt oe3_low      's/^xtie_uio_oe_3 \(.*\)__tieh/xtie_uio_oe_3 \1__tiel/' spice
tt dac_rev      's/^\(xxmdac VAPWR VGND vg vbnf\) dac_tn\[29\] dac_tn\[27\]/\1 dac_tn[27] dac_tn[29]/' spice
tt swap_tx_en   's/^\(xxtxd VDPWR VGND ls\) ui_in\[5\] ui_in\[6\]/\1 ui_in[6] ui_in[5]/' spice
tt rx_en_open   's/^\(xrx_lobuf_q VAPWR VGND lsq\) rx_en/\1 nc_lobuf_q_en/' spice
tt rtl_rx_en    's/assign rx_en = ctrl\[4\];/assign rx_en = ctrl[3];/' rtl
tt rtl_dbg_addr 's/3.d5: dbg      <=/3'"'"'d6: dbg      <=/' rtl
exit $fail
