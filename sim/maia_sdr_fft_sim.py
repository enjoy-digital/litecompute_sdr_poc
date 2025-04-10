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

from gateware.maia_sdr_fft import MaiaSDRFFT

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
    ("sys2x_clk", 0, Pins(1)),
]

class Platform(SimPlatform):
    default_clk_name = "clk_sys"
    def __init__(self):
        SimPlatform.__init__(self, "SIM", _io)

# Sim ----------------------------------------------------------------------------------------------

class SimSoC(SoCCore):
    def __init__(self, sys_clk_freq=int(200e6), data_width=16, stream_file=None,
        with_window    = False,
        radix          = "2",
        fft_order_log2 = 10,
        signal_freq    = 10e6,
        ):

        # Platform ---------------------------------------------------------------------------------
        platform  = Platform()
        self.comb += platform.trace.eq(1) # Always enable tracing.

        # CRG --------------------------------------------------------------------------------------
        sys_clk = platform.request("sys_clk")
        self.submodules.crg = CRG(sys_clk)

        self.cd_sys2x = ClockDomain()
        self.comb += [
            self.cd_sys2x.clk.eq(platform.request("sys2x_clk")),
            self.cd_sys2x.rst.eq(ResetSignal("sys")),
        ]

        # SoC --------------------------------------------------------------------------------------
        SoCMini.__init__(self, platform, clk_freq=sys_clk_freq)

        # MAIA SDR FFT -----------------------------------------------------------------------------
        self.fft = MaiaSDRFFT(platform,
            data_width  = data_width,
            order_log2  = fft_order_log2,
            radix       = radix,
            window      = {True: "blackmanharris", False: None}[with_window],
            cmult3x     = False,
            clk_domain  = "sys",
        )

        # Signals ----------------------------------------------------------------------------------
        re_out = Signal((self.fft.out_width, True))
        im_out = Signal((self.fft.out_width, True))

        self.comb += [
            re_out.eq(self.fft.source.re),
            im_out.eq(self.fft.source.im),
        ]

        # Streamer ---------------------------------------------------------------------------------
        if stream_file is None:
            streamer_data = generate_sample_data(signal_freq, sys_clk_freq, 10000, data_width)
        else:
            streamer_data = read_sample_data_from_file(stream_file, data_width)

        self.streamer = streamer = PacketStreamer(data_width * 2, streamer_data, 8)
        self.comb += [
            streamer.source.connect(self.fft.sink, omit=["data"]),
            self.fft.sink.re.eq(streamer.source.data[:data_width]),
            self.fft.sink.im.eq(streamer.source.data[data_width:]),
        ]

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
    parser.add_argument("--file",  default=None,        help="input stream file.")

    # FFT Configuration.
    parser.add_argument("--with-window",    action="store_true",      help="Enable FFT Windowing.")
    parser.add_argument("--radix",          default="2",              help="Radix 2/4.")
    parser.add_argument("--fft-order-log2", default=5,    type=int,   help="Log2 of the FFT order.")
    parser.add_argument("--signal-freq",    default=10e6, type=float, help="Input signal frequency.")

    args = parser.parse_args()

    sim_config = SimConfig(default_clk="sys_clk", default_clk_freq=int(1e6))
    if args.with_window:
        sim_config.add_clocker("sys2x_clk", int(2e6))

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
