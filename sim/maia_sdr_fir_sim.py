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

def compute_fir_response(re_in, im_in, coefficients):
    # Get lengths
    signal_len = len(re_in)
    coeff_len  = len(coefficients)
    output_len = signal_len - coeff_len + 1

    # Check if we have enough data
    if signal_len < coeff_len:
        return []

    # Initialize output list
    output = []

    # Compute convolution manually
    for i in range(output_len):
        # Calculate one output sample (complex)
        real_part = 0
        imag_part = 0
        for j in range(coeff_len):
            # Multiply complex input by real coefficient
            real_part += re_in[i + j] * coefficients[j]
            imag_part += im_in[i + j] * coefficients[j]
        output.append(real_part)
        output.append(imag_part)

    return output

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
    def __init__(self, sys_clk_freq=int(200e6), data_in_width=16, data_out_width=16,
        stream_file = None,
        coeff_len   = 32,
        signal_freq = 10e6,
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
        re_out          = Signal((data_out_width, True))
        im_out          = Signal((data_out_width, True))
        coeff_write_end = Signal()

        # MAIA HDL FIR Wrapper ---------------------------------------------------------------------
        self.fir = fir = MAIAHDLFIRWrapper(platform,
            data_in_width  = data_in_width,
            data_out_width = data_out_width,
            coeff_width    = 18,
            decim_width    = 7,
            oper_width     = 7,
            macc_trunc     = 0, #19,
            len_log2       = 8,
            cd_domain      = "sys",
            add_csr        = False,
        )

        self.comb += [
            # Decimations.
            fir.decimation.eq(1),

            # Operations minus one.
            fir.operations_minus_one.eq(coeff_len // 2),

            # ODD Operations.
            fir.odd_operations.eq(0),
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
            If(fir.coeff_waddr == coeff_len - 1,
               NextState("END"),
            )
        )
        fsm.act("END",
           coeff_write_end.eq(1),
        )

        self.comb += [
            re_out.eq(fir.source.data[:data_out_width]),
            im_out.eq(fir.source.data[data_out_width:]),
        ]

        # Streamer ---------------------------------------------------------------------------------
        if stream_file is None:
            streamer_data = generate_sample_data(signal_freq, sys_clk_freq, 10000, data_in_width)
        else:
            streamer_data = read_sample_data_from_file(stream_file, data_in_width)

        self.streamer = streamer = PacketStreamer(data_in_width * 2, streamer_data, 0)
        self.comb += [
            streamer.source.connect(self.fir.sink, omit=["ready"]),
            streamer.source.ready.eq(fir.sink.ready & coeff_write_end),
        ]

        # Checker ----------------------------------------------------------------------------------
        re_part      = [i for i in range(0, len(streamer_data), 2)]
        im_part      = [i for i in range(1, len(streamer_data), 2)]
        checker_data = compute_fir_response(re_part, im_part, [1]*coeff_len)

        self.checker = checker = PacketChecker(data_out_width, checker_data)

        self.comb += fir.source.connect(checker.sink)

        # Sim Debug --------------------------------------------------------------------------------
        self.sync += If(fir.source.valid, Display("%d %d", re_out, im_out))

        # Sim Finish -------------------------------------------------------------------------------
        self.sync += If(streamer.source.last, Finish())

# Build --------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="MAIA SDR Simulation.")
    parser.add_argument("--trace", action="store_true", help="Enable VCD tracing.")
    parser.add_argument("--file",  default=None,        help="input stream file.")

    # FFT Configuration.
    parser.add_argument("--signal-freq",    default=10e6, type=float, help="Input signal frequency.")

    args = parser.parse_args()

    sim_config = SimConfig(default_clk="sys_clk", default_clk_freq=int(1e6))

    soc = SimSoC(stream_file=args.file,
        signal_freq = args.signal_freq,
    )
    builder = Builder(soc, output_dir="build/sim", csr_csv="csr.csv")
    builder.build(sim_config=sim_config, trace=args.trace, trace_fst=True)

if __name__ == "__main__":
    main()
