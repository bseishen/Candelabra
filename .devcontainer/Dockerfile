FROM mcr.microsoft.com/devcontainers/base:ubuntu-24.04

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc-arm-none-eabi \
    libnewlib-arm-none-eabi \
    libstdc++-arm-none-eabi-newlib \
    cmake \
    dfu-util \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /home/vscode/.claude && chown vscode:vscode /home/vscode/.claude

# Claude Code (native installer, no Node.js needed)
USER vscode
RUN curl -fsSL https://claude.ai/install.sh | bash
ENV PATH=/home/vscode/.local/bin:$PATH
USER root
