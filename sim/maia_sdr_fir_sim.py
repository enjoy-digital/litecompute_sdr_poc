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
from litex.soc.interconnect.csr    import CSRStorage, CSRField

from liteeth.phy.model import LiteEthPHYModel

sys.path.append("..")

from utils import PacketStreamer, PacketChecker, CoefficientsStreamer

from gateware.maia_sdr_fir import MaiaSDRFIR, compute_coefficients, model, clamp_nbits

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
            #samples.append((1 << data_width) | 1)
    return samples

# IOs ----------------------------------------------------------------------------------------------

_io = [
    # Clk / Rst.
    ("sys_clk",   0, Pins(1)),

    # Ethernet (Stream Endpoint).
    ("eth_clocks", 0,
        Subsignal("tx", Pins(1)),
        Subsignal("rx", Pins(1)),
    ),
    ("eth", 0,
        Subsignal("source_valid", Pins(1)),
        Subsignal("source_ready", Pins(1)),
        Subsignal("source_data",  Pins(8)),

        Subsignal("sink_valid",   Pins(1)),
        Subsignal("sink_ready",   Pins(1)),
        Subsignal("sink_data",    Pins(8)),
    ),
]

class Platform(SimPlatform):
    default_clk_name = "clk_sys"
    def __init__(self):
        SimPlatform.__init__(self, "SIM", _io)

# Sim ----------------------------------------------------------------------------------------------

class SimSoC(SoCCore):
    def __init__(self, sys_clk_freq=int(200e6), data_in_width=16, data_out_width=16,
        stream_file           = None,
        coeff_len             = 34,
        len_log2              = 8,
        signal_freq           = 10e6,
        with_etherbone        = False,
        etherbone_mac_address = 0x10e2d5000001,
        etherbone_ip_address  = "192.168.1.50",
        ethernet_remote_ip    = "192.168.1.100",
        ):

        # Platform ---------------------------------------------------------------------------------
        platform  = Platform()
        self.comb += platform.trace.eq(1) # Always enable tracing.

        # CRG --------------------------------------------------------------------------------------
        sys_clk = platform.request("sys_clk")
        self.submodules.crg = CRG(sys_clk)

        # SoC --------------------------------------------------------------------------------------
        SoCMini.__init__(self, platform, clk_freq=sys_clk_freq)

        # Constants --------------------------------------------------------------------------------
        operation = coeff_len // 2

        # Signals ----------------------------------------------------------------------------------
        coeff_write_end = Signal()

        # Coefficients Streamer --------------------------------------------------------------------
        (taps_len, taps_data, coeffs_data) = compute_coefficients(operation, 1, False, 2**len_log2)
        with open("coeff_lut.txt", "w") as fd:
            for i, c in enumerate(coeffs_data):
                fd.write(f"{i} {i:02x} {c}\n")
        with open("taps_lut.txt", "w") as fd:
            for i, c in enumerate(taps_data):
                fd.write(f"{i} {i:02x} {c}\n")

        assert taps_len == coeff_len
        self.coeff_streamer = CoefficientsStreamer(18, len_log2, coeffs_data)

        # MAIA SDR FIR -----------------------------------------------------------------------------
        self.fir = fir = MaiaSDRFIR(platform,
            data_in_width  = data_in_width,
            data_out_width = data_out_width,
            coeff_width    = 18,
            decim_width    = 7,
            oper_width     = 7,
            macc_trunc     = 0, #19,
            len_log2       = len_log2,
            clk_domain     = "sys",
            with_csr       = False,
        )

        self.comb += [
            # Decimations.
            fir.decimation.eq(1),

            # Operations minus one.
            fir.operations_minus_one.eq(operation - 1),

            # ODD Operations.
            fir.odd_operations.eq(0),
        ]

        # FSM (Coeff write).
        # ------------------
        self.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            NextState("TRANSMIT")
        )
        fsm.act("TRANSMIT",
            self.coeff_streamer.source.ready.eq(1),
            If(self.coeff_streamer.source.last,
                NextState("END"),
            ),
        )
        fsm.act("END",
            coeff_write_end.eq(1),
            self.coeff_streamer.source.ready.eq(0),
        )

        self.comb += [
            fir.coeff_wdata.eq(self.coeff_streamer.source.data),
            fir.coeff_waddr.eq(self.coeff_streamer.source.addr),
            fir.coeff_wren.eq( self.coeff_streamer.source.valid),
        ]

        # Streamer ---------------------------------------------------------------------------------
        if stream_file is None:
            streamer_data = generate_sample_data(signal_freq, sys_clk_freq, 10000, data_in_width)
        else:
            streamer_data = read_sample_data_from_file(stream_file, data_in_width)

        self.streamer = streamer = PacketStreamer(data_in_width * 2, streamer_data, 0)
        self.comb += [
            streamer.source.connect(self.fir.sink, omit=["ready", "valid", "data"]),
            streamer.source.ready.eq(fir.sink.ready & coeff_write_end),
            fir.sink.valid.eq(streamer.source.valid & coeff_write_end),
            fir.sink.re.eq(streamer.source.data[:data_out_width]),
            fir.sink.im.eq(streamer.source.data[data_out_width:]),
        ]

        # Checker ----------------------------------------------------------------------------------
        re_part      = [(((2**data_in_width)-1) & (streamer_data[i] >>             0)) for i in range(0, len(streamer_data), 1)]
        im_part      = [(((2**data_in_width)-1) & (streamer_data[i] >> data_in_width)) for i in range(0, len(streamer_data), 1)]
        checker_data = []
        re_part, im_part = model(0, data_in_width, taps_data, 1, re_part, im_part)
        with open("oracle.txt", "w") as fd:
            for i in range(len(re_part)):
                re = two_complement_encode(int(re_part[i]), data_out_width)
                im = two_complement_encode(int(im_part[i]), data_out_width)
                checker_data.append((im << data_out_width) | (re))
                fd.write(f"{re_part[i]} {im_part[i]}\n");

        self.checker = checker = PacketChecker(2 * data_out_width, checker_data, skip=len(taps_data))
        checker.add_debug("FIR")

        self.comb += [
            fir.source.connect(checker.sink, omit=["ready", "valid", "re", "im"]),
            fir.source.ready.eq(checker.sink.ready & coeff_write_end),
            checker.sink.valid.eq(fir.source.valid & coeff_write_end),
            checker.sink.data.eq(Cat(fir.source.re, fir.source.im)),
        ]

        # Etherbone --------------------------------------------------------------------------------
        if with_etherbone:
            self.ethphy = LiteEthPHYModel(self.platform.request("eth", 0))
            self.add_constant("HW_PREAMBLE_CRC")
            self.add_etherbone(
                phy         = self.ethphy,
                ip_address  = etherbone_ip_address,
                mac_address = etherbone_mac_address,
                data_width  = 8,
                # Ethernet Parameters.
                with_ethmac      = False,
                ethmac_address   = 0x10e2d5000000,
                ethmac_local_ip  = etherbone_ip_address,
                ethmac_remote_ip = ethernet_remote_ip,
            )

            self._coeff_ctrl = CSRStorage(description="Control Registers.", fields=[
                CSRField("coeff_write_end", size=1, offset=0, description="End Of Coefficient load.")
            ])

        # Sim Debug --------------------------------------------------------------------------------
        self.sync += If(fir.source.valid, Display("%d %d", fir.source.re, fir.source.im))
        #self.sync += If(fir.coeff_wren, Display("%x %x", fir.coeff_waddr, fir.coeff_wdata))

        # Sim Finish -------------------------------------------------------------------------------
        if not with_etherbone:
            self.sync += If(streamer.source.last, Finish())
        else:
            ##self.sync += If(coeff_write_end, Finish())
            cycles = Signal(32)
            ##self.sync += cycles.eq(cycles + 1)
            self.sync += If(cycles == 1000, Finish())

