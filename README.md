# CANable-2.5-firmware-Slcan-and-Candlelight
Two new high quality, speed optimized firmwares for CANable adapters with lots of new features.

![CANable Adapter](https://github.com/user-attachments/assets/061f60ba-14a2-4896-866f-6226fc9123f6)


This is the first project that combines the two CANable firmware's Slcan and Candlelight into one code base.
Dozens of bugs have been fixed.
Dozens of new features have been added.
This is the first Candlelight firmware for the STM32Gxxx processor family that supports CAN FD and works without bugs.
However the new firmware is still 100% backward compatible with the legacy Slcan / Candlelight firmware.
The firmware has been tested on the STM32G431 on the isolated adapters from MKS Makerbase and Jhoinrch up to 10 Mbaud.
It works also on the STM32G473 dual CAN channel board from Oleksii.
The WeActStudio v1 firmware is compiled for the STM32G0B1 processor.
The firmware has been designed to be easily expandable for future processors and boards.
Precompiled binary firmware files can be uploaded to the CANable with the new Firmware Updater.

<img width="577" height="484" alt="CANable STM32 Firmware Updater" src="https://github.com/user-attachments/assets/1364398f-fcd4-430e-aa8b-06cde32ce895" />


Please read the detailed 
- User Manual
- Slcan Developer Manual
- Candlelight Developer Manual
- Firmware Developer Manual

https://netcult.ch/elmue/CANable%20Firmware%20Update

________________________

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

________________________

Latest Updates:
You find the version history here:

https://netcult.ch/elmue/CANable%20Firmware%20Update#Source_Code
