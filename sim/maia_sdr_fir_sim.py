#!/usr/bin/env python3

#
# This file is part of LiteCompute PoC project.
#
# Copyright (c) 2025 Enjoy-Digital <enjoy-digital.fr>.
#
# SPDX-License-Identifier: BSD-2-Clause

import sys
import argparse

import matplotlib.pyplot as plt

import numpy as np

from litex.gen import *

from litex.build.generic_platform import *
from litex.build.sim import SimPlatform
from litex.build.sim.config import SimConfig

from litex.soc.integration.soc import SoCRegion
from litex.soc.integration.soc_core import *

from litex.soc.integration.builder import *

from litex.soc.interconnect        import stream

sys.path.append("..")

from utils import PacketStreamer, PacketChecker

from litecompute_poc.maia_hdl_fir_wrapper import MAIAHDLFIRWrapper

# Utils --------------------------------------------------------------------------------------------
def two_complement_encode(value, bits):
    if (value & (1 << (bits - 1))) != 0:
        value = value - (1 << bits)
    return value % (2**bits)

def generate_sample_data(frequency, sample_rate, repetitions, data_width):
    if sample_rate < 2 * frequency:
        print("Warning: Sample rate is less than twice the frequency, which may lead to aliasing.")

    gain        = (2 ** (data_width - 1)) - 1
    total_time  = repetitions / frequency  # total time for z periods
    num_samples = int(total_time * sample_rate) + 1
    t           = np.array([n / sample_rate for n in range(num_samples)])
    re_wave     = np.cos(2 * np.pi * frequency * t)
    im_wave     = np.sin(2 * np.pi * frequency * t)

    real        = np.int16(re_wave * gain)
    imag        = np.int16(im_wave * gain)
    stream_data = []

    with open("lut.txt", "w") as fd:
        for i in range(len(real)):
            re = two_complement_encode(int(real[i]), data_width)
            im = two_complement_encode(int(imag[i]), data_width)
            fd.write(f"{real[i]} {imag[i]} {re_wave[i]} {im_wave[i]}\n")
            stream_data.append((im << data_width) | (re))

    return stream_data

def read_sample_data_from_file(sample_file, data_width):
    samples = []
    i       = 0
    with open(sample_file, 'rb') as f:
        while True:
            if i == 1000:
                break
            i+= 1
            chunk = f.read(2)  # Read 16 bits (2 bytes)
            if not chunk:
                break
            re = int.from_bytes(chunk, byteorder='little', signed=False)  # Convert to integer
            chunk = f.read(2)  # Read 16 bits (2 bytes)
            if not chunk:
                break
            im = int.from_bytes(chunk, byteorder='little', signed=False)  # Convert to integer
            samples.append((im << data_width) | (re))
    return samples

# IOs ----------------------------------------------------------------------------------------------

_io = [
    # Clk / Rst.
    ("sys_clk",   0, Pins(1)),
]

class Platform(SimPlatform):
    default_clk_name = "clk_sys"
    def __init__(self):
        SimPlatform.__init__(self, "SIM", _io)

# Sim ----------------------------------------------------------------------------------------------

