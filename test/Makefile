# cocotb tests (docs/verification_digital.md):
#   make            both benches, RTL: the tx_fine macro on its own (test_tx_fine.py), then the whole tile on
#                   its TT pins (test.py, TOPLEVEL tb)
#   make GL=1       the same on the hardened netlist macro/tx_fine/nl/tx_fine.nl.v
#   make TB=macro | make TB=tt     one bench
# Results: results_<bench>[_gl].xml; make fails if a test fails (cocotb's check_results).
# The TT-level wrapper is generated from the LVS source by tools/check_pinout.py --verilog (the pinout check
# runs too and prints its result; the wrapper is written even while the check reports an error).
SIM ?= icarus
TOPLEVEL_LANG ?= verilog
TESTDIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
REPO := $(abspath $(TESTDIR)/..)

ifeq ($(TB),)
.PHONY: all clean
all:
	$(MAKE) TB=macro
	$(MAKE) TB=tt
clean:
	rm -rf sim_build* results*.xml __pycache__
else

SUF := $(if $(GL),_gl,)
SIM_BUILD := sim_build_$(TB)$(SUF)
COCOTB_RESULTS_FILE := results_$(TB)$(SUF).xml

ifneq ($(GL),)
PDK_ROOT ?= /foss/pdks
SCL = $(PDK_ROOT)/gf180mcuD/libs.ref/gf180mcu_fd_sc_mcu7t5v0/verilog
COMPILE_ARGS += -DFUNCTIONAL -DUNIT_DELAY=\#1 -DGL
VERILOG_SOURCES += $(SCL)/primitives.v $(SCL)/gf180mcu_fd_sc_mcu7t5v0.v $(REPO)/macro/tx_fine/nl/tx_fine.nl.v
else
RTL ?= $(REPO)/src/tx_fine.v
VERILOG_SOURCES += $(RTL)
endif

ifeq ($(TB),macro)
TOPLEVEL = tx_fine
COCOTB_TEST_MODULES = test_tx_fine
else
export PYTHONPATH := $(REPO)/tools:$(PYTHONPATH)
WRAPPER := $(abspath $(SIM_BUILD))/tt_um_mattvenn_gf433_vco.v
VERILOG_SOURCES += $(TESTDIR)/tb.v $(TESTDIR)/stubs.v $(WRAPPER)
TOPLEVEL = tb
COCOTB_TEST_MODULES = test
endif

include $(shell cocotb-config --makefiles)/Makefile.sim

ifeq ($(TB),tt)
$(WRAPPER): $(REPO)/lvs/tt_um_mattvenn_gf433_vco.spice $(REPO)/info.yaml $(REPO)/tools/check_pinout.py
	python3 $(REPO)/tools/check_pinout.py --verilog $@ --no-fail
$(SIM_BUILD)/sim.vvp: $(WRAPPER)
endif
endif
