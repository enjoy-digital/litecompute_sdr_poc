#!/usr/bin/env python3

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


# Parameters
f       = 25e6 / 1 # Signal frequency
fs      = 100e6    # Sampling frequency

re_in   = []
im_in   = []
last_in = []
N       = 1024

samples = read_binary_file("toto.bin")

for i in range(0, len(samples), 2):
    re_in.append(samples[i + 0])
    im_in.append(samples[i + 1])

# Frequency axis.
freq_raw = np.arange(N) * (fs / N)
freq_raw = freq_raw[0:N // 2]


plt.figure(figsize=(12, 6))
for i in range(2*1024, len(re_in)-1024, 1024):
    real     = np.array(re_in[i: i + 1024])
    imag     = np.array(im_in[i: i + 1024])
    fft_data = real + 1j * imag
    # Magnitude of FFT
    magnitude = np.abs(fft_data)
    magnitude = magnitude[0:N // 2]

    # Plot
    plt.plot(freq_raw / 1e6, magnitude, '-o', markersize=4)#, label='FFT Magnitude')
plt.xlabel('Frequency (MHz)')
plt.ylabel('Magnitude')
plt.grid(True)

plt.axvline(x=f / 1e6, color='g', linestyle='--', label=f'Signal ({f} MHz)')
plt.legend()

plt.show()
