---
name: sync-upstream
description: Sync firmware fixes from Elmue's upstream CANable 2.5 repo (elmue/CANable-2.5-firmware-Slcan-and-Candlelight) into Candelabra — pulls only Firmware/ source changes into firmware/, flags new boards that need CMake/README/webdfu updates, builds all targets, and commits on a branch. Use this whenever the user wants to check for, pull in, merge, or review upstream/Elmue changes, handle an upstream sync PR, or asks "is there anything new upstream", even if they don't say "sync".
---

# Sync upstream firmware

Candelabra is a restructured fork of Elmue's CANable 2.5 firmware. Upstream keeps its
source in `Firmware/` with makefiles, prebuilt binaries, sample apps and a manual;
Candelabra keeps the same source in lowercase `firmware/` with a CMake build and the
`webdfu` flasher. So upstream is never merged directly — only the firmware source is
carried over, and everything else upstream changes is treated as a hint for follow-up
work (e.g. a new `Make_*` file means a new board target here).

The last synced upstream commit is stored in `last-sync` next to this file. It is the
only record of the sync point: git history has no merge, so `git merge-base` is useless.

`sync.sh` (same directory) does the mechanical work; run it from Git Bash / bash:

| Command | What it does |
|---|---|
| `sync.sh status [ref]` | Adds/fetches the `upstream` remote, shows commits since last sync, firmware files that will change (and which are locally customized), new/removed boards and any missing from `CMakeLists.txt`, upstream firmware version, and a stat of all other upstream changes. |
| `sync.sh apply [ref]` | Stages the firmware changes into `firmware/` and updates `last-sync`. Does not commit. Exit 2 = conflicts. |
| `sync.sh build` | Builds all targets with the local toolchain, or in the `.devcontainer` image via Docker. Prints warning/error count and the `.bin` list. |

`ref` defaults to `upstream/main`.

## Workflow

1. **Status.** Run `sync.sh status`. If it says UP TO DATE, tell the user and stop.
   Otherwise summarize for the user: the upstream commits, the firmware files changing
   (skim `git diff <last-sync> upstream/main -- Firmware` so you can say what the fixes
   actually do), and the follow-ups listed in step 4.

2. **Branch.** Start from an up-to-date `main` with a clean `firmware/`:
   `git switch -c upstream-sync-<short-upstream-sha> main`.

3. **Apply.** Run `sync.sh apply`.
   - Files untouched locally are staged as upstream's *exact* blobs. This matters: the
     sources are CRLF in the repo and the user has `core.autocrlf=input`, so copying or
     patching files through the working tree would rewrite every line to LF on commit.
     Don't "fix" this by hand-copying files.
   - Files Candelabra customized (currently `firmware/usb_ctrlreq.c`, which holds the
     Candelabra USB strings) are 3-way merged. On exit 2, resolve the conflict markers
     keeping Candelabra's branding/behaviour plus upstream's fix, then `git add`.
     A merged file may show a few CR-only line-ending differences against upstream —
     harmless, upstream's line endings are inconsistent.

4. **Follow-ups** from the status report — do these on the same branch, as separate commits:
   - **New board** (`MISSING in CMakeLists.txt`): add a pair of targets in
     `CMakeLists.txt` under "Board targets", matching the existing style:
     ```cmake
     # BigTreeTechU2C (G0B1, 8 MHz)
     add_firmware_target(Candlelight BigTreeTechU2C STM32G0B1 8000000)
     add_firmware_target(Slcan       BigTreeTechU2C STM32G0B1 8000000)
     ```
     Then add a row to the "Supported Boards" table in `README.md` (use the board's
     human name from its `settings.h` comment) and to the table in `webdfu/README.md`.
     `webdfu` is a submodule: commit there first (it often has unrelated uncommitted
     `.bin` files — stage only README.md), then `git add webdfu` in the parent.
     The release workflow and the webdfu board picker read `.bin` names, so they need
     no changes.
   - **Quartz changed** for an existing board: also shows as `MISSING` — update the
     existing `add_firmware_target` line rather than adding a new one.
   - **Removed board**: ask the user before deleting targets; people may still own it.
   - **Firmware version** bumped upstream (`FIRMWARE_VERSION` in `GCC_Rules.mk`):
     Candelabra versions via `VERSION_MAJOR/MINOR/PATCH` in `CMakeLists.txt` and git
     tags, so don't copy it — just mention it so the user can decide on a release.
   - **New subdirectory under `Firmware/`**: CMake only globs `firmware/*.c` and
     `firmware/<variant>/*.c`, so a new folder needs a CMake change. New files in the
     existing folders are picked up automatically.
   - **Everything else** (sample apps, manual, images, binaries, upstream build
     scripts): not carried over. Mention anything notable in one line.

5. **Build.** Run `sync.sh build`. It must finish with 0 warnings/errors and list every
   target including new boards. If the compile breaks, the usual cause is upstream code
   relying on a define its makefiles pass that `add_firmware_target` doesn't — compare
   with upstream's `GCC_Rules.mk` and add it to `target_compile_definitions`.

6. **Commit** the firmware sync (includes `last-sync`):
   ```
   Sync upstream firmware <old-short>..<new-short>

   <one line per notable fix, from the upstream diff>

   Upstream: https://github.com/elmue/CANable-2.5-firmware-Slcan-and-Candlelight
   ```

7. **Report** what changed, the build result, and the follow-ups done or pending.
   Don't push or open a PR unless asked. When the user does push: push `webdfu` first
   if it has new commits, otherwise the parent points at a commit GitHub doesn't have.
   If there's an open upstream sync PR on GitHub (e.g. from `Elmue:main`), suggest
   closing it in favour of this branch — merging it would drag in upstream's whole tree.
