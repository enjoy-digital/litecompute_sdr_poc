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
    data_in_width  = 12,
    data_out_width = [16] * 3,
    coeff_width    = 18,
    decim_width    = [7, 6, 7],
    oper_width     = [7, 6, 7],
    macc_trunc     = [17, 18, 18],
    ):

    from amaranth.back.verilog import convert
    from maia_hdl.pluto_platform import PlutoPlatform
    from maia_hdl.fir import FIRDecimator3Stage
    fir = FIRDecimator3Stage(
        in_width    = data_in_width,
        out_width   = data_out_width,
        coeff_width = coeff_width,
        decim_width = decim_width,
        oper_width  = oper_width,
        macc_trunc  = macc_trunc,
    )

    ports=[
        fir.coeff_waddr, fir.coeff_wren, fir.coeff_wdata,
        fir.decimation1, fir.decimation2, fir.decimation3,
        fir.bypass2, fir.bypass3,
        fir.operations_minus_one1, fir.operations_minus_one2,
        fir.operations_minus_one3,
        fir.odd_operations1, fir.odd_operations3,
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
        data_in_width  = 12,
        data_out_width = [16] * 3,
        coeff_width    = 18,
        decim_width    = [7, 6, 7],
        oper_width     = [7, 6, 7],
        macc_trunc     = [17, 18, 18],
        clk_domain     = "sys",
        with_csr       = True,
        ):

        # Streams ----------------------------------------------------------------------------------
        self.sink   = sink          = stream.Endpoint([("re", data_in_width), ("im", data_in_width)])
        self.source = source        = stream.Endpoint([("re", data_out_width), ("im", data_out_width)])

        # Parameters/Locals ------------------------------------------------------------------------
        self.platform               = platform
        self.data_in_width          = data_in_width
        self.data_out_width         = data_out_width
        self.coeff_width            = coeff_width
        self.decim_width            = decim_width
        self.oper_width             = oper_width
        self.macc_trunc             = macc_trunc

        # Bypass -----------------------------------------------------------------------------------
        self.bypass2               = Signal()
        self.bypass3               = Signal()

        # Decimation -------------------------------------------------------------------------------
        self.decimation1           = Signal(decim_width[0])
        self.decimation2           = Signal(decim_width[1])
        self.decimation3           = Signal(decim_width[2])

        # FIR Coefficient --------------------------------------------------------------------------
        self.coeff_wren            = Signal()
        self.coeff_waddr           = Signal(10)          # FIXME: size
        self.coeff_wdata           = Signal(coeff_width)

        # Operations Minus One ---------------------------------------------------------------------
        self.operations_minus_one1 = Signal(oper_width[0])
        self.operations_minus_one2 = Signal(oper_width[1])
        self.operations_minus_one3 = Signal(oper_width[2])

        # Odd Operations ---------------------------------------------------------------------------
        self.odd_operations1       = Signal()
        self.odd_operations3       = Signal()

        # # #

        # FIR Instance -----------------------------------------------------------------------------

        self.ip_name   = "fir"
        self.ip_params = dict()
        self.ip_params.update(
            # Clk/Reset.
            i_clk                   = ClockSignal(clk_domain),
            i_rst                   = ResetSignal(clk_domain),

            # FIR Coefficient.
            i_coeff_wren            = self.coeff_wren,
            i_coeff_wdata           = self.coeff_wdata,
            i_coeff_waddr           = self.coeff_waddr,

            # Decimation.
            i_decimation1           = self.decimation1,
            i_decimation2           = self.decimation2,
            i_decimation3           = self.decimation3,

            # Bypass.
            i_bypass2               = self.bypass2,
            i_bypass3               = self.bypass3,

            # Operations Minus One.
            i_operations_minus_one1 = self.operations_minus_one1,
            i_operations_minus_one2 = self.operations_minus_one2,
            i_operations_minus_one3 = self.operations_minus_one3,

            i_odd_operations1       = self.odd_operations1,
            i_odd_operations3       = self.odd_operations3,

            # Input
            i_re_in                 = sink.re,
            i_im_in                 = sink.im,
            i_in_valid              = sink.valid,
            o_in_ready              = sink.ready,

            # Output
            o_re_out                = source.re,
            o_im_out                = source.im,
            o_strobe_out            = source.valid,
        )

        self.specials += Instance(self.ip_name, **self.ip_params)

        if with_csr:
            self.with_csr()

    def with_csr(self):
        self._cfg = CSRStorage(description="Configuration Register.", fields=[
            CSRField("bypass2",         size=1, offset=0,            description="Bypass FIR stage 2."),
            CSRField("bypass3",         size=1, offset=1,            description="Bypass FIR stage 3."),
            CSRField("odd_operations1", size=1, offset=4,            description="ODD Operation 1"),
            CSRField("odd_operations3", size=1, offset=5,            description="ODD Operation 3"),
        ])

        self._decimation1 = CSRStorage(self.decim_width[0],          description="Decimation factor for Stage1.")
        self._decimation2 = CSRStorage(self.decim_width[1],          description="Decimation factor for Stage2.")
        self._decimation3 = CSRStorage(self.decim_width[2],          description="Decimation factor for Stage3.")

        self._coeff_waddr = CSRStorage(10,                           description="FIR Coefficient Address.") # FIXME: size
        self._coeff_wdata = CSRStorage(self.coeff_width,             description="FIR Coefficient Data.")

        self._operations_minus_one1 = CSRStorage(self.oper_width[0], description="Operations Minus One Stage 1.")
        self._operations_minus_one2 = CSRStorage(self.oper_width[1], description="Operations Minus One Stage 2.")
        self._operations_minus_one3 = CSRStorage(self.oper_width[2], description="Operations Minus One Stage 3.")

        self.comb += [
            # Bypass.
            self.bypass2.eq(self._cfg.fields.bypass2),
            self.bypass3.eq(self._cfg.fields.bypass3),

            # Decimations.
            self.decimation1.eq(self._decimation1.storage),
            self.decimation2.eq(self._decimation2.storage),
            self.decimation3.eq(self._decimation3.storage),

            # Coeff configuration.
            self.coeff_wren.eq(self._coeff_wdata.re),
            self.coeff_waddr.eq(self._coeff_waddr.storage),
            self.coeff_wdata.eq(self._coeff_wdata.storage),

            # Operations minus one.
            self.operations_minus_one1.eq(self._operations_minus_one1.storage),
            self.operations_minus_one2.eq(self._operations_minus_one2.storage),
            self.operations_minus_one3.eq(self._operations_minus_one3.storage),

            # ODD Operations.
            self.odd_operations1.eq(self._cfg.fields.odd_operations1),
            self.odd_operations3.eq(self._cfg.fields.odd_operations3),
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
        )

        self.platform.add_source(v_file)