# Build --------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="MAIA SDR Simulation.")
    parser.add_argument("--trace",          action="store_true",     help="Enable VCD tracing.")
    parser.add_argument("--file",           default=None,            help="input stream file.")

    # Ethernet /Etherbone.
    parser.add_argument("--with-etherbone", action="store_true",     help="Enable Etherbone support.")
    parser.add_argument("--remote-ip",      default="192.168.1.100", help="Remote IP address of TFTP server.")
    parser.add_argument("--local-ip",       default="192.168.1.50",  help="Remote IP address of TFTP server.")

    # FIR Configuration.
    parser.add_argument("--signal-freq",    default=10e6, type=float, help="Input signal frequency.")

    args = parser.parse_args()

    sim_config = SimConfig(default_clk="sys_clk", default_clk_freq=int(1e6))
    if args.with_etherbone:
        sim_config.add_module("ethernet", "eth", args={"interface": "tap0", "ip": args.remote_ip})

    soc = SimSoC(stream_file=args.file,
        signal_freq          = args.signal_freq,
        with_etherbone       = args.with_etherbone,
        etherbone_ip_address = args.local_ip,
        ethernet_remote_ip   = args.remote_ip,
    )

    builder = Builder(soc, output_dir="build/sim", csr_csv="csr.csv")
    builder.build(sim_config=sim_config,
        trace=args.trace, trace_fst=True)

if __name__ == "__main__":
    main()
