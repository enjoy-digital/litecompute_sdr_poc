#!/usr/bin/env python3

import argparse
import numpy as np
import matplotlib.pyplot as plt

# Utils --------------------------------------------------------------------------------------------
def read_binary_file(file_path):
    samples = []
    length = 1000
    i      = 0
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(2)  # Read 16 bits (2 bytes)
            if not chunk:
                break
            i+=1
            value = int.from_bytes(chunk, byteorder='little', signed=True)  # Convert to integer
            samples.append(value)
    return samples

def read_sim_file(file_path):
    samples = []
    with open(file_path, "r") as fd:
    
        lines = fd.readlines()
        # Search for <DUMP ON
        #for _ in range(len(lines)):
        #    line = lines.pop(0)
        #    if line.startswith("<DUMP ON"):
        #        break
        for index, line in enumerate(lines):
            if line.startswith("- /"):
                continue
            val = line.strip().split()

            re_v = int(val[0])
            im_v = int(val[1])

            #re_in.append(re_v)
            #im_in.append(im_v)
            #last_in.append(int(val[2]))
            samples.append(re_v)
            samples.append(im_v)
            #if int(val[2]) == 1:
            #    indices.append(index)
    print(len(samples))
    return samples


# Main ---------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="MAIA SDR Simulation.")
    parser.add_argument("--sim-file",    help="Simulation output result file dump.")
    parser.add_argument("--acorn-file",  help="litepcie_test record result file dump.")

    args = parser.parse_args()

    sim_dump  = read_sim_file(args.sim_file)
    real_dump = read_binary_file(args.acorn_file)

    sim_re_in  = []
    sim_im_in  = []
    real_re_in = []
    real_im_in = []
    for i in range(0, len(sim_dump), 2):
        sim_re_in.append(sim_dump[i + 0])
        sim_im_in.append(sim_dump[i + 1])
    for i in range(0, len(real_dump), 2):
        real_re_in.append(real_dump[i + 0])
        real_im_in.append(real_dump[i + 1])


    r = np.array(sim_re_in)
    i = np.array(sim_im_in)
    sim_mag  = np.abs(r + 1j * i)
    r = np.array(real_re_in)
    i = np.array(real_im_in)
    real_mag = np.abs(r + 1j * i)


    if len(sim_dump) > len(real_dump):
        length = len(real_dump)
    else:
        sim_dump += [0] * (len(real_dump) - len(sim_dump))
        length = len(sim_dump)

    with open("dump.txt", "w") as fd:
        for i in range(length):
            fd.write(f"{sim_dump[i]} {real_dump[i]}\n")

    plt.figure(figsize=(12, 6))
    real_offset = (30 - 12) + 32*1
    real_offset = 1 + 32*0
    real_offset = 32
    #plt.plot(real_mag[real_offset:] + 1000, '-o', markersize=4, color="red")
    #plt.plot(sim_mag,  '-o', markersize=4, color="blue")

    real_t = real_mag[real_offset:]
    sim_t =  sim_mag[0:len(real_t)]
    #real_t = real_mag[:982]
    plt.plot((real_t - sim_t)[56:] + 10000 - 10000, color="green")
    plt.show()

if __name__ == "__main__":
    main()
