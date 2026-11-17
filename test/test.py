"""TT-level cocotb tests: the whole tile (tt_um_mattvenn_gf433_vco) driven only through its Tiny Tapeout pins.

The wrapper is generated from the LVS source (tools/check_pinout.py --verilog), so the wiring under test is the
wiring that is LVS-matched to the GDS: tx_fine (RTL, or the GL netlist with GL=1) and the analog blocks as
behavioural stubs (test/stubs.v). The SPI runs on uio_in[0..2] / uio_out[3]; the tests read the analog blocks'
control ports (the stubs) to see that each register bit reaches the right block.
Run: cd test && make TB=tt  (GL=1 for the hardened macro). docs/verification_digital.md, "TT-level cocotb".
"""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer
from cocotb.utils import get_sim_time

from check_pinout import UIO_OE

CLK_NS = 40      # 25 MHz project clock
CK_NS = 9.2      # ~108 MHz: the VCO / 4 (the stub's osc)
SCK_NS = 400     # SPI clock (clk / 10)
SCLK, MOSI, CS_N, MISO = 0, 1, 2, 3     # uio bits


def bit(sig, i):
    """Bit i of a vector as a character ('0', '1', 'x', 'z')."""
    s = str(sig.value)
    return s[len(s) - 1 - i].lower()


class Pins:
    def __init__(self, dut):
        self.dut = dut
        self.uio = 0
        self.ui = 0

    def set_uio(self, b, v):
        self.uio = (self.uio & ~(1 << b)) | (int(v) << b)
        self.dut.uio_in.value = self.uio

    def set_ui(self, b, v):
        self.ui = (self.ui & ~(1 << b)) | (int(v) << b)
        self.dut.ui_in.value = self.ui


async def start(dut, ena=1):
    p = Pins(dut)
    cocotb.start_soon(Clock(dut.clk, CLK_NS, unit="ns").start())
    cocotb.start_soon(Clock(dut.user_project.xvco_core.osc, CK_NS, unit="ns").start())
    dut.ena.value = ena
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    p.set_uio(CS_N, 1)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)
    return p


async def xfer(dut, p, word):
    """One 16-bit SPI frame on the uio pins; returns the 16 MISO bits sampled on the rising edges."""
    p.set_uio(CS_N, 0)
    await Timer(SCK_NS, unit="ns")
    got = 0
    for i in range(15, -1, -1):
        p.set_uio(MOSI, (word >> i) & 1)
        await Timer(SCK_NS / 2, unit="ns")
        p.set_uio(SCLK, 1)
        got = (got << 1) | int(bit(dut.uio_out, MISO) == '1')
        await Timer(SCK_NS / 2, unit="ns")
        p.set_uio(SCLK, 0)
    await Timer(SCK_NS, unit="ns")
    p.set_uio(CS_N, 1)
    await Timer(SCK_NS, unit="ns")
    return got


async def wr(dut, p, addr, data):
    await xfer(dut, p, (addr << 12) | (data & 0xfff))


async def rd(dut, p, addr):
    return (await xfer(dut, p, 0x8000 | (addr << 12))) & 0xfff


def mdac(dut):
    m = dut.user_project.xxmdac
    assert int(m.thermo_ok.value) == 1, "mdac: the segment lines are not a thermometer from ns1 up"
    return int(m.word.value), int(m.sd.value)


def dbg_ctrl(dut):
    u = dut.user_project
    return [int(getattr(u, n).ctrl.value) for n in ("xxdbg_bbi", "xxdbg_bbq", "xxdbg_nb", "xxdbg_vctrl")]


def rx_on(dut):
    u = dut.user_project
    return [int(u.xrx_bias.en.value), int(u.xrx_lobuf_i.en.value), int(u.xrx_lobuf_q.en.value)]


@cocotb.test()
async def test_reset_and_oe(dut):
    """uio_oe and the tied outputs during and after reset; every control at its reset value; ena is ignored."""
    p = Pins(dut)
    cocotb.start_soon(Clock(dut.clk, CLK_NS, unit="ns").start())
    cocotb.start_soon(Clock(dut.user_project.xvco_core.osc, CK_NS, unit="ns").start())
    dut.ena.value = 0
    dut.ui_in.value = 0
    p.set_uio(CS_N, 1)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 3)
    assert int(dut.uio_oe.value) == UIO_OE == 0x08, f"uio_oe in reset {dut.uio_oe.value}"
    assert bit(dut.uio_out, MISO) == '0', "MISO not low in reset"
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 5)
    assert int(dut.uio_oe.value) == UIO_OE, f"uio_oe after reset {dut.uio_oe.value}"
    assert int(dut.uio_out.value) == 0, f"uio_out {dut.uio_out.value}"
    for i in (0, 6, 7):        # ck gated off after reset; uo[6..7] tied low
        assert bit(dut.uo_out, i) == '0', f"uo_out[{i}] = {bit(dut.uo_out, i)}"
    assert rx_on(dut) == [0, 0, 0], "receiver enabled after reset"
    assert bit(dut.uo_out, 4) == '0' and bit(dut.uo_out, 5) == '0'
    assert dbg_ctrl(dut) == [0, 0, 0, 0], "a debug switch is on after reset"
    assert bit(dut.ua, 0) == 'z', f"ua[0] is driven after reset ({bit(dut.ua, 0)})"
    assert mdac(dut) == (512, 0), f"mdac after reset {mdac(dut)}"
    # the design ignores ena: the SPI works with ena low
    assert await rd(dut, p, 7) == 0x433
    dut.ena.value = 1
    assert await rd(dut, p, 7) == 0x433
    # rst_n puts every register back
    await wr(dut, p, 0, 0x2a5); await wr(dut, p, 3, 0x1f); await wr(dut, p, 5, 0x4)
    await ClockCycles(dut.clk, 6)
    assert mdac(dut)[0] == 0x2a5 and rx_on(dut) == [1, 1, 1] and dbg_ctrl(dut) == [0, 0, 1, 0]
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 2)
    assert mdac(dut) == (512, 0) and rx_on(dut) == [0, 0, 0] and dbg_ctrl(dut) == [0, 0, 0, 0]
    assert int(dut.uio_oe.value) == UIO_OE
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 4)
    assert await rd(dut, p, 0) == 512 and await rd(dut, p, 3) == 0 and await rd(dut, p, 5) == 0


