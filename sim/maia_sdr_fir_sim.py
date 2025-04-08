#!/usr/bin/env python3

#
# This file is part of LiteCompute PoC project.
#
# Copyright (c) 2025 Enjoy-Digital <enjoy-digital.fr>.
#
# SPDX-License-Identifier: BSD-2-Clause

import subprocess
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

def read_binary_file(file_path, coeffs_width=18, signed=True, convert=False):
    samples = []
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(4)
            if not chunk:
                break
            value = int.from_bytes(chunk, byteorder='little', signed=signed)  # Convert to integer
            if convert:
                value = two_complement_encode(value, coeffs_width)
            samples.append(value)
    return samples

def two_complement_encode(value, bits):
    if (value & (1 << (bits - 1))) != 0:
        value = value - (1 << bits)
    return value % (2**bits)

def two_complement_decode(value, bits):
    if value >= (1 << (bits - 1)):
        value -= (1 << (bits))
    return value

def generate_sample_data(frequency, sample_rate, repetitions, data_width, num_taps, decimation):
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

    re_in = np.zeros(2048, 'int')
    for j in range(decimation):
        re_in[4 * num_taps * j + j + 10] = 1
    im_in = np.random.randint(-2**15, 2**15, size=re_in.size)
    im_in = np.arange(1, re_in.size + 1)
    # set first input samples to 0 to avoid results that do not match
    # the model due to initial samples being written in the wrong memory
    # locations
    keep_out = 7
    im_in[:keep_out] = 0

    with open("lut.txt", "w") as fd:
        fd.write(f"{decimation} {num_taps}\n")
        for i in range(len(re_in)):
            re = two_complement_encode(int(re_in[i]), data_width)
            im = two_complement_encode(int(im_in[i]), data_width)
            #fd.write(f"{re} {im} {int(re_in[i])} {int(im_in[i])}\n")
            fd.write(f"{int(re_in[i])} {int(im_in[i])}\n")
            stream_data.append((im << data_width) | (re))

    return (stream_data, re_in, im_in)

