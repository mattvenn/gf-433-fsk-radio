// tx_cg replaced by a wire: the reference for the clock-gating equivalence (formal/tx_fine.sby task gates)
module tx_cg_ng (input wire clk, input wire en, output wire gclk);
    assign gclk = clk;
endmodule
