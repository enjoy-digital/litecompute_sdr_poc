# [> SDR GUI
------------

This application is a demonstrator for FIR, FFT Modules.
It requires to have a *LiteX M2SDR* platform programmed with the correct
gateware (see Primary README.md).

As shown in this figure:
![sdr_gui](https://github.com/user-attachments/assets/8c20a75c-4f38-4727-9f2f-e24f657d0ab2)

- Upper left: a panel dedicated to interact with `m2sdr_tone`
- Upper right: a panel to enable/bypass FIR and to configure parameters and
  coefficients
- Lower left: a panel to display raw samples or FFT, with optional waterfall
  from DMA1 channel
- Lower right: a panel to display fft samples (with optional FIR), with optional
  waterfall from DMA2 channel

## [> Prerequisites
-------------------

`libsdl2`
```bash
sudo apt install libsdl2-dev
```

`imgui`
```bash
git clone https://github.com/ocornut/imgui.git
```

`tiny-process-library`
```bash
git clone https://gitlab.com/eidheim/tiny-process-library
```

## [> Build
------------

```bash
make
```

## [> Run
---------
``bash
./build/sdr_gui
```
