#
# Copyright (c) 2025 Enjoy-Digital <enjoy-digital.fr>
#
# SPDX-License-Identifier: BSD-2-Clause

import os

import numpy as np

from migen import *

from litex.gen import *

from litex.soc.interconnect     import stream
from litex.soc.interconnect.csr import *

from .clk_nx_common_edge import ClkNxCommonEdge

# Generator ----------------------------------------------------------------------------------------

def fir_generator(output_path,
    data_in_width  = 16,
    data_out_width = 16,
    coeff_width    = 18,
    decim_width    = 7,
    oper_width     = 7,
    macc_trunc     = 19,
    len_log2       = 8, # Maximum FIR length is log2
    ):

    from amaranth.back.verilog import convert
    from maia_hdl.pluto_platform import PlutoPlatform
    from maia_hdl.fir import FIR4DSP
    fir = FIR4DSP(
        in_width    = data_in_width,
        out_width   = data_out_width,
        coeff_width = coeff_width,
        decim_width = decim_width,
        oper_width  = oper_width,
        macc_trunc  = macc_trunc,
        len_log2    = len_log2,
    )

    ports=[
        fir.coeff_waddr, fir.coeff_wren, fir.coeff_wdata,
        fir.decimation,
        fir.operations_minus_one,
        fir.odd_operations,
        fir.re_in, fir.im_in, fir.in_valid, fir.in_ready,
        fir.re_out, fir.im_out, fir.strobe_out
    ]

    with open(output_path, 'w') as f:
        platform = PlutoPlatform()
        f.write(convert(fir,
            name     = f"fir",
            ports    = ports,
            platform = platform,
            emit_src = False)
        )

    print('wrote verilog to', output_path)

# MaiaSDRFIR ---------------------------------------------------------------------------------------

class MaiaSDRFIR(LiteXModule):
    def __init__(self, platform,
        data_in_width  = 16,
        data_out_width = 16,
        coeff_width    = 18,
        decim_width    = 7,
        oper_width     = 7,
        macc_trunc     = 19,
        len_log2       = 8,
        clk_domain     = "sys",
        with_csr       = True,
        ):

        # Streams ----------------------------------------------------------------------------------
        self.sink   = sink        = stream.Endpoint([("re", data_in_width), ("im", data_in_width)])
        self.source = source      = stream.Endpoint([("re", data_out_width), ("im", data_out_width)])

        # Parameters/Locals ------------------------------------------------------------------------
        self.platform             = platform
        self.data_in_width        = data_in_width
        self.data_out_width       = data_out_width
        self.coeff_width          = coeff_width
        self.decim_width          = decim_width
        self.oper_width           = oper_width
        self.macc_trunc           = macc_trunc
        self.len_log2             = len_log2

        # Decimation -------------------------------------------------------------------------------
        self.decimation           = Signal(decim_width)
        # FIR Coefficient --------------------------------------------------------------------------
        self.coeff_wren           = Signal()
        self.coeff_waddr          = Signal(len_log2)
        self.coeff_wdata          = Signal(coeff_width)

        # Operations Minus One ---------------------------------------------------------------------
        self.operations_minus_one = Signal(oper_width)

        # Odd Operations ---------------------------------------------------------------------------
        self.odd_operations       = Signal()

        # # #

        # FIR Instance -----------------------------------------------------------------------------

        self.ip_name   = "fir"
        self.ip_params = dict()
        self.ip_params.update(
            # Clk/Reset.
            i_clk                  = ClockSignal(clk_domain),
            i_rst                  = ResetSignal(clk_domain),

            # FIR Coefficient.
            i_coeff_wren           = self.coeff_wren,
            i_coeff_wdata          = self.coeff_wdata,
            i_coeff_waddr          = self.coeff_waddr,

            # Decimation.
            i_decimation           = self.decimation,

            # Operations Minus One.
            i_operations_minus_one = self.operations_minus_one,

            # Number of Operations.
            i_odd_operations       = self.odd_operations,

            # Input
            i_re_in                = sink.re,
            i_im_in                = sink.im,
            i_in_valid             = sink.valid,
            o_in_ready             = sink.ready,

            # Output
            o_re_out               = source.re,
            o_im_out               = source.im,
            o_strobe_out           = source.valid,
        )

        self.specials += Instance(self.ip_name, **self.ip_params)

        if with_csr:
            self.with_csr()

    def with_csr(self):
        self._cfg = CSRStorage(description="Configuration Register.", fields=[
            CSRField("odd_operations", size=1, offset=0,         description="ODD Operation"),
        ])

        self._decimation = CSRStorage(self.decim_width,          description="Decimation factor for Stage.")

        self._coeff_waddr = CSRStorage(self.len_log2,            description="FIR Coefficient Address.")
        self._coeff_wdata = CSRStorage(self.coeff_width,         description="FIR Coefficient Data.")

        self._operations_minus_one = CSRStorage(self.oper_width, description="Operations Minus One Stage.")

        self.comb += [
            # Decimations.
            self.decimation.eq(self._decimation.storage),

            # Coeff configuration.
            self.coeff_wren.eq(self._coeff_wdata.re),
            self.coeff_waddr.eq(self._coeff_waddr.storage),
            self.coeff_wdata.eq(self._coeff_wdata.storage),

            # Operations minus one.
            self.operations_minus_one.eq(self._operations_minus_one.storage),

            # ODD Operations.
            self.odd_operations.eq(self._cfg.fields.odd_operations),
        ]

    def do_finalize(self):
        src_dir  = os.path.join(self.platform.output_dir, "maia_hdl_fir")
        v_file   = os.path.join(src_dir, self.ip_name + ".v")

        # Create verilog files when not present.
        if not os.path.exists(src_dir):
            os.mkdir(src_dir)

        fir_generator(output_path=v_file,
            data_in_width  = self.data_in_width,
            data_out_width = self.data_out_width,
            coeff_width    = self.coeff_width,
            decim_width    = self.decim_width,
            oper_width     = self.oper_width,
            macc_trunc     = self.macc_trunc,
            len_log2       = self.len_log2,
        )

        self.platform.add_source(v_file)