class SimSoC(SoCCore):
    def __init__(self, sys_clk_freq=int(200e6), data_width=12, stream_file=None,
        with_window    = False,
        radix          = 2,
        fft_order_log2 = 10,
        signal_freq    = 10e6,
        ):

        # Platform ---------------------------------------------------------------------------------
        platform  = Platform()
        self.comb += platform.trace.eq(1) # Always enable tracing.

        # CRG --------------------------------------------------------------------------------------
        sys_clk = platform.request("sys_clk")
        self.submodules.crg = CRG(sys_clk)

        # SoC --------------------------------------------------------------------------------------
        SoCMini.__init__(self, platform, clk_freq=sys_clk_freq)

        # Signals ----------------------------------------------------------------------------------
        re_out          = Signal((16, True))
        im_out          = Signal((16, True))
        coeff_write_end = Signal()

        # MAIA HDL FIR Wrapper ---------------------------------------------------------------------
        self.fir = fir = MAIAHDLFIRWrapper(platform,
            data_in_width  = data_width,
            data_out_width = [16] * 3,
            coeff_width    = 18,
            decim_width    = [7, 6, 7],
            oper_width     = [7, 6, 7],
            macc_trunc     = [17, 18, 18],
            cd_domain      = "sys",
            add_csr        = False,
        )

        self.comb += [
            # Bypass.
            fir.bypass2.eq(1),
            fir.bypass3.eq(1),

            # Decimations.
            fir.decimation1.eq(1),
            fir.decimation2.eq(1),
            fir.decimation3.eq(1),

            # Operations minus one.
            fir.operations_minus_one1.eq(32),
            fir.operations_minus_one2.eq(0),
            fir.operations_minus_one3.eq(0),

            # ODD Operations.
            fir.odd_operations1.eq(0),
            fir.odd_operations3.eq(0),
        ]

        # FSM (Coeff write).
        # ------------------
        self.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            NextValue(fir.coeff_waddr, 0),
            NextState("TRANSMIT")
        )
        fsm.act("TRANSMIT",
            NextValue(fir.coeff_waddr, fir.coeff_waddr + 1),
            fir.coeff_wdata.eq(1),
            fir.coeff_wren.eq(1),
            If(fir.coeff_waddr == 1023,
               NextState("END"),
            )
        )
        fsm.act("END",
           coeff_write_end.eq(1),
        )

        self.comb += [
            re_out.eq(fir.source.data[:16]),
            im_out.eq(fir.source.data[16:]),
        ]

        # Streamer ---------------------------------------------------------------------------------
        if stream_file is None:
            streamer_data = generate_sample_data(signal_freq, sys_clk_freq, 10000, data_width)
        else:
            streamer_data = read_sample_data_from_file(stream_file, data_width)

        self.streamer = streamer = PacketStreamer(data_width * 2, streamer_data, 0)
        self.comb += [
            streamer.source.connect(self.fir.sink, omit=["ready"]),
            streamer.source.ready.eq(fir.sink.ready & coeff_write_end),
        ]

        # Sim Debug --------------------------------------------------------------------------------
        self.sync += If(fir.source.valid, Display("%d %d", re_out, im_out))

        # Sim Finish -------------------------------------------------------------------------------
        self.sync += If(streamer.source.last, Finish())
        #self.sync += If(coeff_write_end, Finish())
        #cycles = Signal(32)
        #self.sync += cycles.eq(cycles + 1)
        #self.sync += If(cycles == 1000, Finish())

# Build --------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="MAIA SDR Simulation.")
    parser.add_argument("--trace", action="store_true", help="Enable VCD tracing.")
    parser.add_argument("--file",  default=None,        help="input stream file.")

    # FFT Configuration.
    parser.add_argument("--with-window",    action="store_true",      help="Enable FFT Windowing.")
    parser.add_argument("--radix",          default=2,    type=int,   help="Radix 2/4.")
    parser.add_argument("--fft-order-log2", default=5,    type=int,   help="Log2 of the FFT order.")
    parser.add_argument("--signal-freq",    default=10e6, type=float, help="Input signal frequency.")

    args = parser.parse_args()

    sim_config = SimConfig(default_clk="sys_clk", default_clk_freq=int(1e6))

    soc = SimSoC(stream_file=args.file,
        with_window    = args.with_window,
        radix          = args.radix,
        fft_order_log2 = args.fft_order_log2,
        signal_freq    = args.signal_freq,
    )
    builder = Builder(soc, output_dir="build/sim", csr_csv="csr.csv")
    builder.build(sim_config=sim_config, trace=args.trace, trace_fst=True)

if __name__ == "__main__":
    main()
