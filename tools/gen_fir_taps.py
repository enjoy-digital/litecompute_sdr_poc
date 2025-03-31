#!/usr/bin/env python3

#
# This file is part of LiteCompute PoC project.
#
# Copyright (c) 2025 Enjoy-Digital <enjoy-digital.fr>.
#
# SPDX-License-Identifier: BSD-2-Clause

import sys
import argparse
import numpy as np
import matplotlib.pyplot as plt
import struct

sys.path.append("../..")
from gateware.maia_sdr_fir import compute_coefficients

def main():
    parser = argparse.ArgumentParser(description="FIR Generator.")
    parser.add_argument("--file",       default=None,            help="output coefficients file.")

    # TAPS configuration.
    parser.add_argument("--fs",         default=10000, type=float, help="Sampling Frequency (Hz).")
    parser.add_argument("--fc",         default=100,   type=float, help="Cutoff Frequency (Hz).")
    parser.add_argument("--length",     default=100,   type=int,   help="Filter length.")
    parser.add_argument("--coeff-size", default=16,    type=int,   help="Coefficients Size.")
    parser.add_argument("--bypass-gen"  action="store_true",       help="Use locally computed pseudo Coeff table.")

    # FIR parameters.
    parser.add_argument("--operations",     default=16,  type=int, help="Number of operations.")
    parser.add_argument("--odd_operations", action="store_true",   help="Is ODD operations.")
    parser.add_argument("--decimation",     default=2,   type=int, help="Decimation factor.")
    parser.add_argument("--num-coeffs",     default=256, type=int, help="Maximum Number of coefficents.")

    args = parser.parse_args()

    assert args.file is not None

    h = []
    if not args.bypass_gen:
        # Normalized cutoff frequency
        fc_normalized = args.fc / args.fs

        # Time vector centered at 0
        t = np.arange(-(args.length-1)//2, (args.length-1)//2 + 1)

        # Sinc function for ideal low-pass filter
        h = 2 * fc_normalized * np.sinc(2 * fc_normalized * t)

        # Apply a window (e.g., Hamming) to smooth the filter
        window = np.hamming(args.length)
        h = h * window

        # Normalize the filter to ensure unity gain at DC
        h = h / np.max(h)
        # Apply gain to fit coeff_size
        gain = 2**(args.coeff_size -1) -1 # Maximum positive value
        h = h * gain

    (len_taps, _, coeffs) = compute_coefficients(args.operations,
        args.decimation, args.odd_operations, args.num_coeffs, h)
    print(len_taps)

    with open(args.file, "wb") as fd:
        # '<i' specifies little-endian signed 32-bit integer
        for value in coeffs:
            # Pack each integer into 4 bytes in little-endian format
            binary_data = struct.pack('<i', value)
            fd.write(binary_data)

    # Plot the filter
    plt.plot(t, h)
    plt.title('Low-Pass Filter Kernel')
    plt.xlabel('Sample')
    plt.ylabel('Amplitude')
    plt.grid(True)
    plt.show()

if __name__ == "__main__":
    main()