@cocotb.test()
async def test_spi_to_mdac(dut):
    """Register writes on the uio pins reach the macro and, through the 37 DAC lines, the medium DAC's word."""
    p = await start(dut)
    for a, v in ((0, 0x2a5), (1, 0x5c), (2, 0x9f3), (3, 0x5), (5, 0x3)):
        await wr(dut, p, a, v)
    for a, v in ((0, 0x2a5), (1, 0x5c), (2, 0x9f3), (3, 0x5), (5, 0x3), (7, 0x433)):
        assert await rd(dut, p, a) == v, f"register {a}"
    await wr(dut, p, 3, 0); await wr(dut, p, 5, 0)
    # every thermometer level (k segments on) with a different binary part, plus the end points
    for w in [k * 32 + (k * 7) % 32 for k in range(32)] + [1, 0x155, 0x2aa, 1023]:
        await wr(dut, p, 0, w)
        await ClockCycles(dut.clk, 6)
        assert mdac(dut) == (w, 0), f"MED_INT {w}: mdac sees {mdac(dut)}"
        assert await rd(dut, p, 4) == w
    # FSK on ui_in[7]: +/- FSK_DEV (4.8 fixed point) at the DAC
    await wr(dut, p, 0, 500); await wr(dut, p, 1, 0x40); await wr(dut, p, 2, 0x2c0); await wr(dut, p, 3, 0b100)
    for f, exp in ((1, (500 << 8) + 0x40 + 0x2c0), (0, (500 << 8) + 0x40 - 0x2c0)):
        p.set_ui(7, f)
        await ClockCycles(dut.clk, 8)
        assert mdac(dut)[0] == exp >> 8, f"fsk {f}: {mdac(dut)}"
    # the SD cell runs with SD_EN and a fraction: its mean is the fraction
    await wr(dut, p, 3, 0); await wr(dut, p, 1, 77); await wr(dut, p, 3, 1)
    await ClockCycles(dut.clk, 4)
    ones = 0
    for _ in range(256):
        await RisingEdge(dut.clk); await Timer(1, unit="ns")
        ones += mdac(dut)[1]
    assert ones == 77, f"SD cell mean {ones}/256"


@cocotb.test()
async def test_rx_en(dut):
    """CTRL[4] (RX_EN) turns on the receiver's bias and both LO buffers; the limiters reach uo_out[4] / [5]."""
    p = await start(dut)
    u = dut.user_project
    u.xrx_bb_i.val.value = 1
    u.xrx_bb_q.val.value = 0
    await wr(dut, p, 3, 0b01111)                 # every CTRL bit but RX_EN
    await ClockCycles(dut.clk, 4)
    assert rx_on(dut) == [0, 0, 0]
    assert bit(dut.uo_out, 4) == '0' and bit(dut.uo_out, 5) == '0'
    await wr(dut, p, 3, 0b10000)
    await ClockCycles(dut.clk, 4)
    assert rx_on(dut) == [1, 1, 1]
    assert int(u.xrx_lim_i.enb.value) == 0 and int(u.xrx_lna.enb.value) == 0
    for vi, vq in ((1, 0), (0, 1), (1, 1)):
        u.xrx_bb_i.val.value = vi
        u.xrx_bb_q.val.value = vq
        await Timer(1, unit="ns")
        assert (bit(dut.uo_out, 4), bit(dut.uo_out, 5)) == (str(vi), str(vq)), "limiter outputs swapped or lost"
    # the LO buffers pass the LO only while enabled
    await RisingEdge(u.xrx_lobuf_i.lo)
    await wr(dut, p, 3, 0)
    await ClockCycles(dut.clk, 4)
    assert rx_on(dut) == [0, 0, 0]
    for _ in range(20):
        await Timer(3, unit="ns")
        assert int(u.xrx_lobuf_i.lo.value) == 0 and int(u.xrx_lobuf_q.lo.value) == 0


