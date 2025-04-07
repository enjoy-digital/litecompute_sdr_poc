#!/usr/bin/env python3

#
# This file is part of LiteX-Boards.
#
# Copyright (c) 2021-2024 Florent Kermarrec <florent@enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import argparse
import subprocess

from migen import *

from litex.gen import *

from litex.build.io import DifferentialInput

from litex_boards.platforms import sqrl_acorn

from litex.soc.interconnect.csr import *
from litex.soc.interconnect     import stream

from litex.soc.integration.soc_core import *
from litex.soc.integration.builder import *

from litex.soc.cores.clock import *
from litex.soc.cores.led   import LedChaser

from litepcie.phy.s7pciephy import S7PCIEPHY
from litepcie.software import generate_litepcie_software_headers

from litedram.frontend.fifo import LiteDRAMFIFO
from litedram.modules import MT41K512M16
from litedram.phy import s7ddrphy

from liteeth.phy.a7_gtp import QPLLSettings, QPLL

from litescope import LiteScopeAnalyzer

from gateware.sdr_processing import SDRProcessing

# CRG ----------------------------------------------------------------------------------------------

class CRG(LiteXModule):
    def __init__(self, platform, sys_clk_freq, with_dram=False, with_fft_window=False):
        self.rst          = Signal()
        self.cd_sys       = ClockDomain()
        self.cd_sys4x     = ClockDomain()
        self.cd_sys4x_dqs = ClockDomain()
        self.cd_idelay    = ClockDomain()

        if with_fft_window:
            self.cd_sys2x = ClockDomain()

        # Clk/Rst.
        clk200    = platform.request("clk200")
        clk200_se = Signal()
        self.specials += DifferentialInput(clk200.p, clk200.n, clk200_se)

        # PLL.
        self.pll = pll = S7PLL()
        self.comb += pll.reset.eq(self.rst)
        pll.register_clkin(clk200_se, 200e6)
        pll.create_clkout(self.cd_sys,       sys_clk_freq)
        if with_dram:
            pll.create_clkout(self.cd_sys4x,     4*sys_clk_freq)
            pll.create_clkout(self.cd_sys4x_dqs, 4*sys_clk_freq, phase=90)
        platform.add_false_path_constraints(self.cd_sys.clk, pll.clkin) # Ignore sys_clk to pll.clkin path created by SoC's rst.

        # IDelayCtrl.
        if with_dram:
            self.specials += Instance("BUFG", i_I=clk200_se, o_O=self.cd_idelay.clk)
            self.idelayctrl = S7IDELAYCTRL(self.cd_idelay)

        # MAIA FFT.
        if with_fft_window:
            pll.create_clkout(self.cd_sys2x, 2 * sys_clk_freq)

# BaseSoC -----------------------------------------------------------------------------------------

