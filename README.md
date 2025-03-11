## [> Introduction - Creating FPGA based accelerators with LiteX.
-----------------------------------------------------------------

LiteX is already used to create various designs integrating Ethernet, PCIe or DRAM cores on FPGA.
These cores + the LiteX infrastructure provides all the materials to allow users to create FPGA
based accelerators for experienced FPGA developers. The aim of this task is to provide a simplified
infrastructure to allow developers with less experience to also create their own accelerator using
the HDL language of their choice and to also provide example projects on various FPGA boards + documentation.

![Image](https://github.com/user-attachments/assets/a5956085-1a22-4cf9-a580-338e8bb5f3de)

Example of FPGA based PCIe accelerator infrastructure with LiteX and its cores.

## [> Prepare Environment
-------------------------

**Note**: with recent *Python* and `pip` it not more possible to install package via `pip`. A solution
to force install is to create the file `$HOME/.config/pip.conf` with:
```sh
[global]
break-system-packages = true
```

### [> LiteX

Execute the following commands in a directory of your choice:
- `wget https://raw.githubusercontent.com/enjoy-digital/litex/master/litex_setup.py`
- `chmod +x litex_setup.py`
- `./litex_setup.py --init`
- `sudo ./litex_setup.py --install`
- `sudo ./litex_setup.py --gcc`

**LiteX** requires knowledge of the *Vivado* installation path, which is provided through an environment variable:
```bash
export LITEX_ENV_VIVADO=/opt/Xilinx/Vivado/2021.2
```
This path assumes Vivado 2021.2 is installed in the */opt* directory. Adjust it as needed.

### [> Maia SDR

```bash
# Amaranth Yosys
pip3 install -U amaranth-yosys

# Amaranth
git clone https://github.com/amaranth-lang/amaranth
cd amaranth
pip3 install --user
cd ..

# Maia-SDR
git clone https://github.com/maia-sdr/maia-sdr
cd maia-sdr/maia-hdl
pip3 install --user
cd ../..
```

### [> Cloning the Repository / Install

Execute the following:
- `git clone https://github.com/enjoy-digital/litecompute_poc`
- `cd litecompute_poc`
- `pip3 install --user -e .`

## [> Cores

For *Maia SDR* Modules, configurations/parameters are used at build time to produce the Verilog file. It's not possible
to changes it at run time.

### [> MAIAHDLFFTWrapper

This Module is a wrapper for the [FFT](https://github.com/maia-sdr/maia-sdr/blob/main/maia-hdl/maia_hdl/fft.py)

Example usage:

```python
# MAIA HDL FFT Wrapper ---------------------------------------------------------------------
self.fft = MAIAHDLFFTWrapper(platform,
    data_width  = 16,
    order_log2  = fft_order_log2,
    radix       = radix,
    window      = {True: "blackmanharris", False: None}[with_window],
    cmult3x     = False,
    cd_domain   = "sys",
    cd_domain2x = "sys2x",
    cd_domain3x = "fft_3x",
)
```

Where:
- `data_width` is the size of Real/Imag input signals
- `order_log2` is the *log2* of the FFT size
- `radix` is the implementation (maybe be *2*, *4* or *R22*)
- `window` is an optional windowing applied (allowed parameters: None (no window) or *blackmanharris*
- `cmult3x` is an optimization, requiring a clock 3 times faster to perform complex multiplication with only one DSP
- `cd_domain` main core clock domain
- `cd_domain2x` another clock domain 2 times faster than `cd_domain` (only required when `window` is set to *blackmanharris*
- `cd_domain3x` 3 times faster clock domain only required when `cmult3x` is set to `True`

The module provides 2 streams interface:
- `sink` to receive samples with `data == data_width * 2`, LSB are real part, MSB are imaginary part. `ready` is always set to `1`
- `source` to propagates results with a `data` size == `instance.out_width * 2`, `last` is set with the last sample of an
  FFT.

**Connection example:**

```python
self.tx_conv = stream.Converter(64, 32)
self.rx_conv = stream.Converter(32 64)

self.pipeline = stream.Pipeline(
    self.pcie_dma0.source,
    self.tx_conv,
    self.fft,
    self.rx_conv,
    self.pcie_dma0.sink,
)
```

## (> Simulation
----------------

All simulations are stored in *sim* directory

### [> FFT Simulation

```bash
./maia_sdr_fft_sim.py --help
usage: maia_sdr_fft_sim.py [-h] [--trace] [--with-window] [--radix RADIX] [--fft-order-log2 FFT_ORDER_LOG2] [--signal-freq SIGNAL_FREQ]

MAIA SDR Simulation.

options:
  -h, --help            show this help message and exit
  --trace               Enable VCD tracing.
  --with-window         Enable FFT Windowing.
  --radix RADIX         Radix 2/4.
  --fft-order-log2 FFT_ORDER_LOG2
                        Log2 of the FFT order.
  --signal-freq SIGNAL_FREQ
                        Input signal frequency.
```