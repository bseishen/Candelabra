# Candelabra

Unified Slcan and Candlelight firmware for CANable adapters built on the STM32Gxxx processor family.

![CANable Adapter](https://github.com/user-attachments/assets/061f60ba-14a2-4896-866f-6226fc9123f6)

## Overview

Candelabra combines the Slcan and Candlelight CANable firmwares into a single codebase with dozens of bug fixes and new features. This is the first Candlelight firmware for the STM32Gxxx family that supports CAN FD without known bugs, while remaining 100% backward compatible with legacy Slcan and Candlelight firmware.

### Supported Boards

| Board | MCU | Quartz |
|---|---|---|
| MKS Makerbase / Walfront / DSD Tech (Multiboard) | STM32G431 | RC oscillator |
| Jhoinrch | STM32G431 | 25 MHz |
| OpenlightLabs | STM32G431 | RC oscillator |
| OleksiiSolo | STM32G431 | 8 MHz |
| OleksiiDual (dual channel) | STM32G473 | 8 MHz |
| WeActStudio USB2CANFD v1 | STM32G0B1 | 16 MHz |
| WeActStudio USB2CANFD v2 | STM32G431 | 16 MHz |

Tested up to 10 Mbaud on STM32G431 isolated adapters from MKS Makerbase and Jhoinrch. The firmware is designed to be easily expandable for future processors and boards.

## Firmware Updater

Precompiled binary firmware files can be uploaded to the CANable with the Firmware Updater.

<img width="577" height="484" alt="CANable STM32 Firmware Updater" src="https://github.com/user-attachments/assets/1364398f-fcd4-430e-aa8b-06cde32ce895" />

## Documentation

- User Manual
- Slcan Developer Manual
- Candlelight Developer Manual
- Firmware Developer Manual

https://netcult.ch/elmue/CANable%20Firmware%20Update

## Building from Source

### Prerequisites

- [ARM GCC toolchain](https://developer.arm.com/tools-and-software/open-source-software/developer-tools/gnu-toolchain/gnu-rm) (`arm-none-eabi-gcc`)
- [CMake](https://cmake.org/) (3.20 or newer)

### Build all targets

```bash
./build_all.sh
```

This configures and builds all 14 firmware variants (Slcan + Candlelight for each supported board). Output `.bin` and `.hex` files are placed in the `build/` directory.

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
