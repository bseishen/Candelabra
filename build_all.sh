#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="${SCRIPT_DIR}/build"

mkdir -p "${BUILD_DIR}"
cd "${BUILD_DIR}"

cmake -DCMAKE_TOOLCHAIN_FILE="${SCRIPT_DIR}/cmake/arm-none-eabi.cmake" "${SCRIPT_DIR}"
cmake --build . --parallel "$(nproc)"

echo ""
echo "Build complete. Output files:"
find "${BUILD_DIR}/binaries" -maxdepth 1 \( -name "*.bin" -o -name "*.hex" \) | sort
