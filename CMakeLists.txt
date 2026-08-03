cmake_minimum_required(VERSION 3.20)
project(Candelabra LANGUAGES C ASM)

set(VERSION_MAJOR 1 CACHE STRING "Firmware major version")
set(VERSION_MINOR 0 CACHE STRING "Firmware minor version")
set(VERSION_PATCH 0 CACHE STRING "Firmware patch version")

# Encode semver as BCD for USB bcdDevice descriptor: 0xMMmmpp
math(EXPR FIRMWARE_VERSION_BCD
    "(${VERSION_MAJOR} / 10) * 16 + (${VERSION_MAJOR} % 10)")
math(EXPR _MINOR_BCD
    "(${VERSION_MINOR} / 10) * 16 + (${VERSION_MINOR} % 10)")
math(EXPR _PATCH_BCD
    "(${VERSION_PATCH} / 10) * 16 + (${VERSION_PATCH} % 10)")
math(EXPR FIRMWARE_VERSION_BCD
    "(${FIRMWARE_VERSION_BCD} << 16) | (${_MINOR_BCD} << 8) | ${_PATCH_BCD}")

message(STATUS "Firmware version: ${VERSION_MAJOR}.${VERSION_MINOR}.${VERSION_PATCH}")

# ---------------------------------------------------------------------------
# function: add_firmware_target(FIRMWARE BOARD MCU QUARTZ)
# ---------------------------------------------------------------------------
function(add_firmware_target FIRMWARE BOARD MCU QUARTZ)
    # Derive MCU family and CPU core
    if(MCU STREQUAL "STM32G431" OR MCU STREQUAL "STM32G473")
        set(MCU_SERIE STM32G4xx)
        set(CPU cortex-m4)
    elseif(MCU STREQUAL "STM32G0B1")
        set(MCU_SERIE STM32G0xx)
        set(CPU cortex-m0plus)
    else()
        message(FATAL_ERROR "Unsupported MCU: ${MCU}")
    endif()

    set(TARGET_NAME ${MCU}_${FIRMWARE}_${BOARD})
    set(DRIVER_PATH ${CMAKE_SOURCE_DIR}/STM32/${MCU_SERIE}_HAL_Driver)
    set(CONFIG_DIR ${DRIVER_PATH}/Config)

    # -- Collect sources --

    # Common firmware sources
    file(GLOB COMMON_SOURCES ${CMAKE_SOURCE_DIR}/Firmware/*.c)

    # Firmware-variant sources (Candlelight or Slcan)
    file(GLOB VARIANT_SOURCES ${CMAKE_SOURCE_DIR}/Firmware/${FIRMWARE}/*.c)

    # HAL driver sources (exclude templates)
    file(GLOB HAL_SOURCES ${DRIVER_PATH}/Src/*.c)
    list(FILTER HAL_SOURCES EXCLUDE REGEX "_template\\.c$")

    # System and startup
    set(SYSTEM_SOURCE ${CONFIG_DIR}/system_${MCU_SERIE}.c)
    set(STARTUP_SOURCE ${CONFIG_DIR}/startup_${MCU}.s)

    # -- Create executable --
    add_executable(${TARGET_NAME}
        ${COMMON_SOURCES}
        ${VARIANT_SOURCES}
        ${HAL_SOURCES}
        ${SYSTEM_SOURCE}
        ${STARTUP_SOURCE}
    )

    target_include_directories(${TARGET_NAME} PRIVATE
        ${CMAKE_SOURCE_DIR}/STM32/CMSIS
        ${DRIVER_PATH}/Inc
        ${CONFIG_DIR}
        ${CMAKE_SOURCE_DIR}/Firmware
        ${CMAKE_SOURCE_DIR}/Firmware/USB
        ${CMAKE_SOURCE_DIR}/Firmware/${FIRMWARE}
    )

    target_compile_definitions(${TARGET_NAME} PRIVATE
        ${BOARD}
        ${FIRMWARE}
        ${MCU}xx
        ${MCU_SERIE}
        TARGET_BOARD="${BOARD}"
        TARGET_FIRMWARE="${FIRMWARE}"
        TARGET_MCU="${MCU}"
        MCU_SERIE="${MCU_SERIE}"
        HSE_VALUE=${QUARTZ}
        FIRMWARE_VERSION_BCD=${FIRMWARE_VERSION_BCD}
        USER_VECT_TAB_ADDRESS
    )

    target_compile_options(${TARGET_NAME} PRIVATE
        -mcpu=${CPU} -mthumb
        -Wall -g
        -ffunction-sections -fdata-sections
        -O3
    )

    target_link_options(${TARGET_NAME} PRIVATE
        -mcpu=${CPU} -mthumb
        -T${CONFIG_DIR}/${MCU}.ld
        -fno-exceptions
        -ffunction-sections -fdata-sections
        -Wl,--gc-sections
        --specs=nano.specs
        --specs=nosys.specs
        -Wl,-Map=${CMAKE_CURRENT_BINARY_DIR}/${TARGET_NAME}.map
    )

    target_link_libraries(${TARGET_NAME} PRIVATE c m nosys)

    set_target_properties(${TARGET_NAME} PROPERTIES
        SUFFIX .elf
        RUNTIME_OUTPUT_DIRECTORY ${CMAKE_CURRENT_BINARY_DIR}
    )

    # Print size after linking
    add_custom_command(TARGET ${TARGET_NAME} POST_BUILD
        COMMAND ${CMAKE_SIZE} $<TARGET_FILE:${TARGET_NAME}>
    )

    # Generate .bin
    add_custom_command(TARGET ${TARGET_NAME} POST_BUILD
        COMMAND ${CMAKE_OBJCOPY} -O binary
            $<TARGET_FILE:${TARGET_NAME}>
            ${CMAKE_CURRENT_BINARY_DIR}/${TARGET_NAME}.bin
        COMMENT "Generating ${TARGET_NAME}.bin"
    )

    # Generate .hex
    add_custom_command(TARGET ${TARGET_NAME} POST_BUILD
        COMMAND ${CMAKE_OBJCOPY} -O ihex
            $<TARGET_FILE:${TARGET_NAME}>
            ${CMAKE_CURRENT_BINARY_DIR}/${TARGET_NAME}.hex
        COMMENT "Generating ${TARGET_NAME}.hex"
    )
endfunction()

# ---------------------------------------------------------------------------
# Board targets
# ---------------------------------------------------------------------------

# Multiboard (G431, no quartz)
add_firmware_target(Candlelight Multiboard   STM32G431 0)
add_firmware_target(Slcan       Multiboard   STM32G431 0)

# Jhoinrch (G431, 25 MHz)
add_firmware_target(Candlelight Jhoinrch     STM32G431 25000000)
add_firmware_target(Slcan       Jhoinrch     STM32G431 25000000)

# Openlightlabs (G431, no quartz)
add_firmware_target(Candlelight OpenlightLabs STM32G431 0)
add_firmware_target(Slcan       OpenlightLabs STM32G431 0)

# OleksiiSolo (G431, 8 MHz)
add_firmware_target(Candlelight OleksiiSolo  STM32G431 8000000)
add_firmware_target(Slcan       OleksiiSolo  STM32G431 8000000)

# OleksiiDual (G473, 8 MHz)
add_firmware_target(Candlelight OleksiiDual  STM32G473 8000000)
add_firmware_target(Slcan       OleksiiDual  STM32G473 8000000)

# WeActStudioV1 (G0B1, 16 MHz)
add_firmware_target(Candlelight WeActStudioV1 STM32G0B1 16000000)
add_firmware_target(Slcan       WeActStudioV1 STM32G0B1 16000000)

# WeActStudioV2 (G431, 16 MHz)
add_firmware_target(Candlelight WeActStudioV2 STM32G431 16000000)
add_firmware_target(Slcan       WeActStudioV2 STM32G431 16000000)
