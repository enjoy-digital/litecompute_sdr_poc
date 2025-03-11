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

from litecompute_poc.maia_hdl_fft_wrapper import MAIAHDLFFTWrapper

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

    for i in range(len(real)):
        re = two_complement_encode(int(real[i]), data_width)
        im = two_complement_encode(int(imag[i]), data_width)
        stream_data.append((im << data_width) | (re))

    return stream_data

# IOs ----------------------------------------------------------------------------------------------

_io = [
    # Clk / Rst.
    ("sys_clk",  0, Pins(1)),
]

class Platform(SimPlatform):
    default_clk_name = "clk_sys"
    def __init__(self):
        SimPlatform.__init__(self, "SIM", _io)

# Sim ----------------------------------------------------------------------------------------------

class SimSoC(SoCCore):
    def __init__(self, sys_clk_freq=int(100e6), data_width=16):

        # Platform ---------------------------------------------------------------------------------
        platform  = Platform()
        self.comb += platform.trace.eq(1) # Always enable tracing.

        # CRG --------------------------------------------------------------------------------------
        sys_clk = platform.request("sys_clk")
        self.submodules.crg = CRG(sys_clk)

        # SoC --------------------------------------------------------------------------------------
        SoCMini.__init__(self, platform, clk_freq=sys_clk_freq)

        # MAIA HDL FFT Wrapper ---------------------------------------------------------------------
        self.fft = MAIAHDLFFTWrapper(platform,
            data_width = data_width,
            order_log2 = 10,
            radix      = 4,
            window     = None,
            cmult3x    = False,
            cd_domain  = "sys",
        )

        # Signals ----------------------------------------------------------------------------------
        re_out = Signal((self.fft.out_width, True))
        im_out = Signal((self.fft.out_width, True))

        self.comb += [
            re_out.eq(self.fft.source.data[:self.fft.out_width]),
            im_out.eq(self.fft.source.data[self.fft.out_width:]),
        ]

        # Streamer ---------------------------------------------------------------------------------
        streamer_data = generate_sample_data(25e6, sys_clk_freq, 1000, data_width)

        self.streamer = streamer = PacketStreamer(data_width * 2, streamer_data, 8)
        self.comb += streamer.source.connect(self.fft.sink)

        # Sim Debug --------------------------------------------------------------------------------
        self.sync += If(self.fft.source.valid, Display("%d %d %d", re_out, im_out, self.fft.source.last))

        # Sim Finish -------------------------------------------------------------------------------
        self.sync += If(streamer.source.last, Finish())

    def plot_array(self, re, im):
        # Generate x values automatically (0, 1, 2, ...)
        x = np.arange(len(re))

        # Plot the data
        plt.plot(x, re, color='red')
        plt.plot(x, im, color='blue')

        # Add labels and title
        plt.xlabel("Index")
        plt.ylabel("Value")
        plt.title("Simple Plot with One Array")

        # Show the plot
        plt.show()

# Build --------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="MAIA SDR Simulation.")
    parser.add_argument("--trace", action="store_true", help="Enable VCD tracing.")
    args = parser.parse_args()

    sim_config = SimConfig(default_clk="sys_clk")

    soc = SimSoC()
    builder = Builder(soc, output_dir="build/sim", csr_csv="csr.csv")
    builder.build(sim_config=sim_config, trace=args.trace, trace_fst=True)

if __name__ == "__main__":
    main()
