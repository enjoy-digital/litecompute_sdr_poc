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
    parser.add_argument("--file",       default=None,            help="output data file.")

    # configuration.
    parser.add_argument("--length",     default=100,   type=int,   help="length.")
    parser.add_argument("--data-size",  default=16,    type=int,   help="Coefficients Size.")

    args = parser.parse_args()

    assert args.file is not None

    with open(args.file, "wb") as fd:
        value = 0x01
        for _ in range(args.length):
            # Pack each integer into 2 bytes in little-endian format
            binary_data = struct.pack('<h', value)
            fd.write(binary_data)

if __name__ == "__main__":
    main()
