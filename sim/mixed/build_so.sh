#!/bin/bash
# Build build/mixed/tx_fine.so: src/tx_fine.v (the RTL, behavioural clock gates) verilated into a shared object
# for an XSPICE d_cosim instance in ngspice. This is ngspice's vlnggen script redone in bash (ngspice 46/47
# lowercases the script's shell lines, '-Mdir' -> '-mdir', which Verilator rejects), as in ook-asic-radio.
# Run in the osic image from the repo root:  bash sim/mixed/build_so.sh [out_dir]
set -e
SRC=/foss/tools/ngspice/share/ngspice/scripts/src
OUT=${1:-build/mixed}
OBJ=$OUT/tx_fine_obj_dir
RTL=src/tx_fine.v
mkdir -p $OUT
rm -rf $OBJ $OUT/tx_fine.so
# 1. Verilog -> C++ (prefix Vlng, as the shim expects)
verilator -Wno-fatal -Mdir $OBJ --prefix Vlng --CFLAGS -fpic --cc --top-module tx_fine $RTL
# 2. port tables for the shim: VL_IN8(&clk,0,0); -> VL_DATA(8,clk,0,0)
for kind in INOUT IN OUT; do
  f=$(echo $kind | tr A-Z a-z); [ $f = inout ] && f=inouts || f=${f}puts
  echo "/* Generated code: do not edit. */" > $OBJ/$f.h
  sed -n -e "s/.*VL_${kind}\([0-9]*\)(&\([^;]*\);.*/VL_DATA(\1,\2/p" $OBJ/Vlng.h >> $OBJ/$f.h
done
# 3. compile with the ngspice shim + main, then link the shared library
verilator -Wno-fatal -Mdir $OBJ --prefix Vlng --CFLAGS -fpic --CFLAGS -I$SRC --cc --build --exe \
  --top-module tx_fine $SRC/verilator_main.cpp $SRC/verilator_shim.cpp $RTL
g++ --shared $OBJ/verilator_shim.o $OBJ/verilated.o $OBJ/verilated_threads.o $OBJ/Vlng__ALL.a \
  -pthread -lpthread -o $OUT/tx_fine.so
echo "built $OUT/tx_fine.so"
echo "inputs:";  grep VL_DATA $OBJ/inputs.h
echo "outputs:"; grep VL_DATA $OBJ/outputs.h
