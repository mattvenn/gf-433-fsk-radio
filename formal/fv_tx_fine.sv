`default_nettype none
// Formal harness for tx_fine (SymbiYosys: formal/tx_fine.sby). docs/verification_digital.md, "Formal".
// Every input is free at every step: rst_n (any time), SPI pins, fsk, and ck (any waveform). clk toggles every
// step (the project clock); the only other assumption is reset in the first step. The RTL is not modified: the
// gated clocks and latches of src/tx_fine.v are modelled as they are (multiclock, the non-SYNTHESIS tx_cg latch
// model). Internal registers reach fv_props' s_* ports through `connect -set` in the .sby after flatten.
//
//   R  reset: every output at its reset value while rst_n is low
//   S  SPI register file: the registers (and rx_en / dbg_sel) always equal a reference model of the documented
//      frame format (16 bits, [15] read, [14:12] address, write at the 16th rising edge, 4 / 6 / 7 not writable)
//   F  FSK and saturation: the effective word is {MED_INT, MED_FRAC} +/- FSK_DEV clamped to 0 .. 2^18 - 1 (no wrap)
//   D  DAC lines: the thermometer has no gaps and the lines always encode eff_int (monotonic medium DAC)
//   Q  SD: with SD_EN off, the SD cell is off and the accumulator clear after one clk
//   G  ck_o: only whole ck pulses (rising and falling with ck), outside reset
//   gates task: the clock-gated macro equals the same RTL with every gate replaced by a wire, output for output
//   dbg task (expected FAIL, BMC): at most one DBG_SEL bit on; a counterexample shows the RTL allows two
module fv_tx_fine (
    input wire clk, input wire ck, input wire rst_n,
    input wire sclk, input wire mosi, input wire cs_n, input wire fsk
);
    wire miso, ck_o, div16, div64, div1024, dac_sdn, rx_en;
    wire [30:0] dac_tn;
    wire [4:0]  dac_bn;
    wire [3:0]  dbg_sel;
    tx_fine dut (.clk(clk), .rst_n(rst_n), .sclk(sclk), .mosi(mosi), .cs_n(cs_n), .miso(miso), .fsk(fsk), .ck(ck),
                 .ck_o(ck_o), .div16(div16), .div64(div64), .div1024(div1024), .dac_tn(dac_tn), .dac_bn(dac_bn),
                 .dac_sdn(dac_sdn), .rx_en(rx_en), .dbg_sel(dbg_sel));

    reg f_init = 1'b1;
    always @($global_clock) f_init <= 1'b0;
    always @(*) if (f_init) assume (!rst_n);
    always @($global_clock) if (!f_init) assume (clk != $past(clk));

`ifdef FV_GATES
    // the same RTL with tx_cg -> a wire (tx_fine_ng is made in the .sby by copy + chtype)
    wire miso2, ck_o2, div16_2, div64_2, div1024_2, dac_sdn2, rx_en2;
    wire [30:0] dac_tn2;
    wire [4:0]  dac_bn2;
    wire [3:0]  dbg_sel2;
    tx_fine_ng ref (.clk(clk), .rst_n(rst_n), .sclk(sclk), .mosi(mosi), .cs_n(cs_n), .miso(miso2), .fsk(fsk),
                    .ck(ck), .ck_o(ck_o2), .div16(div16_2), .div64(div64_2), .div1024(div1024_2), .dac_tn(dac_tn2),
                    .dac_bn(dac_bn2), .dac_sdn(dac_sdn2), .rx_en(rx_en2), .dbg_sel(dbg_sel2));
    reg f_rst_seen = 1'b0;
    always @($global_clock) if (!rst_n) f_rst_seen <= 1'b1;
    always @(*) if (f_rst_seen && !f_init) begin
        assert ({miso, ck_o, div16, div64, div1024, dac_sdn, rx_en, dac_tn, dac_bn, dbg_sel} ==
                {miso2, ck_o2, div16_2, div64_2, div1024_2, dac_sdn2, rx_en2, dac_tn2, dac_bn2, dbg_sel2});
    end
`else
    fv_props chk (.clk(clk), .ck(ck), .rst_n(rst_n), .sclk(sclk), .mosi(mosi), .cs_n(cs_n), .f_init(f_init),
                  .miso(miso), .ck_o(ck_o), .div16(div16), .div64(div64), .div1024(div1024), .dac_tn(dac_tn),
                  .dac_bn(dac_bn), .dac_sdn(dac_sdn), .rx_en(rx_en), .dbg_sel(dbg_sel)
                  // s_* left open: driven from the DUT's internals by `connect -set` in the .sby
                  );
`endif
endmodule

