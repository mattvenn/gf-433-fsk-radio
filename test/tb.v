`default_nettype none
`timescale 1ns / 1ps

// TT-style testbench: the tile on its Tiny Tapeout pins only (test/test.py). The wrapper
// tt_um_mattvenn_gf433_vco is generated from the LVS source by tools/check_pinout.py --verilog.
module tb ();
    reg        clk;
    reg        rst_n;
    reg        ena;
    reg  [7:0] ui_in;
    reg  [7:0] uio_in;
    wire [7:0] uo_out;
    wire [7:0] uio_out;
    wire [7:0] uio_oe;
    wire [7:0] ua;
    // the bench may drive ua[0] (the vctrl override through the debug switch); high impedance otherwise
    reg        ua0_drive_en = 1'b0;
    reg        ua0_drive = 1'b0;
    assign ua[0] = ua0_drive_en ? ua0_drive : 1'bz;

    tt_um_mattvenn_gf433_vco user_project (
        .ui_in  (ui_in),
        .uo_out (uo_out),
        .uio_in (uio_in),
        .uio_out(uio_out),
        .uio_oe (uio_oe),
        .ua     (ua),
        .ena    (ena),
        .clk    (clk),
        .rst_n  (rst_n)
    );
endmodule
