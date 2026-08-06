# Candelabra

Unified Slcan and Candlelight firmware for CANable adapters built on the STM32Gxxx processor family.

*A candelabra unites many candles — Candelabra unites many CANables.*

![Candelabra Logo](documentation/candelabra_logo.png)

## Background

This project is a fork of [Elmue's CANable firmware](https://github.com/Elmue/CANable-Firmware), which unified the Slcan and Candlelight firmwares with dozens of bug fixes and CAN FD support for the STM32Gxxx family.

Candelabra extends that work with:

- A CMake-based build system replacing the original Makefile
- A browser-based firmware flasher ([Candelabra Web](https://bseishen.github.io/candelabra-web))
- Automated release builds via GitHub Actions
- Restructured project layout for easier development

## Web Firmware Flasher

Flash firmware directly from your browser — no drivers or native tools required.

**[Launch Candelabra Web](https://bseishen.github.io/candelabra-web)**

Works with Chrome, Edge, Opera, and other Chromium-based browsers (requires WebUSB support).

## Supported Boards

| Board | MCU | Quartz |
|---|---|---|
| Multiboard (MKS Makerbase, Walfront, DSD Tech, etc.) | STM32G431 | RC oscillator |
| Multiboard (Walfront) | STM32G473 | RC oscillator |
| Jhoinrch | STM32G431 | 25 MHz |
| OpenlightLabs | STM32G431 | RC oscillator |
| OleksiiSolo | STM32G431 | 8 MHz |
| OleksiiDual (dual channel) | STM32G473 | 8 MHz |
| WeActStudio USB2CANFD v1 | STM32G0B1 | 16 MHz |
| WeActStudio USB2CANFD v2 | STM32G431 | 16 MHz |

**Multiboard** refers to the numerous generic CANable clones from various manufacturers (MKS Makerbase, Walfront, DSD Tech, and others) that share the same pinout and PCB layout. If your adapter is an unbranded or budget STM32G431 or STM32G473 CANable clone, Multiboard is likely the correct target.

Tested up to 10 Mbaud on STM32G431 isolated adapters from MKS Makerbase and Jhoinrch. The firmware is designed to be easily expandable for future processors and boards.

## Documentation

- User Manual
- Slcan Developer Manual
- Candlelight Developer Manual
- Firmware Developer Manual

https://netcult.ch/elmue/CANable%20Firmware%20Update

## Development Environment

### Dev Container (recommended)

This project includes a [Dev Container](https://containers.dev/) configuration for VS Code and GitHub Codespaces. The container comes pre-configured with:

- ARM GCC toolchain (`arm-none-eabi-gcc`)
- CMake
- dfu-util
- VS Code extensions: C/C++, CMake Tools, Makefile Tools

To use it: open the repo in VS Code, then **Reopen in Container** when prompted (or via the Command Palette).

### Manual Setup

- [ARM GCC toolchain](https://developer.arm.com/tools-and-software/open-source-software/developer-tools/gnu-toolchain/gnu-rm) (`arm-none-eabi-gcc`)
- [CMake](https://cmake.org/) (3.20 or newer)

## Building from Source

```bash
./build_all.sh
```

This configures and builds all 16 firmware variants (Slcan + Candlelight for each supported board). Output `.bin` and `.hex` files are placed in the `build/binaries/` directory.

### Build with a specific version

```bash
mkdir -p build && cd build
cmake -DCMAKE_TOOLCHAIN_FILE=../cmake/arm-none-eabi.cmake \
      -DVERSION_MAJOR=1 -DVERSION_MINOR=0 -DVERSION_PATCH=0 ..
cmake --build . --parallel $(nproc)
```

### Versioning

Firmware uses semantic versioning (major.minor.patch). The version is embedded in the USB device descriptor (`bcdDevice`). To release, tag and push:

```bash
git tag v1.0.0
git push origin v1.0.0
```

The GitHub Actions workflow will build all targets and create a release with the firmware binaries attached.