module fv_props (
    input wire clk, input wire ck, input wire rst_n, input wire sclk, input wire mosi, input wire cs_n,
    input wire f_init,
    input wire miso, input wire ck_o, input wire div16, input wire div64, input wire div1024,
    input wire [30:0] dac_tn, input wire [4:0] dac_bn, input wire dac_sdn, input wire rx_en, input wire [3:0] dbg_sel,
    // probes into the DUT (see the .sby)
    input wire [9:0]  s_med_int,
    input wire [7:0]  s_med_frac,
    input wire [11:0] s_fsk_dev,
    input wire [4:0]  s_ctrl,
    input wire [9:0]  s_eff_int,
    input wire [17:0] s_eff,      // the effective word (combinational, before eff_q)
    input wire [2:0]  s_fsk,      // the fsk synchroniser; [1] is the synchronised level
    input wire [7:0]  s_acc
);
    // ---------------------------------------------------------------- R: reset values
    reg f_rst_q = 1'b0;
    always @($global_clock) f_rst_q <= !rst_n;
    always @(*) if (!f_init && f_rst_q && !rst_n) begin
        assert (dac_tn == 31'h7fff_0000 && dac_bn == 5'h1f && dac_sdn);    // word 512, SD cell off
        assert (!miso && !rx_en && dbg_sel == 4'd0);
        assert (!ck_o && !div16 && !div64 && !div1024);
    end

    // ---------------------------------------------------------------- S: register file vs a reference model
    // the pins through the same two-flop synchronisers as the spec (SCLK < clk / 8 is the user's job)
    reg [2:0] f_sclk, f_cs;
    reg [1:0] f_mosi;
    reg [4:0] f_n;                // bits in this frame, saturating at 16
    reg [15:0] f_sr;
    reg [9:0] m_med_int; reg [7:0] m_med_frac; reg [11:0] m_fsk_dev; reg [4:0] m_ctrl; reg [3:0] m_dbg;
    wire f_rise = f_sclk[1] & ~f_sclk[2];
    wire f_sel = ~f_cs[1];
    wire [15:0] f_frame = {f_sr[14:0], f_mosi[1]};
    always @(posedge clk or negedge rst_n)
        if (!rst_n) begin
            f_sclk <= 0; f_cs <= 3'b111; f_mosi <= 0; f_n <= 0; f_sr <= 0;
            m_med_int <= 512; m_med_frac <= 0; m_fsk_dev <= 0; m_ctrl <= 0; m_dbg <= 0;
        end else begin
            f_sclk <= {f_sclk[1:0], sclk}; f_cs <= {f_cs[1:0], cs_n}; f_mosi <= {f_mosi[0], mosi};
            if (!f_sel) f_n <= 0;
            else if (f_rise) begin
                f_sr <= f_frame;
                if (f_n != 16) f_n <= f_n + 1'b1;
                if (f_n == 15 && !f_frame[15])
                    case (f_frame[14:12])
                        3'd0: m_med_int  <= f_frame[9:0];
                        3'd1: m_med_frac <= f_frame[7:0];
                        3'd2: m_fsk_dev  <= f_frame[11:0];
                        3'd3: m_ctrl     <= f_frame[4:0];
                        3'd5: m_dbg      <= f_frame[3:0];
                        default: ;          // 4 EFF_INT, 7 ID: read only; 6: none
                    endcase
            end
        end
    // frame length: the RTL's bit counter is 5 bits and wraps, so a frame of 48 or more bits writes again at bit
    // 48 (80, ...). The documented frames are 16 bits: the prove task assumes at most 47 bits per CS_n low; the
    // long task (FV_LONG_FRAMES, expected FAIL) shows the extra write.
    reg [5:0] f_len;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) f_len <= 0;
        else if (!f_sel) f_len <= 0;
        else if (f_rise && f_len != 6'd63) f_len <= f_len + 1'b1;
`ifndef FV_LONG_FRAMES
    always @(*) assume (f_len <= 6'd47);
`endif
    always @(*) if (!f_init) begin
        assert (s_med_int == m_med_int && s_med_frac == m_med_frac && s_fsk_dev == m_fsk_dev);
        assert (s_ctrl == m_ctrl && rx_en == m_ctrl[4] && dbg_sel == m_dbg);
    end

    // ---------------------------------------------------------------- F: FSK offset, saturated
    wire [18:0] f_base = {1'b0, s_med_int, s_med_frac};
    wire        f_up = s_fsk[1] ^ s_ctrl[3];
    wire [18:0] f_hi = f_base + s_fsk_dev;
    wire [17:0] f_want = !s_ctrl[2] ? f_base[17:0]
                       : f_up ? (f_hi > 19'h3ffff ? 18'h3ffff : f_hi[17:0])
                              : (f_base < s_fsk_dev ? 18'd0 : f_base[17:0] - s_fsk_dev);
    always @(*) if (!f_init) assert (s_eff == f_want);

    // ---------------------------------------------------------------- D: DAC lines
    wire [30:0] f_seg = ~dac_tn;
    always @(*) if (!f_init) begin
        assert ((f_seg & (f_seg + 31'd1)) == 31'd0);                    // 0...01...1: no gaps
        assert (f_seg == ((31'd1 << s_eff_int[9:5]) - 31'd1) && ~dac_bn == s_eff_int[4:0]);
    end

    // ---------------------------------------------------------------- Q: SD off
    reg f_sdoff = 1'b0;           // the last clk edge saw SD_EN = 0
    always @(posedge clk or negedge rst_n)
        if (!rst_n) f_sdoff <= 1'b1; else f_sdoff <= !s_ctrl[0];
    always @(*) if (!f_init && f_sdoff) assert (dac_sdn && s_acc == 8'd0);

    // ---------------------------------------------------------------- G: ck_o whole pulses only
    reg f_ck_q = 1'b0, f_cko_q = 1'b0, f_rstn_q = 1'b0;
    always @($global_clock) begin f_ck_q <= ck; f_cko_q <= ck_o; f_rstn_q <= rst_n; end
    always @(*) if (!f_init && rst_n && f_rstn_q) begin
        assert (!ck_o || ck);
        if (ck_o && !f_cko_q) assert (ck && !f_ck_q);      // rises only with ck
        if (!ck_o && f_cko_q) assert (!ck && f_ck_q);      // falls only with ck
    end

`ifdef FV_DBG_ONEHOT
    // expected to FAIL: the RTL stores any 4-bit DBG_SEL ("at most one is the firmware's job")
    always @(*) if (!f_init) assert ((dbg_sel & (dbg_sel - 4'd1)) == 4'd0);
`endif
endmodule
