#
# Copyright (c) 2025 Enjoy-Digital <enjoy-digital.fr>
#
# SPDX-License-Identifier: BSD-2-Clause

import os

import numpy as np

from migen import *

from litex.gen import *

from litedram.frontend.fifo import LiteDRAMFIFO

from litex.soc.interconnect     import stream
from litex.soc.interconnect.csr import *

from gateware.maia_sdr_fft import MaiaSDRFFT
from gateware.maia_sdr_fir import MaiaSDRFIR

# SDR Processing -----------------------------------------------------------------------------------

class SDRProcessing(LiteXModule):
    def __init__(self, platform, soc,
        with_litedram      = False,
        dram_write_port    = None,
        dram_read_port     = None,
        dram_data_width    = 32,
        dram_base          = 0x00000000,
        dram_depth         = 0x01000000,

        # FIR.
        with_fir           = False,
        fir_data_in_width  = 16,
        fir_data_out_width = 16,
        fir_coeff_width    = 18,
        fir_decim_width    = 7,
        fir_oper_width     = 7,
        fir_macc_trunc     = 19,
        fir_len_log2       = 8,
        fir_clk_domain     = "sys",
        fir_with_csr       = True,

        # FFT.
        with_fft           = False,
        fft_data_width     = 12,
        fft_order_log2     = 12,
        fft_radix          = 2,
        fft_window         = True,
        fft_cmult3x        = False,
        fft_clk_domain     = "sys",
        ):

        # Streams ----------------------------------------------------------------------------------
        self.sink   = sink   = stream.Endpoint([("data", 2 * fir_data_in_width)])
        self.source = source = stream.Endpoint([("data", 2 * fft_data_width)])

        # SDR DSP Generals CSR (FIR/FFT/LiteDRAM enable/disable (bypass) ---------------------------
        if with_fft or with_fir or with_litedram:
            self._configuration = CSRStorage(description="Stream Configuration.", fields=[
                CSRField("fir", size=1, offset=0, values=[
                    ("``0b0``", "Disable FIR Filter."),
                    ("``0b1``", "Enable  FIR Filter."),
                ], reset = 0b1),
                CSRField("fft", size=1, offset=1, values=[
                    ("``0b0``", "Disable FFT."),
                    ("``0b1``", "Enable  FFT."),
                ], reset = 0b1),
                CSRField("litedram_fifo", size=1, offset=2, values=[
                    ("``0b0``", "Disable LiteDRAMFIFO."),
                    ("``0b1``", "Enable  LiteDRAMFIFO."),
                ], reset = 0b1),
            ])

        # reset/disable input signal.
        self.reset = Signal()

        # # #

        # Signals.
        # FIXME: size must be correctly adapted
        ep0 = stream.Endpoint([("re", fir_data_in_width),  ("im", fir_data_in_width)])
        ep1 = stream.Endpoint([("re", fir_data_out_width), ("im", fir_data_out_width)])
        ep2 = stream.Endpoint([("re", fft_data_width),     ("im", fft_data_width)])

        # LiteDRAMFIFO.
        # -------------
        if with_litedram:
            self.fifo_dsp = fifo_dsp = LiteDRAMFIFO(
                data_width  = dram_data_width,
                base        = dram_base,
                depth       = dram_depth,
                write_port  = dram_write_port,
                read_port   = dram_read_port,
                with_bypass = True
            )

        # MAIA SDR FFT.
        # -------------
        if with_fft:
            self.fft = MaiaSDRFFT(platform,
                data_width  = fft_data_width,
                order_log2  = fft_order_log2,
                radix       = fft_radix,
                window      = {True: "blackmanharris", False: None}[fft_window],
                cmult3x     = fft_cmult3x,
                clk_domain  = fft_clk_domain,
            )
            self.fft.add_constants(soc)

            # Window Clocking.
            # ----------------
            if fft_window:
                self.cd_sys2x = ClockDomain()

                # FIXME: can't be here
                soc.crg.pll.create_clkout(self.cd_sys2x, soc.sys_clk_freq * 2)

            # MAIA SDR FFT Logic.
            # -------------------
            # Disables/clear FFT when no stream.
            self.comb += self.fft.reset.eq(self.reset),

        # MAIA SDR FIR.
        # -------------
        if with_fir:
            # MAIA SDR FIR Status.
            #---------------------
            self._fir_status = CSRStatus(description="FIR Status", fields=[
                CSRField("overflow", size=1, offset=0),
            ])

            # FIFO to check overflow.
            fir_fifo_ready_d = Signal()
            self.fir_fifo    = ResetInserter()(stream.SyncFIFO([("data", 2 * fir_data_in_width)], 16))
            self.fir = fir   = MaiaSDRFIR(platform,
                data_in_width  = fir_data_in_width,
                data_out_width = fir_data_out_width,
                coeff_width    = fir_coeff_width,
                decim_width    = fir_decim_width,
                oper_width     = fir_oper_width,
                macc_trunc     = fir_macc_trunc,
                len_log2       = fir_len_log2,
                clk_domain     = fir_clk_domain,
                with_csr       = fir_with_csr,
            )

            # MAIA SDR FIR Logic.
            # -------------------
            # Store ready -> not ready for FIR FIFO (means FIR is too slow).
            self.sync += [
                fir_fifo_ready_d.eq(self.fir_fifo.sink.ready),
                If(self.reset,
                    self._fir_status.fields.overflow.eq(0),
                ).Elif(~self.fir_fifo.sink.ready & fir_fifo_ready_d,
                    self._fir_status.fields.overflow.eq(1),
                )
            ]

            self.comb += self.fir_fifo.reset.eq(self.reset),

        # RFIC -> FIFO -> [MaiaSDRFIR] -> MaiaSDRFFT -> PCIe.
        # ---------------------------------------------------

        # Default data path (everything in bypass).
        self.comb += [
            # sink -> ep0.
            sink.connect(ep0, omit=["data"]),
            ep0.re.eq(sink.data[0: fir_data_in_width]),
            ep0.im.eq(sink.data[fir_data_in_width:]),

            # ep0 -> ep1.
            ep0.connect(ep1),

            # ep1 -> ep2.
            ep1.connect(ep2),

            # ep2 -> Converter.
            ep2.connect(source, omit=["re", "im"]),
            self.source.data.eq(Cat(ep2.re, ep2.im)),
        ]

        # LiteDRAM Integration.
        # ---------------------
        if with_litedram:
            self.comb += [
                If(self._configuration.fields.litedram_fifo,
                    sink.connect(self.fifo_dsp.sink),
                    fifo_dsp.source.connect(ep0, omit=["data"]),
                    ep0.re.eq(fifo_dsp.source.data[0: fir_data_in_width]),
                    ep0.im.eq(fifo_dsp.source.data[fir_data_in_width:]),
                ),
            ]

        # FIR Integration.
        # ----------------
        if with_fir:
            self.comb += If(self._configuration.fields.fir,
                ep0.connect(self.fir.sink),
                self.fir.source.connect(ep1),
            ),

        # FFT Integration.
        # ----------------
        if with_fft:
            self.comb += [
                If(self._configuration.fields.fft,
                    ep1.connect(self.fft.sink),
                    self.fft.source.connect(ep2),
                ),
            ]
