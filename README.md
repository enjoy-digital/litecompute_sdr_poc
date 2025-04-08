## [> Introduction - Creating FPGA based accelerators with LiteX.
-----------------------------------------------------------------

LiteX is already used to create various designs integrating Ethernet, PCIe or DRAM cores on FPGA.
These cores + the LiteX infrastructure provides all the materials to allow users to create FPGA
based accelerators for experienced FPGA developers. The aim of this task is to provide a simplified
infrastructure to allow developers with less experience to also create their own accelerator using
the HDL language of their choice and to also provide example projects on various FPGA boards + documentation.

![Image](https://github.com/user-attachments/assets/a5956085-1a22-4cf9-a580-338e8bb5f3de)

Example of FPGA based PCIe-based FPGA accelerator using LiteX and its cores.

## [> Demonstrations

This primary goal of this repository is to demonstrates how *Digital Signal Processing (DSP)* modules
can be directly integrated into data streams -- either between a DMA writer/reader or between an
external RFIC device and a DMA Channel.

It also highligths:
- `Amaranth` integration: both *FIR Filter* and *FFT* modules are written in the `Amaranth` HDL.
- **Custom processing: Shows how to insert processing blocks into RX/TX datapaths.

Both demonstrations (`acorn` and `litex_m2sdr`) uses the same `sdr_processing` to integrates
SDR processing in the RX datapath.

### Acorn Demonstration

- **Target**: *SQRL Acorn CLE-215+*
- **Script**: `targets/acorn.py`

This demonstration implements a DMA loopback pipeline with the following data path:
`DMA Reader [-> LiteDRAM FIFO] -> FIR -> FFT -> DMA Writer`

**Note**: `LiteDRAM` is optional and must be enabled at build time.
Modules can be bypassed dynamically at runtime using `litepcie_util` with this command:
```bash
litepcie_util [-f 0/1] [-i 0/1] [-l 0/1] stream_configuration
```
With:
- `-f` to enable/disable the FFT (default: 1).
- `-i` to enable/disable the FIR filter (default: 1).
- `-l` to enable/disable the LiteDRAMFIFO Module (default: 1).

**Build command**

```bash
python3 -m targets.acorn --build [--load] [--flash] [--with-fft-window] [--fft-radix 2/4] [--fft-order-log2 x] [--with-litedram-fifo]
```
With:
* `--load` loads the bitstream to SRAM.
* `--flash` writes the bitstream into the SPI Flash.
* `--with-fft-window` enables windowing.
* `--fft-radix` selects between radix 2 and radix 4 (default: 2)
* `--fft-order-log2` sets the log2 of the FFT size (default: 5)
* `--with-litedram-fifo` enable integration of the DRAM between DMA reader and
  DMA writer

### LiteX M2SDR Demonstration

- **Target**: *LiteX M2SDR*
- **Script**: `targets/litex_m2sdr.py`

This second demonstration uses `sdr_processing` module to integrates `MaiaSDRFIR` and `MaiaSDRFFT` in a new stream
between the RFIC and a third DMA Channel.

**Note**: The second DMA Channel is used to have raw samples as comparison.

This demonstration is accompanied to a GUI (*software_m2sdr/sdr_gui*) with:
- a panel dedicated to displays raw sample or FFT with waterfall
- a panel dedicated to displays `MaiaSDRFFT` output with waterfall
- a panel to configure *FIR filter* (including coefficients) and to enable/bypass with module

**Build command**

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

## [> Environment Setup
-----------------------

### Python Pip Workaround

Modern Python versions restrict certain system installations. To override:
```bash
mkdir -p $HOME/.config
echo -e "[global]\nbreak-system-packages = true" > $HOME/.config/pip.conf
```

### [> LiteX

Execute the following commands in a directory of your choice:
```bash
wget https://raw.githubusercontent.com/enjoy-digital/litex/master/litex_setup.py
chmod +x litex_setup.py
./litex_setup.py --init
sudo ./litex_setup.py --install
sudo ./litex_setup.py --gcc
```

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

### [> Clone and Install This Repository

```bash
git clone https://github.com/enjoy-digital/litecompute_poc
cd litecompute_poc
pip3 install --user -e .
```

## [> Cores

### [> MaiaSDRFFT

This Module is a wrapper for the [FFT](https://github.com/maia-sdr/maia-sdr/blob/main/maia-hdl/maia_hdl/fft.py)

For this *Maia SDR* Modules, configurations/parameters are set at build time to
produce the Verilog file. It's not possible to changes it at run time.

**Example usage:**

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
- `source` to propagates results with two subsignals `re` and `im` (size == `instance.out_width`), `last` is set with the last sample of an FFT.

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
# 64bit -> 32bit before FFT.
self.pre_conv  = stream.Converter(64, 32)
# 64bit -> 32bit after FFT.
self.post_conv = stream.Converter(32, 64)

self.comb += [
  # PCIe DMA0 source -> Converter
  self.pcie_dma0.source.connect(self.pre_conv.sink),

  # Converter -> FFT
  self.pre_conv.source.connect(self.fft.sink, omit["data"]),
  # Split Converter source data to RE/IM.
  self.fft.sink.re.eq(self.pre_conv.source.data[ 0:16]),
  self.fft.sink.im.eq(self.pre_conv.source.data[16:32]),

  # FFT -> Converter.
  self.fft.source.connect(self.post_conv.sink, omit=["re", "im"]),
  # Merge RE/IM in Converter sink data.
  self.post_conv.sink.data.eq(Cat(self.fft.source.re, self.fft.source.im)),

  # Convert DMA0 sink.
  self.post_conv.source.connect(self.pcie_dma0.sink),
]
```

### [> MaiaSDRFIR

This Module is a wrapper for the [FIR](https://github.com/maia-sdr/maia-sdr/blob/main/maia-hdl/maia_hdl/fir.py)

Example usage:

```python
self.fir = fir   = MaiaSDRFIR(platform,
  data_in_width  = 16,
  data_out_width = 16,
  coeff_width    = 18,
  decim_width    = 7,
  oper_width     = 7,
  macc_trunc     = macc_trunc,
  len_log2       = 8,
  with_csr       = True,
)
```

Where:
- `data_in_width` Size of Real/Imag input signals
- `data_out_width` Size of Real/Imag output signals
- `coeff_width` Size of Coefficients
- `decim_width` Size of the decimation register
- `oper_width` Size of the operations register
- `macc_trunc` Truncation length for output of each MACC.
- `len_log2` Coefficients RAM maximum capacity
- `with_csr` to add CSR for each dynamic parameters configuration

The module provides 2 streams interface:
- `sink` to receive samples. data are filled with `re` and `im`  with a size == `data_in_width`.
- `source` to propagates results with two subsignals `re` and `im` (size == `data_out_width`).

**Notes:**

- The `operations` signal or CSR, defines both the number of multiplications
  to perform and the length of the coefficient table ($2 * operations$). It also
  determines the input sample rate: for each new complex sample, `operations`
  clock cycles are required before the next sample can be processed.
- The `macc_trunc` signal or CSR must be configured with care.
  By definition, a FIR filter (or a MACC unit) requires an output width of
  approximately
  $data\_in\_width \times coeff\_width \times \log_2(operations \times 2)$.
  If the output width or internal accumulator is too small, the results may
  become corrupted.
  However, this theoretical value is often an overestimate and depends on
  factors such as the coefficient lookup table (LUT) and the input sample range.

**Connection example:**

```python
# 64bit -> 32bit before FIR.
self.pre_conv  = stream.Converter(64, 32)
# 64bit -> 32bit after FIR.
self.post_conv = stream.Converter(32, 64)

self.comb += [
  # PCIe DMA0 source -> Converter
  self.pcie_dma0.source.connect(self.pre_conv.sink),

  # Converter -> FIR
  self.pre_conv.source.connect(self.fir.sink, omit["data"]),
  # Split Converter source data to RE/IM.
  self.fir.sink.re.eq(self.pre_conv.source.data[ 0:16]),
  self.fir.sink.im.eq(self.pre_conv.source.data[16:32]),

  # FIR -> Converter.
  self.fir.source.connect(self.post_conv.sink, omit=["re", "im"]),
  # Merge RE/IM in Converter sink data.
  self.post_conv.sink.data.eq(Cat(self.fir.source.re, self.fir.source.im)),

  # Convert DMA0 sink.
  self.post_conv.source.connect(self.pcie_dma0.sink),
]
```

### [> SDRProcessing

Located in *gateware/sdr_processing.py* combines:
- a `LiteSDRAMFIFO` Module
- a `MaiaSDRFIR` Module
- a `MaiaSDRFFT` Module


**Instanciation example**

It may instiated with a code similar too:
```python
self.sdr_processing = sdr_processing = SDRProcessing(platform, self,
  # External FIFO.
  with_litedram      = with_litedram_fifo,

  # FIR.
  with_fir           = True,
  fir_data_in_width  = 16,
  fir_data_out_width = 16,
  fir_coeff_width    = 18,
  fir_decim_width    = 7,
  fir_oper_width     = 7,
  fir_macc_trunc     = 0,
  fir_len_log2       = 8,
  fir_clk_domain     = "sys",
  fir_with_csr       = True,
  # FFT.
  with_fft           = True,
  fft_data_width     = 16,
  fft_order_log2     = fft_order_log2,
  fft_radix          = fft_radix,
  fft_window         = with_fft_window,
  fft_cmult3x        = False,
  fft_clk_domain     = "sys",
)
```

All attributes are similar to `MaiSDRFIR` and `MaiaSDRFFT` and are simply propagated to the dedicated Module

**CSR for bypass**

A `CSRStorage` module is present. It allows to enable/bypass each block independtly.

**Interfaces**

Two primary endpoints are present
- `sink` with a data size of `2 * fir_data_in_width`. It receives stream from previous module
- `source` with a data size of `2 * fft_data_widht`. It propagates results.

Two additionals endpoints are also present when `with_litedram` is set to `True`:
- `ext_fifo_source` with a data size of `2 * fir_data_in_width`. To be connected to the `LiteDRAMFIFO.sink`.
- `ext_fifo_sink` with a data size of `2 * fir_data_in_width` To be connected to the `LiteDRAMFIFO.source`.

A signal `reset` must be connected to reset/clear internal FIFO and to set FFT in its default state.

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
