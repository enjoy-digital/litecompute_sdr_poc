## [> Introduction - Creating FPGA based accelerators with LiteX.
-----------------------------------------------------------------

LiteX is already used to create various designs integrating Ethernet, PCIe or DRAM cores on FPGA.
These cores + the LiteX infrastructure provides all the materials to allow users to create FPGA
based accelerators for experienced FPGA developers. The aim of this task is to provide a simplified
infrastructure to allow developers with less experience to also create their own accelerator using
the HDL language of their choice and to also provide example projects on various FPGA boards + documentation.

![Image](https://github.com/user-attachments/assets/a5956085-1a22-4cf9-a580-338e8bb5f3de)

Example of FPGA based PCIe accelerator infrastructure with LiteX and its cores.

### [> Demonstrations

This repository provides two demonstrations:
1. The first is based on *SQRL Acorn CLE-215+* (`targets/acorn.py`): it demonstrates the use of the `MaiSDRFFT` integration between
   `reader` and `writer` DMA channel 0. It act as loopback.
2. The second is based on *LiteX M2SDR* target (`targets/litex_m2sdr.py`: in this demonstration, the `MaiaSDRFFT` is connected between RFIC and
   a second DMA Channel. The FFT may be fed with RFIC output (RX side) or set in loopback mode.

**Acorn demonstration**
```bash
python3 -m targets.acorn --build [--load] [--flash] [--with-fft-window] [--fft-radix 2/4] [--fft-order-log2 x] [--with-litedram-fifo]
```
With:
* `--load` loads the bitstream to SRAM.
* `--flash` writes the bitstream into the SPI Flash.
* `--with-fft-window` enables windowing.
* `--fft-radix` selects between radix 2 and radix 4 (default: 2)
* `--fft-order-log2` sets the log2 of the FFT size (default: 5)
* `--with-litedram-fifo` enable integration of the DRAM between DMA reader and DMA writer

**LiteX M2SDR**
```bash
python3 -m targets.litex_m2sdr --build [--load] [--flash] [--with-pcie] [--variant] [--without-fft] [--with-fft-window] [--fft-radix 2/4] [--fft-order-log2 x]
```
With:
* `--load` loads the bitstream to SRAM.
* `--flash` writes the bitstream into the SPI Flash.
* `--variant` selects between `m2` configuration and `baseboard`.
* `--with-pcie` enables PCIe support.
* `--without-fft` disables the FFT module (connected to a third DMA channel).
* `--without-fft-window` disables windowing.
* `--fft-radix` selects between radix 2 and radix 4 (default: 2).
* `--fft-order-log2` sets the log2 of the FFT size (default: 10).
* `--without-fir` disables FIR.
* `--macc-trunk` Truncation length for output of each MACC.

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

### [> LiteX M2SDR]

```bash
git clone https://github.com/enjoy-digital/litex_m2sdr
cd litex_m2sdr
pip3 install --user
```

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

# pm-remez (to produces FIR coefficients)
pip3 install --user pm-remez
```

### [> Cloning the Repository / Install

Execute the following:
- `git clone https://github.com/enjoy-digital/litecompute_poc`
- `cd litecompute_poc`
- `pip3 install --user -e .`

## [> Cores

For *Maia SDR* Modules, configurations/parameters are used at build time to produce the Verilog file. It's not possible
to changes it at run time.

### [> MaiaHDLFFT

This Module is a wrapper for the [FFT](https://github.com/maia-sdr/maia-sdr/blob/main/maia-hdl/maia_hdl/fft.py)

Example usage:

```python
# MAIA SDR FFT -----------------------------------------------------------------------------
self.fft = MaiaSDRFFT(platform,
    data_width  = 16,
    order_log2  = fft_order_log2,
    radix       = radix,
    window      = {True: "blackmanharris", False: None}[with_window],
    cmult3x     = False,
    clk_domain  = "sys",
)
```

Where:
- `data_width` is the size of Real/Imag input signals
- `order_log2` is the *log2* of the FFT size
- `radix` is the implementation (maybe be *2*, *4* or *R22*)
- `window` is an optional windowing applied (allowed parameters: None (no window) or *blackmanharris*
- `cmult3x` is an optimization, requiring a clock 3 times faster to perform complex multiplication with only one DSP
- `clk_domain` main core clock domain

The module provides 2 streams interface:
- `sink` to receive samples. data are filled with `re` and `im`  with a size == `data_width`. `ready` is always set to `1`
- `source` to propagates results with two subsignals `re` and `im` (size == `instance.out_width * 2`), `last` is set with the last sample of an FFT.

**Note:**
when windowing support is enabled or `cmult3x` option is set to true, to extra
clocks are required:

- One clock 2 times faster than `clk_domain` (only required when `window` is set to *blackmanharris*
- One clock 3 times faster clock domain only required when `cmult3x` is set to `True`

two clocks domains must be added and must be named:
- `clk_domain`2x
- `clk_domain`3x

With `clk_domain` the value provided to `clk_domain` parameter

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

## Using Core with acorn baseboard

A ready to uses targets is available in the *targets* directory:
```bash
./targets/acorn.py --help
usage: acorn.py [-h] [--build] [--load] [--flash] [--variant VARIANT] [--programmer {openocd,openfpgaloader}] [--with-window] [--radix RADIX] [--fft-order-log2 FFT_ORDER_LOG2] [--with-fft-datapath-probe]

LiteX SoC on Acorn CLE-101/215(+).

options:
  -h, --help            show this help message and exit
  --build               Build bitstream
  --load                Load bitstream
  --flash               Flash bitstream.
  --variant VARIANT     Board variant (cle-215+, cle-215 or cle-101).
  --programmer {openocd,openfpgaloader}
                        Programmer select from OpenOCD/openFPGALoader.
  --with-window         Enable FFT Windowing.
  --radix RADIX         Radix 2/4.
  --fft-order-log2 FFT_ORDER_LOG2
                        Log2 of the FFT order.
  --with-fft-datapath-probe
                        Enable FFT Datapath Probe.
```

This target performs `PCIe` -> `FFT` -> `PCIe` processing.

### Preparing FIR Coeffcients

The *tools* directory contains the script *gen_fir_taps.py*, which generates
coefficients table ready to be loaded:
```bash

usage: gen_fir_taps.py [-h] [--file FILE] [--taps-file TAPS_FILE] [--model MODEL] [--fs FS] [--fc FC] [--length LENGTH] [--coeff-size COEFF_SIZE] [--bypass-gen] [--operations OPERATIONS] [--odd_operations]
                       [--decimation DECIMATION] [--num-coeffs NUM_COEFFS]

```

with:
- `--file`: output coefficients file (to uses with the MaiaSDRFir).
- `--taps-file`: Output Taps file (contains only coefficients).
- `--model`: Algorithm to uses between `firls` and `pm-remez` (Default: `pm-remez`)
- `--fs`: Sampling Frequency (Hz).
- `--fc`: Cutoff Frequency (Hz).
- `--length`: Filter length (see note below).
- `--coeff-size`: Coefficients Size (bits).
- `--operations`: number of operations to perform
- `--odd_operations`: Is Odd/Even operations.
- `--decimation`: Decimation factor (must be > 1).
- `--num-coeffs`: Coefficients RAM capacity (up to 256)

`--length` must equal to $operations * 2 * decimation$ for even operations, or
$((operations * 2) - 1) * decimation$ for odd operations

### Preparing Complex Samples

The *software/user* directory contains the script *gen_lut.py*, which generates lookup table data:
```bash
./software/user/gen_lut.py --help
usage: gen_lut.py [-h] [--signal-freq SIGNAL_FREQ] [--sample-rate SAMPLE_RATE] [--repetitions REPETITIONS] [--data-width DATA_WIDTH]
```

with:
- `--signal-freq` Frequency of the sine wave
- `--sample-rate` Sample frequency, used with `signal-freq` to compute steps for real and imaginary parts
- `--repetitions` number of periods
- `--data-width` sample size

The generated signal is stored in a file called  `data.bin`.

### Sending and Receiving Data

In the *software/user* directory:

- Start recording (Terminal 1):
  `./litepcie_test record output.bin 4000`
- Play the generated signal (Terminal 2):
  `./litepcie_test play data.bin 100`


**Important:** The FFT process is not synchronized with the data stream, so
`record` must be started before `play`.

### Displaying Results

In *software/user*
```bash
./display_fft.py --dump-file FILE [--fs]  [--fft-order]
```
With:
- `--dump-file` the file produces by `litepcie_test record`
- `--fs` the sample frequency (default: 100e6)
- `--fft-order` FFT order (default: 32)
