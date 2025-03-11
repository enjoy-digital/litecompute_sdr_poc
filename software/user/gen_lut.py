#!/usr/bin/env python3

#
# This file is part of LiteCompute PoC project.
#
# Copyright (c) 2025 Enjoy-Digital <enjoy-digital.fr>.
#
# SPDX-License-Identifier: BSD-2-Clause

import argparse
import numpy as np

def two_complement_encode(value, bits):
    if (value & (1 << (bits - 1))) != 0:
        value = value - (1 << bits)
    return value % (2**bits)

def generate_sample_data(output, frequency, sample_rate, repetitions, data_width):
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
        re = int(real[i])
        im = int(imag[i])
        stream_data.append(re)
        stream_data.append(im)
    print(type(stream_data))

    arr = np.array(stream_data, dtype=np.int16)
    print(stream_data[0:10])
    print(arr[0:10])
    for i in range(10):
        t = two_complement_encode(stream_data[i], data_width)
        print(f"{stream_data[i]:05x} {arr[i]:04x} {t:04x}")

    with open(output, "wb") as fd:
        arr.tofile(fd)
    #    fd.write(struct.pack

    return stream_data

def main():
    parser = argparse.ArgumentParser(description="MAIA SDR Simulation.")
    # FFT Configuration.
    parser.add_argument("--signal-freq", default=10e6,  type=float, help="Input signal frequency (Hz).")
    parser.add_argument("--sample-rate", default=100e6, type=float, help="Sample rate (Hz).")
    parser.add_argument("--repetitions", default=1000,  type=int,   help="Input signal Repetitions.")
    parser.add_argument("--data-width",  default=16,    type=int,   help="Input signal size.")

    args = parser.parse_args()

    generate_sample_data(output="data.bin",
        frequency   = args.signal_freq,
        sample_rate = args.sample_rate,
        repetitions = args.repetitions,
        data_width  = args.data_width,
    )
                

if __name__ == "__main__":
    main()