class BaseSoC(SoCCore):
    def __init__(self, variant="cle-215+", sys_clk_freq=125e6,
        with_pcie          = False,
        with_led_chaser    = True,
        with_uartbone      = True,
        with_litedram_fifo = False,
        with_fft_window    = False,
        fft_radix          = 2,
        fft_order_log2     = 10,
        **kwargs):
        platform      = sqrl_acorn.Platform(variant=variant)
        platform.name = "acorn" # Keep target name
        platform.add_extension(sqrl_acorn._litex_acorn_baseboard_mini_io, prepend=True)

        # SoCCore ----------------------------------------------------------------------------------
        SoCCore.__init__(self, platform, sys_clk_freq,
            ident               = "LiteX SoC on Acorn CLE-101/215(+)",
            ident_version       = True,
            integrated_rom_size = 0x9800,
            with_uartbone       = with_uartbone,
            uart_name           = "crossover",
            no_uart             = True,
        )

        # Avoid stalling CPU at startup.
        self.uart.add_auto_tx_flush(sys_clk_freq=sys_clk_freq, timeout=1, interval=128)

        # CRG --------------------------------------------------------------------------------------
        self.crg = CRG(platform, sys_clk_freq,
            with_dram       = with_litedram_fifo,
            with_fft_window = with_fft_window,
        )

        # DDR3 SDRAM -------------------------------------------------------------------------------
        if with_litedram_fifo:
            self.ddrphy = s7ddrphy.A7DDRPHY(platform.request("ddram"),
                memtype        = "DDR3",
                nphases        = 4,
                sys_clk_freq   = sys_clk_freq)
            self.add_sdram("sdram",
                phy           = self.ddrphy,
                module        = MT41K512M16(sys_clk_freq, "1:4"),
                l2_cache_size = kwargs.get("l2_size", 8192)
            )

        # PCIe -------------------------------------------------------------------------------------
        if with_pcie:
            self.pcie_phy = S7PCIEPHY(platform, platform.request("pcie_x1"),
                data_width = 64,
                bar0_size  = 0x20000)
            self.add_pcie(phy=self.pcie_phy, ndmas=1)
            platform.toolchain.pre_placement_commands.append("reset_property LOC [get_cells -hierarchical -filter {{NAME=~pcie_s7/*gtp_channel.gtpe2_channel_i}}]")
            platform.toolchain.pre_placement_commands.append("set_property LOC GTPE2_CHANNEL_X0Y7 [get_cells -hierarchical -filter {{NAME=~pcie_s7/*gtp_channel.gtpe2_channel_i}}]")

            # PCIe QPLL Settings.
            qpll_pcie_settings = QPLLSettings(
                refclksel  = 0b001,
                fbdiv      = 5,
                fbdiv_45   = 5,
                refclk_div = 1,
            )

            platform.add_platform_command("set_property SEVERITY {{Warning}} [get_drc_checks REQP-49]")

            # Shared QPLL.
            self.qpll = qpll = QPLL(
                gtrefclk0     = self.pcie_phy.pcie_refclk,
                qpllsettings0 = qpll_pcie_settings,
                gtgrefclk1    = Open(),
                qpllsettings1 = None,
            )
            self.pcie_phy.use_external_qpll(qpll_channel=qpll.channels[0])

        # DMA Converters ---------------------------------------------------------------------------
        self.pre_conv  = ResetInserter()(stream.Converter(64, 32))
        self.post_conv = ResetInserter()(stream.Converter(32, 64))

        self.comb += [
            self.pcie_dma0.source.connect(self.pre_conv.sink),
            self.pre_conv.reset.eq(~self.pcie_dma0.writer.enable),

            self.post_conv.source.connect(self.pcie_dma0.sink),
            self.post_conv.reset.eq(~self.pcie_dma0.writer.enable),
        ]

        # SDR Processing ---------------------------------------------------------------------------
        self.sdr_processing = sdr_processing = SDRProcessing(platform, self,
            # LiteDRAMFIFO.
            with_litedram      = with_litedram_fifo,
            dram_data_width    = 32,
            dram_base          = 0x00000000,
            dram_depth         = 0x01000000, # 16MB
            dram_write_port    = self.sdram.crossbar.get_port(mode="write"),
            dram_read_port     = self.sdram.crossbar.get_port(mode="read"),

            # FIR.
            with_fir           = True,
            fir_data_in_width  = 16,
            fir_data_out_width = 16,
            fir_coeff_width    = 18,
            fir_decim_width    = 7,
            fir_oper_width     = 7,
            fir_macc_trunc     = 0,
            fir_len_log2       = 8,
            fir_clk_domain     = "sys",
            fir_with_csr       = True,

            # FFT.
            with_fft           = True,
            fft_data_width     = 16,
            fft_order_log2     = fft_order_log2,
            fft_radix          = fft_radix,
            fft_window         = with_fft_window,
            fft_cmult3x        = False,
            fft_clk_domain     = "sys",
        )

        self.comb += [
            # Converter -> SDR Processing Sink.
            self.pre_conv.source.connect(sdr_processing.sink),

            # SDR Processing Source -> DMA0 Sink.
            sdr_processing.source.connect(self.post_conv.sink, omit=["first", "last"]),

            # SDR Processing Reset.
            sdr_processing.reset.eq(~self.pcie_dma0.writer.enable),
        ]

        # Leds -------------------------------------------------------------------------------------
        if with_led_chaser:
            self.leds = LedChaser(
                pads         = platform.request_all("user_led"),
                sys_clk_freq = sys_clk_freq)

    def add_fft_datapath_probe(self):
        analyzer_signals = [
            self.fft.sink,
            self.fft.source,
            self.fft.re_in,
            self.fft.im_in,
            self.fft.re_out,
            self.fft.im_out,
        ]

        self.analyzer = LiteScopeAnalyzer(analyzer_signals,
            depth        = 1024,
            clock_domain = "sys",
            register     = True,
            csr_csv      = "analyzer.csv"
        )

# Build --------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="LiteX SoC on Acorn CLE-101/215(+).")

    # Build/Load/Utilities.
    parser.add_argument("--build",      action="store_true",      help="Build bitstream")
    parser.add_argument("--load",       action="store_true",      help="Load bitstream")
    parser.add_argument("--flash",      action="store_true",      help="Flash bitstream.")
    parser.add_argument("--variant",    default="cle-215+",       help="Board variant (cle-215+, cle-215 or cle-101).")
    parser.add_argument("--programmer", default="openfpgaloader", help="Programmer select from OpenOCD/openFPGALoader.",
        choices=[
            "openocd",
            "openfpgaloader"
    ])

    # FFT Configuration.
    parser.add_argument("--with-fft-window", action="store_true",      help="Enable FFT Windowing.")
    parser.add_argument("--fft-radix",       default="2",              help="Radix 2/4.")
    parser.add_argument("--fft-order-log2",  default=5,    type=int,   help="Log2 of the FFT order.")

    # Stream options.
    parser.add_argument("--with-litedram-fifo", action="store_true",   help="Enable LiteDRAM between DMA Writer and Reader.")

    # Litescope Analyzer Probes.
    probeopts = parser.add_mutually_exclusive_group()
    probeopts.add_argument("--with-fft-datapath-probe", action="store_true", help="Enable FFT Datapath Probe.")

    args = parser.parse_args()

    soc = BaseSoC(
        variant            = args.variant,
        with_pcie          = True,
        with_uartbone      = True,
        with_litedram_fifo = args.with_litedram_fifo,
        with_fft_window    = args.with_fft_window,
        fft_radix          = args.fft_radix,
        fft_order_log2     = args.fft_order_log2,
    )

    if args.with_fft_datapath_probe:
        soc.add_fft_datapath_probe()

    builder = Builder(soc, csr_csv="csr.csv", bios_console="lite")
    builder.build(run=args.build)

    # Generate LitePCIe Driver.
    generate_litepcie_software_headers(soc, "software/kernel")

    if args.load:
        prog = soc.platform.create_programmer(args.programmer)
        prog.load_bitstream(builder.get_bitstream_filename(mode="sram"))

    if args.flash:
        prog = soc.platform.create_programmer(args.programmer)
        prog.flash(0, builder.get_bitstream_filename(mode="flash"))

if __name__ == "__main__":
    main()