def read_sample_data_from_file(sample_file, data_width):
    samples = []
    re_in   = []
    im_in   = []
    i       = 0
    with open(sample_file, 'rb') as f:
        while True:
            if i == 1000:
                break
            i+= 1
            chunk = f.read(2)  # Read 16 bits (2 bytes)
            if not chunk:
                break
            re    = int.from_bytes(chunk, byteorder='little', signed=True)  # Convert to integer
            re_in.append(re)
            re    = two_complement_encode(re, data_width)

            chunk = f.read(2)  # Read 16 bits (2 bytes)
            if not chunk:
                break
            im    = int.from_bytes(chunk, byteorder='little', signed=True)  # Convert to integer
            im_in.append(im)
            im    = two_complement_encode(im, data_width)

            samples.append((im << data_width) | (re))
    return (samples, re_in, im_in)

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
    def __init__(self, sys_clk_freq=int(200e6),
        data_in_width         = 16,
        data_out_width        = 16,
        stream_file           = None,
        operations            = 6,
        odd_operations        = True,
        macc_trunc            = 17,
        coeffs_width          = 18,
        len_log2              = 8,
        decimation            = 2,
        sample_rate           = 4e6,
        cutoff_freq           = 600e3,
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
        num_mult  = operations * 2
        if odd_operations:
            num_mult -= 1
        coeff_len = num_mult * decimation

        # Signals ----------------------------------------------------------------------------------
        coeff_write_end = Signal()

        # Coefficients Streamer --------------------------------------------------------------------

        # Compute taps and coefficients.
        # ------------------------------
        cmd = [
            "../tools/gen_fir_taps.py",
            "--file",       "/tmp/coeffs.bin",
            "--taps-file",  "/tmp/taps.bin",
            "--fs",         str(sample_rate),
            "--fc",         str(cutoff_freq),
            "--length",     str(coeff_len),
            "--operations", str(operations),
            "--decimation", str(decimation),
            "--num-coeffs", str(2**len_log2),
            "--model",      "simple",
            {True: "--odd_operations", False: ""}[odd_operations],
        ]
        ret = subprocess.run(" ".join(cmd), shell=True)
        if ret.returncode != 0:
            raise OSError("Error occured during coefficients and taps generation.")

        # Read taps and coefficients from file.
        # -------------------------------------
        coeffs_data = read_binary_file("/tmp/coeffs.bin", coeffs_width, signed=False, convert=True)
        taps_data   = read_binary_file("/tmp/taps.bin",   coeffs_width, signed=True,  convert=False)
        #taps_data   = taps_data[:-1]
        assert len(taps_data) == coeff_len, f"{len(taps_data)} {coeff_len}"

        # Adds CoefficientsStreamer Module.
        # ---------------------------------
        self.coeff_streamer = CoefficientsStreamer(18, len_log2, coeffs_data, 32)

        # MAIA SDR FIR -----------------------------------------------------------------------------
        self.fir = fir = MaiaSDRFIR(platform,
            data_in_width  = data_in_width,
            data_out_width = data_out_width,
            coeff_width    = 18,
            decim_width    = 7,
            oper_width     = 7,
            macc_trunc     = macc_trunc,
            len_log2       = len_log2,
            clk_domain     = "sys",
            with_csr       = False,
        )

        self.comb += [
            # Decimations.
            fir.decimation.eq(decimation),

            # Operations minus one.
            fir.operations_minus_one.eq(operations - 1),

            # ODD Operations.
            fir.odd_operations.eq(odd_operations),
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

        # Read or Create input samples dataset.
        # -------------------------------------
        if stream_file is None:
            streamer_data, re_in, im_in = generate_sample_data(signal_freq, sample_rate, 10000, data_in_width,
                num_taps   = len(taps_data),
                decimation = decimation,
            )
        else:
            streamer_data, re_in, im_in = read_sample_data_from_file(stream_file, data_in_width)

        # Adds PacketStreamer Module and connect it to FIR instance.
        # ----------------------------------------------------------
        # The first sample must be dropped to match model.
        self.streamer = streamer = PacketStreamer(data_in_width * 2, streamer_data[1:], 0)
        self.comb += [
            streamer.source.connect(self.fir.sink, omit=["ready", "valid", "data"]),
            streamer.source.ready.eq(fir.sink.ready & coeff_write_end),
            fir.sink.valid.eq(streamer.source.valid & streamer.source.ready & coeff_write_end),
            fir.sink.re.eq(streamer.source.data[:data_in_width]),
            fir.sink.im.eq(streamer.source.data[data_in_width:]),
        ]

        # Checker ----------------------------------------------------------------------------------
        re_part      = [int(r) for r in re_in]
        im_part      = [int(i) for i in im_in]
        with open("t.txt", "w") as fd:
            for i in range(len(streamer_data)):
                fd.write(f"{re_part[i]} {im_part[i]}\n")
        checker_data = []

        # Create re/im based on model.
        re_part, im_part = model(macc_trunc, data_out_width, taps_data, decimation, re_part, im_part)

        with open("oracle.txt", "w") as fd:
            for i in range(len(re_part)):
                r  = re_part[i]
                i  = im_part[i]
                re = two_complement_encode(int(r), data_out_width)
                im = two_complement_encode(int(i), data_out_width)
                checker_data.append((im << data_out_width) | (re))
                fd.write(f"{r} {i}\n");

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

        # Force signed format.
        # --------------------
        re_signed = Signal((data_out_width, True))
        im_signed = Signal((data_out_width, True))
        self.comb += [
            re_signed.eq(fir.source.re),
            im_signed.eq(fir.source.im),
        ]
        self.sync += If(fir.source.valid, Display("%d %d", re_signed, im_signed))
        #self.sync += If(fir.coeff_wren, Display("%x %x", fir.coeff_waddr, fir.coeff_wdata))

        # Sim Finish -------------------------------------------------------------------------------
        if not with_etherbone:
            self.sync += If(streamer.source.last, Finish())
        else:
            #self.sync += If(coeff_write_end, Finish())
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
    parser.add_argument("--signal-freq",    default=10e6,  type=float, help="Input signal frequency.")
    parser.add_argument("--data-in-width",  default=16,    type=int,   help="FIR input data width.")
    parser.add_argument("--data-out-width", default=16,    type=int,   help="FIR output data width.")
    parser.add_argument("--sample-rate",    default=4e6,   type=float, help="sampling frequency.")
    parser.add_argument("--cutoff-freq",    default=600e3, type=float, help="cutoff Frequency.")
    parser.add_argument("--operations",     default=6,     type=int,   help="number of operation to performs.")
    parser.add_argument("--odd-operations", action="store_true",       help="is total operations is odd.")
    parser.add_argument("--macc-trunc",     default=0,     type=int,   help="Truncation length for output of each MACC.")
    parser.add_argument("--coeffs-width",   default=18,    type=int,   help="FIR coefficients width.")
    parser.add_argument("--len-log2",       default=8,     type=int,   help="FIR maximum coefficients RAM capacity (log2).")
    parser.add_argument("--decimation",     default=2,     type=int,   help="Decimate Factor.")

    args = parser.parse_args()

    sim_config = SimConfig(default_clk="sys_clk", default_clk_freq=int(1e6))
    if args.with_etherbone:
        sim_config.add_module("ethernet", "eth", args={"interface": "tap0", "ip": args.remote_ip})

    soc = SimSoC(stream_file=args.file,
        data_in_width        = args.data_in_width,
        data_out_width       = args.data_out_width,
        operations           = args.operations,
        odd_operations       = args.odd_operations,
        macc_trunc           = args.macc_trunc,
        coeffs_width         = args.coeffs_width,
        len_log2             = args.len_log2,
        decimation           = args.decimation,
        sample_rate          = args.sample_rate,
        cutoff_freq          = args.cutoff_freq,
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
