#
# Copyright (c) 2025 Enjoy-Digital <enjoy-digital.fr>
#
# SPDX-License-Identifier: BSD-2-Clause

import os

import numpy as np

from migen import *

from litex.gen import *

from litex.soc.interconnect import stream

from .clk_nx_common_edge import ClkNxCommonEdge

# Generator ----------------------------------------------------------------------------------------

def fft_generator(output_path, data_width=12, order_log2=12, radix=4, window=None, cmult3x=None):
    from amaranth.back.verilog import convert
    from maia_hdl.pluto_platform import PlutoPlatform
    from maia_hdl.fft import FFT
    w = window if window is not None else 'nowindow'
    truncates = {
        2: [0] * (order_log2 // 2) + [1] * (order_log2 // 2),
        4: [0] * (order_log2 // 4) + [2] * (order_log2 // 4),
        'R22': (
            [[0, 0]] * (order_log2 // 4)
            + [[1, 1]] * (order_log2 // 4)),
    }[radix]
    x3 = '_cmult3x' if cmult3x else ''
    file_out = os.path.join(output_path, f'fft_radix{radix}_{w}{x3}.v')
    m = FFT(data_width, order_log2, radix,
            width_twiddle=16,
            #truncates=truncates,
            use_bram_reg=True,
            window=window,
            cmult3x=cmult3x,
            domain_2x='clk2x' if window is not None else None,
            domain_3x='clk3x' if cmult3x else None)
    ports = [m.clken,
             m.re_in, m.im_in,
             m.re_out, m.im_out,
             m.out_last]
    if window is not None:
        ports.append(m.common_edge_2x)
    if cmult3x:
        ports.append(m.common_edge_3x)
    with open(file_out, 'w') as f:
        platform = PlutoPlatform()
        f.write(
            convert(
                m,
                name=f'fft_radix{radix}_{w}{x3}',
                ports=ports, platform=platform,
                emit_src=False))
    print('wrote verilog to', file_out)

# MAIAHDLFFTWrapper --------------------------------------------------------------------------------

class MAIAHDLFFTWrapper(LiteXModule):
    def __init__(self, platform,
        data_width   = 12,
        order_log2   = 12,
        radix        = 2,
        window       = None,
        cmult3x      = False,
        cd_domain    = "sys",
        cd_domain2x  = "fft_2x",
        cd_domain3x  = "fft_3x",
        ):

        # Prepare/Compute output data width --------------------------------------------------------
        # FIXME: considerer truncates is not used
        # FIXME: copied from FFT constructor
        bfly_trunc = {2: 1, 4: 2, 'R22': [1, 1]}[radix]
        radix_log2 = {2: 1, 4: 2, 'R22': 2}[radix]
        nstages    = order_log2 // radix_log2
        truncates  = [bfly_trunc] * nstages
        widths     = [data_width]
        w          = data_width
        for j in range(nstages):
            w += radix_log2 - int(np.sum(truncates[j]))
            widths.append(w)

        self.out_width = out_width = widths[-1]

        # Streams ----------------------------------------------------------------------------------
        self.sink   = sink   = stream.Endpoint([("data", 2 * data_width)])
        self.source = source = stream.Endpoint([("data", 2 * (out_width))])

        # Signals ----------------------------------------------------------------------------------
        self.reset = Signal()

        # Parameters/Locals ------------------------------------------------------------------------
        self.platform   = platform
        self.data_width = data_width
        self.order_log2 = order_log2
        self.radix      = radix
        self.window     = window
        self.cmult3x    = cmult3x

        # # #

        assert radix   in [2, 4, 'R22']
        assert window  in [None, 'blackmanharris']
        assert cmult3x in [False, True]

        # Signals.
        # --------
        self.re_in        = Signal(data_width)
        self.im_in        = Signal(data_width)
        self.re_out       = Signal(self.out_width)
        self.im_out       = Signal(self.out_width)
        self.source_first = Signal()

        self.ip_name = "fft_radix{radix}_{window}{cmult3x}".format(
            radix   = radix,
            window  = {True: "nowindow", False: "blackmanharris"}[window is None],
            cmult3x = {True:"_cmult3x",  False: ""}[cmult3x],
        )

        # FFT Instance -----------------------------------------------------------------------------

        self.ip_params = dict()
        self.ip_params.update(
            # Clk/Reset.
            i_clk      = ClockSignal(cd_domain),
            i_rst      = (ResetSignal(cd_domain) | self.reset),

            # Input
            i_re_in    = self.re_in,
            i_im_in    = self.im_in,
            i_clken    = self.sink.valid,

            # Output
            o_re_out   = self.re_out,
            o_im_out   = self.im_out,
            o_out_last = self.source.last,
        )

        # Windowing.
        if window is not None:
            self.clk_edge_x2 = ClockDomainsRenamer({"clk_x1": cd_domain, "clk_xn": cd_domain2x})(
                ClkNxCommonEdge(2)
            )

            self.ip_params.update(
                # Clk/Reset.
                i_clk2x_clk      = ClockSignal(cd_domain2x),
                i_clk2x_rst      = ResetSignal(cd_domain2x),

                i_common_edge_2x = self.clk_edge_x2.common_edge,
            )

        # One multiplier clocked at 3x cd_domain.
        if cmult3x:
            self.clk_edge_x3 = ClockDomainsRenamer({"clk_x1": cd_domain, "clk_xn": cd_domain3x})(
                ClkNxCommonEdge(3)
            )

            self.ip_params.update(
                # Clk/Reset.
                i_clk3x_clk      = ClockSignal(cd_domain3x),
                i_clk3x_rst      = ResetSignal(cd_domain3x),

                i_common_edge_3x = self.clk_edge_x3.common_edge
            )

        self.specials += Instance(self.ip_name, **self.ip_params)

        # Logic ------------------------------------------------------------------------------------

        # FFT module has no ready nor output valid (but re_out/im_out are updated one clock cycle after
        # clken/valid goes high).
        self.comb += [
            sink.ready.eq(1),
            source.first.eq(self.source_first),
        ]
        self.sync += source.valid.eq(sink.valid)

        self.sync += [
            If(source.last,
               self.source_first.eq(1),
            ).Elif(source.valid | self.reset,
               self.source_first.eq(0),
            )
        ]

        # Reconstruct samples.
        self.comb += [
            # Input.
            self.re_in.eq(self.sink.data[:data_width]),
            self.im_in.eq(self.sink.data[data_width:]),
            # Output.
            self.source.data.eq(Cat(self.re_out, self.im_out)),
        ]

    def do_finalize(self):
        src_dir  = os.path.join(self.platform.output_dir, "maia_hdl_fft")
        curr_dir = os.getcwd()

        # Create verilog files when not present.
        if not os.path.exists(src_dir):
            os.mkdir(src_dir)

        fft_generator(output_path=src_dir,
            data_width = self.data_width,
            order_log2 = self.order_log2,
            radix      = self.radix,
            window     = self.window,
            cmult3x    = self.cmult3x
        )

        self.platform.add_source(os.path.join(src_dir, self.ip_name + ".v"))
