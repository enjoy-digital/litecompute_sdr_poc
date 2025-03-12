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

# Utils --------------------------------------------------------------------------------------------
def read_binary_file(file_path):
    samples = []
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(2)  # Read 16 bits (2 bytes)
            if not chunk:
                break
            value = int.from_bytes(chunk, byteorder='little', signed=True)  # Convert to integer
            samples.append(value)
    return samples

# Main ---------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Display FFT.")
    parser.add_argument("--dump-file",                            help="litepcie_test record result file dump.")
    parser.add_argument("--fft-order", default=32,    type=int,   help="FFT Order.")
    parser.add_argument("--fs",        default=100e6, type=float, help="Sample Frequency.")

    args = parser.parse_args()

    # Parameters
    f       = 25e6 / 1 # Signal frequency
    fs      = args.fs  # Sampling frequency

    re_in   = []
    im_in   = []
    last_in = []
    N       = args.fft_order

    samples = read_binary_file(args.dump_file)

    for i in range(0, len(samples), 2):
        re_in.append(samples[i + 0])
        im_in.append(samples[i + 1])

    # Frequency axis.
    freq_raw = np.arange(N) * (fs/2 / N)

    plt.figure(figsize=(12, 6))
    for i in range(1*N, len(re_in)-N, N):
        real     = np.array(re_in[i: i + N])
        imag     = np.array(im_in[i: i + N])
        fft_data = real + 1j * imag

        # Magnitude of FFT
        magnitude = np.abs(fft_data)

        # Plot
        plt.plot(freq_raw / 1e6, magnitude, '-o', markersize=4)
    plt.xlabel('Frequency (MHz)')
    plt.ylabel('Magnitude')
    plt.grid(True)

    plt.axvline(x=f / 1e6, color='g', linestyle='--', label=f'Signal ({f} MHz)')
    plt.legend()

    plt.show()

if __name__ == "__main__":
    main()