@cocotb.test()
async def test_dbg_sel(dut):
    """DBG_SEL bit k closes debug switch k only, and ua[0] then carries that switch's source; bit 3 also lets
    the bench drive vctrl from ua[0]."""
    p = await start(dut)
    u = dut.user_project
    await wr(dut, p, 3, 0b10000)                 # RX on, so the baseband and nb sources are live
    for vi, vq in ((1, 0), (0, 1)):
        u.xrx_bb_i.val.value = vi
        u.xrx_bb_q.val.value = vq
        u.xrx_bias.val.value = vq ^ 1 if vi else vq
        src = [str(vi), str(vq), str(int(u.xrx_bias.val.value)), '0']   # vctrl: the 200 kOhm pull-down
        for k in range(4):
            await wr(dut, p, 5, 1 << k)
            await ClockCycles(dut.clk, 2)
            assert dbg_ctrl(dut) == [int(j == k) for j in range(4)], f"DBG_SEL {1 << k}: {dbg_ctrl(dut)}"
            assert bit(dut.ua, 0) == src[k], f"DBG_SEL {1 << k}: ua[0] = {bit(dut.ua, 0)}, expected {src[k]}"
    await wr(dut, p, 5, 0)
    await ClockCycles(dut.clk, 2)
    assert dbg_ctrl(dut) == [0, 0, 0, 0] and bit(dut.ua, 0) == 'z'
    # the vctrl override: with switch 3 on, ua[0] driven from the bench sets vctrl at the core
    await wr(dut, p, 5, 0b1000)
    dut.ua0_drive.value = 1
    dut.ua0_drive_en.value = 1
    await Timer(1, unit="ns")
    assert int(u.xvco_core.vctrl.value) == 1, "ua[0] does not reach vctrl through switch 3"
    await wr(dut, p, 5, 0)
    await Timer(1, unit="ns")
    assert int(u.xvco_core.vctrl.value) == 0, "vctrl not back on its pull-down with switch 3 off"
    dut.ua0_drive_en.value = 0
    # two switches at once short two sources on ua[0] (the RTL allows it: at most one is firmware's job)
    u.xrx_bb_i.val.value = 1
    u.xrx_bb_q.val.value = 0
    await wr(dut, p, 5, 0b0011)
    await ClockCycles(dut.clk, 2)
    assert dbg_ctrl(dut) == [1, 1, 0, 0] and bit(dut.ua, 0) == 'x'
    await wr(dut, p, 5, 0)


@cocotb.test()
async def test_tx_and_code(dut):
    """ui_in[5] / ui_in[6] enable the TX arms on ua[3] / ua[2]; ui_in[4:0] reach the ring's coarse DAC with
    their inverses."""
    p = await start(dut)
    u = dut.user_project

    async def toggles(i, n=40):
        seen = set()
        for _ in range(n):
            await Timer(CK_NS / 4, unit="ns")
            seen.add(bit(dut.ua, i))
        return seen
    assert await toggles(3) == {'0'} and await toggles(2) == {'0'}
    for b, (pin, other) in ((5, (3, 2)), (6, (2, 3))):
        p.set_ui(b, 1)
        assert await toggles(pin) == {'0', '1'}, f"ui_in[{b}] does not key ua[{pin}]"
        assert await toggles(other) == {'0'}, f"ui_in[{b}] keys ua[{other}]"
        p.set_ui(b, 0)
    for code in (0, 1, 2, 4, 8, 16, 0x15, 0x0a, 0x1f):
        for b in range(5):
            p.set_ui(b, (code >> b) & 1)
        await Timer(1, unit="ns")
        assert int(u.xvco_core.code.value) == code and int(u.xvco_core.code_ok.value) == 1, f"code {code}"


@cocotb.test()
async def test_dividers(dut):
    """uo_out[1..3] = ck / 4, / 16, / 256 (f / 16, / 64, / 1024); uo_out[0] = ck only with CTRL.CK_EN."""
    p = await start(dut)
    for i, n in ((1, 4), (2, 16), (3, 256)):
        sig = dut.uo_out
        async def edge():
            while True:
                prev = bit(sig, i)
                await sig.value_change
                if prev == '0' and bit(sig, i) == '1':
                    return get_sim_time("ps")
        t0 = await edge()
        t1 = await edge()
        per = (t1 - t0) / (CK_NS * 1000)
        assert abs(per - n) < 0.01, f"uo_out[{i}]: {per} ck periods, expected {n}"
    ck = dut.user_project.xvco_core.osc
    await wr(dut, p, 3, 0b10)
    await ClockCycles(ck, 10)
    for _ in range(40):
        await Timer(CK_NS / 4, unit="ns")
        assert bit(dut.uo_out, 0) == str(int(ck.value)), "uo_out[0] does not follow ck with CK_EN"
    await wr(dut, p, 3, 0)
    await ClockCycles(ck, 10)
    for _ in range(40):
        await Timer(CK_NS / 4, unit="ns")
        assert bit(dut.uo_out, 0) == '0'
