// The integrated clock gate as a black box on both sides: it is the same library cell, instantiated by name in
// the RTL (tx_cg under SYNTHESIS), so eqy matches the four instances by name and proves their inputs (CLK, E, TE)
// equivalent instead of reasoning through the latch inside.
(* blackbox *)
module gf180mcu_fd_sc_mcu7t5v0__icgtp_1 (input CLK, input E, input TE, output Q);
endmodule
