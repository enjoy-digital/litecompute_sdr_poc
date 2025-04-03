#!/usr/bin/env python3

#
# This file is part of LiteCompute PoC project.
#
# Copyright (c) 2025 Enjoy-Digital <enjoy-digital.fr>.
#
# SPDX-License-Identifier: BSD-2-Clause

import sys
import argparse
import pm_remez
import struct
import matplotlib.pyplot as plt
import numpy as np
from scipy import signal

sys.path.append("../..")
from gateware.maia_sdr_fir import compute_coefficients

def design_antialias_lowpass(decimation, transition_bandwidth, numtaps,
    stopband_weight = 1.0,
    one_over_f      = False,
    bigfloat        = False,
    worN            = 4096):

    passband_end   = 0.5 * (1 - transition_bandwidth) / decimation
    stopband_start = 0.5 * (1 + transition_bandwidth) / decimation

    # Stopband weight is a constant or linear slope depending

    # on one_over_f parameter.
    sweight = ((stopband_weight, stopband_weight * 0.5 / stopband_start)
        if one_over_f else stopband_weight)

    design = pm_remez.remez(numtaps, [0, passband_end, stopband_start, 0.5],
        [1, 0], weight=[1, sweight], bigfloat=bigfloat)
    return design.impulse_response

def main():
    parser = argparse.ArgumentParser(description="FIR Generator.")
    parser.add_argument("--file",       default=None,            help="output coefficients file.")
    parser.add_argument("--taps-file",  default=None,            help="output Taps file.")

    # TAPS configuration.
    parser.add_argument("--model",      default="pm-remez",        help="Coefficients Model.")
    parser.add_argument("--fs",         default=10000, type=float, help="Sampling Frequency (Hz).")
    parser.add_argument("--fc",         default=100,   type=float, help="Cutoff Frequency (Hz).")
    parser.add_argument("--length",     default=100,   type=int,   help="Filter length.")
    parser.add_argument("--coeff-size", default=16,    type=int,   help="Coefficients Size.")
    parser.add_argument("--bypass-gen", action="store_true",       help="Use locally computed pseudo Coeff table.")

    # FIR parameters.
    parser.add_argument("--operations",     default=16,  type=int, help="Number of operations.")
    parser.add_argument("--odd_operations", action="store_true",   help="Is ODD operations.")
    parser.add_argument("--decimation",     default=2,   type=int, help="Decimation factor.")
    parser.add_argument("--num-coeffs",     default=256, type=int, help="Maximum Number of coefficents.")

    # Utils.
    parser.add_argument("display-coefficients", action="store_true", help="display coefficients table.")

    args = parser.parse_args()

    assert args.file is not None

    h        = []
    num_taps = args.length
    fs       = args.fs
    fc       = args.fc
    if not args.bypass_gen:
        if args.model == "simple":
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
        elif args.model == "firls":
            # Normalize frequency to 0-1 range (Nyquist = 1)
            f_nyquist = fs / 2
            f_norm = fc / f_nyquist

            # Ensure num_taps is odd
            if num_taps % 2 == 0:
                num_taps += 1

            # Define frequency points and desired amplitude
            bands = [0, f_norm, f_norm + 0.1, 1]  # Normalized frequency points
            desired = [1, 1, 0, 0]               # Desired amplitude

            # Compute coefficients using firls
            h = signal.firls(num_taps, bands, desired)

            # Normalize to 1.
            h = h / np.max(np.abs(h))
        elif args.model == "pm-remez":
            # Normalize frequency to 0-1 range (Nyquist = 1)
            f_nyquist = fs / 2
            f_norm    = fc / f_nyquist
            h         = design_antialias_lowpass(args.decimation, f_norm, args.length)
            # Normalize to 1.
            h         = h / np.max(np.abs(h))
        else:
            print(error)

        # Apply gain to fit coeff_size
        gain = 2**(args.coeff_size -1) -1 # Maximum positive value
        h    = h * gain

    (len_taps, _, coeffs) = compute_coefficients(args.operations,
        args.decimation, args.odd_operations, args.num_coeffs, h)

    with open(args.taps_file, "wb") as fd:
        for value in h:
            binary_data = struct.pack('<i', int(value))
            fd.write(binary_data)

    with open(args.file, "wb") as fd:
        for value in coeffs:
            binary_data = struct.pack('<i', value)
            fd.write(binary_data)

    # Plot the filter
    if False and args.display_coefficients:
        plt.plot(h)
        plt.title('Low-Pass Filter Kernel')
        plt.xlabel('Sample')
        plt.ylabel('Amplitude')
        plt.grid(True)
        plt.figure()
        plt.plot(coeffs)
        plt.show()

if __name__ == "__main__":
    main()
