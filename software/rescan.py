#!/usr/bin/env python3

# This file is part of LiteX-M2SDR.
#
# Copyright (c) 2024-2025 Enjoy-Digital <enjoy-digital.fr>
# SPDX-License-Identifier: BSD-2-Clause

import argparse
import subprocess

# Generic PCIe Utilities ---------------------------------------------------------------------------

def get_pcie_device_id(vendor, device):
    try:
        lspci_output = subprocess.check_output(["lspci", "-d", f"{vendor}:{device}"]).decode()
        device_id = lspci_output.split()[0]
        return device_id
    except:
        return None

def remove_pcie_device(device_id, driver="litepcie"):
    if not device_id:
        return
    subprocess.run(f"echo 1 | sudo tee /sys/bus/pci/devices/0000:{device_id}/remove > /dev/null", shell=True)

def rescan_pcie_bus():
    subprocess.run("echo 1 | sudo tee /sys/bus/pci/rescan > /dev/null", shell=True)


# Rescan Utilities ---------------------------------------------------------------------------------

def remove_driver():
    print("Removing Driver...")
    subprocess.run("sudo rmmod litepcie", shell=True)
    subprocess.run("sudo rmmod liteuart", shell=True)

def remove_board_from_pcie_bus(device_ids):
    print("Removing Board from PCIe Bus...")
    for device_id in device_ids:
        if device_id:
            remove_pcie_device(device_id)

def rescan_bus():
    print("Rescanning PCIe Bus...")
    rescan_pcie_bus()

def load_driver():
    print("Loading Driver...")
    subprocess.run("sudo insmod kernel/litepcie.ko", shell=True)
    subprocess.run("sudo insmod kernel/liteuart.ko", shell=True)

def get_device_ids():
    return [
        get_pcie_device_id("0x10ee", "0x7021"),
        get_pcie_device_id("0x10ee", "0x7022"),
        get_pcie_device_id("0x10ee", "0x7024"),
    ]

# Main ---------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="FPGA PCIe rescan.")
    args = parser.parse_args()

    # PCIe Rescan and driver Remove/Reload.
    remove_driver()
    device_ids = get_device_ids()
    remove_board_from_pcie_bus(device_ids)
    rescan_bus()
    load_driver()

if __name__ == '__main__':
    main()
