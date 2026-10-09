# USB CAN adapter flood test (gs_usb / candleLight)

Saturation test for gs_usb ("candleLight") USB CAN adapters, and what it found
on two WeAct Studio V2 adapters. It started with a host crash under about
3,000 frames/s of traffic: the adapter sent a 20-byte packet in
hardware-timestamp mode, where 24 bytes are expected, and the gs_usb library's
fixed-size unpack raised `struct.error`.

**Short version:** the bad packet came from firmware state carried over between
sessions, not from timestamps. It's fixed on branch `usb-flow-control`, together
with the 70% silent TX drop under load. See [Findings](#findings).

| File | What |
|---|---|
| `flood_test.py` | The test. Windows and Linux, needs only `libusb1` |
| `results/results_v1.1.0_flow-control.txt` | Raw output with the fixed firmware (classic 250k / 1M, FD 500k/5M, control run) |
| `results/results_rx_v1.0.2.txt`, `results/results_rx_2.5.txt` | Raw output of the first (pyusb) version of this test on the old firmware. Most of what they show is stale data, see finding 1 |

## Running it

**Only on an isolated bus.** The flood takes the whole bus. Two adapters,
120 Ω at each end, nothing else connected.

```bash
pip install libusb1
python flood_test.py --list                                    # adapters, firmware, USB port
python flood_test.py --flooder 0 --receiver 1                  # 250 kbit/s, 4 s
python flood_test.py --flooder 1 --receiver 0 --bitrate 1000000
python flood_test.py --flooder 0 --receiver 1 --fd --bitrate 500000 --data-bitrate 5000000
python flood_test.py --flooder 1 --receiver 0 --no-tx          # control: nothing is sent
```

- **Windows:** the adapters need the WinUSB driver. Candelabra and CANable 2.5
  firmware install it automatically through MS OS descriptors; other firmware
  may need Zadig. The `libusb1` wheel ships its own `libusb-1.0.dll`. Close
  other programs that use the adapters: WinUSB allows only one open handle per
  device.
- **Linux:** needs `libusb-1.0` and access to the device, either a udev rule
  for `1d50:606f` or root. The kernel `gs_usb` driver is detached while the
  test runs and re-attached afterwards, so stop any SocketCAN interface on the
  adapters first. Tested on Windows 11; on Linux only the startup path has been
  checked (no adapters attached).

| Option | Default | |
|---|---|---|
| `--flooder`, `--receiver` | 0, 1 | adapter index from `--list` (sorted by serial) |
| `--seconds` | 4 | flood duration; keep it under 65,536 frames (16-bit sequence) |
| `--bitrate` | 250000 | (nominal) bitrate, sample point 87.5% |
| `--fd`, `--data-bitrate` | off, 5000000 | CAN FD with BRS, data sample point 75% |
| `--dlc` | 2 classic, 15 FD | DLC code; must carry at least the 2-byte sequence |
| `--queue` | 16 | queued USB transfers per endpoint |
| `--rx-queue` | = `--queue` | queued reads on the receiver; 0 = don't read it at all |
| `--no-tx` | | control run: open and start both adapters, send nothing |

### Reading the output

The test ends with a checklist. A healthy adapter on a good USB link passes
every line:

```
[PASS] no stale packets at start
[PASS] receiver: only 24-byte data frames       (80 with --fd)
[PASS] receiver: no echo frames, no bad payload
[PASS] receiver: no gaps
[PASS] flooder sends at bus rate (back-pressure)
[PASS] timestamps never backwards
```

- **stale packets at start:** packets waiting in the adapter before any traffic
  was sent. They are left over from the previous session. The firmware should
  report 0.
- **gaps:** sequence numbers the receiver never got, with a histogram of how
  many were missing in a row. Isolated single frames mean the receiver's queue
  to the host was full (see the USB IN overflow error frame, `data[5]=0x08`).
- **back-pressure:** accepted frames that were neither echoed nor received.
  Up to about 70 may still be queued in the flooder when the test stops. It
  isn't judged when the receiver has gaps, because then a missed frame can't
  be told apart from one that was never sent.
- **error frames** show the full payload. In legacy mode, `data[1]` holds the
  Linux `can/error.h` controller bits, `data[5]` the firmware's own
  `APP_xxx` flags (0x04 = CAN TX queue overflow, 0x08 = USB IN overflow),
  `data[6]`/`data[7]` the TX/RX error counters. Error frames are classic
  frames, so they are 24 bytes also in FD mode.
- Error frames among the **last** packets of a run are harmless: the flooder
  is reset in the middle of a frame when the test stops, and the receiver
  reports it, as a protocol error (`id=0x20000008`, `data[2]` set) and/or an
  error state with `data[7]=0x01` (RX error counter 1).

## Method

- Each adapter runs in its own process and keeps 16 USB transfers queued per
  endpoint (libusb async API). The first version of this test used one
  blocking `read()`/`write()` per frame from three threads in one process;
  that capped the host at about 3,600 transfers/s, which is below a saturated
  1 Mbit/s bus.
- **Flooder:** normal mode, no timestamps. Sends extended-ID frames `0x203000`
  with a 16-bit sequence number in `data[0:2]` and a sequence-derived pattern
  in the rest, as fast as the adapter accepts them. The TX echo ID is
  `(seq % 8) ^ 5`, deliberately different from `data[0] & 7`, so an echo that
  ends up in the wrong place can be identified.
- **Receiver:** **normal mode**, because it must ACK (with only two nodes a
  listen-only receiver leaves every frame unacknowledged), with
  `HW_TIMESTAMP`. It records every packet.
- Both adapters drain and count leftover packets before the flood starts.
- The parent process compares the flooder's echoes with the receiver's frames
  by sequence number.

## Setup (2026-10-09)

| | Adapter #0 | Adapter #1 |
|---|---|---|
| Serial | 208A34BB4B4550142 | 208C34994B4550142 |
| Firmware at first | Candelabra v1.0.2 | Candlelight 2.5 (ElmueSoft) |
| Firmware at the end | Candelabra v1.1.0 + `usb-flow-control` | same |
| CAN clock / feature word | 160 MHz / 0xE53B | 160 MHz / 0xE53B |

Feature bits 14 and 15 aren't in the mainline Linux `gs_usb` list: they are
ElmueSoft's protocol extensions (`ELM_DevFlagProtocolElmue`,
`ELM_DevFlagSendUsbBlobs`).

The first runs were done from a Linux devcontainer; everything after the first
round of findings ran natively on Windows 11, both adapters directly on root
hub ports 9 and 10 of the same USB 3 controller.

## Findings

The first version of this README listed five firmware findings. Re-running with
controls showed that four of them came from one cause.

### 1. Stale packets from the previous session (the crash)

v1.0.2 and 2.5 cleared only the CAN TX queue when a channel was opened or
closed. The **queue to the host (70 entries) survived**, and the receiver in
each run had been the flooder in the run before. So every session started by
delivering about 70 leftover packets from the previous one: TX echoes, TX
overflow error frames and old timestamps. The **control run** proved it: with
the flooder sending nothing, its stream still produced 23 echoes and
49 error frames.

What the original findings actually showed:

| Original finding | Explanation |
|---|---|
| 20-byte error frame in timestamp mode | The last packet the previous session had already loaded into the USB IN endpoint, still in that session's non-timestamp format |
| RX frames carrying the flooder's echo ID | Leftover echoes from when this adapter was the flooder |
| TX overflow error frames on a receiver | Leftover error frames from its flooder session |
| Timestamps backwards, 12–17 µs gaps, 20–167 s jumps | Leftover packets carry the old session's timestamps |

v1.1.0 already clears both queues (upstream sync f9c3bcb), which leaves
1 stale packet per session: the one loaded in the IN endpoint. Commit
`79689cd` discards it when a channel is opened or closed (it sets the endpoint
to NAK; close/reopen would reset the USB data toggle). Result: **0 stale
packets**, only 24-byte packets on the receiver, timestamps 330–380 µs apart at
250 kbit/s and never backwards.

### 2. 70% of TX frames silently dropped (no back-pressure)

At 250 kbit/s the host could push about 10,000 frames/s into the flooder while
the bus carries about 2,850/s. The firmware accepted every USB OUT transfer and
dropped what didn't fit its 64-entry CAN TX queue. Each drop sent an immediate
TX overflow error frame, about 5,500 per second, and those overflowed the queue
to the host, which then also dropped real TX echoes.

The TX echo itself is honest: every echoed frame was seen on the bus. In legacy
mode the firmware sends the echo when the frame enters the controller's 3-deep
TX FIFO, not when it has been transmitted, so it can be up to 3 frames early.
The original "echoes for frames never transmitted"
finding came from counting every IN packet as an echo, error frames included.

Commit `5f6d195` NAKs the USB OUT endpoint while the CAN TX queue is full and
accepts data again once frames have gone out. Results:

| | Before | After |
|---|---|---|
| Frames accepted at 250 kbit/s | ~9,700–10,600/s, ~70% dropped | 2,848/s = bus rate, 0 dropped |
| TX overflow error frames | ~5,500/s | 0 |
| Frames on the bus but not echoed | 4,600–7,600 per 5 s | 0 |

The host's writes now block while the bus is busy, and for up to 500 ms when
nothing ACKs before the firmware's TX timeout clears the queue.

### 3. The cable

At a saturated bus, one adapter dropped 0.7–2.6% of frames when receiving
(isolated single frames, reported as USB IN overflow) and flooded about 3%
slower. Swapping adapters and ports showed it follows **one USB cable**
("cable X"), not the adapter or the port. USB full speed retries corrupted
packets in hardware, which costs time without any visible error. In legacy
mode at about 11,000 frames/s there is no headroom for that. Keep marginal
cables off adapters that have to run a saturated bus.

### Results with the fixed firmware

From `results/results_v1.1.0_flow-control.txt` (Windows, async test). "Good cable"
means the receiver wasn't on cable X:

| Bus | Frames/s | Receiver (good cable) | Echoes |
|---|---|---|---|
| Classic 250 kbit/s | ~2,850 | lossless | all |
| Classic 1 Mbit/s | 10,700–11,100 | lossless | 17–42% missing, see limits |
| FD 500k/5M, 64 bytes | 3,590–3,830 | lossless, 0 bad payload (2 USB packets per frame) | all |

### Known limits

- **Echoes at 1 Mbit/s:** the flooder has to take in about 11,000 USB OUT
  transfers/s and send about 11,000 echo transfers/s, one frame per transfer
  each way. It can't do both: it drops echoes and reports a USB IN overflow.
  This is the legacy gs_usb protocol's limit. ElmueSoft mode can bundle frames
  into one transfer (`ELM_DevFlagSendUsbBlobs`), which this test doesn't use.
- **Error reports are rate-limited** to one per 100 ms when the state changes
  and one per 3 s when it doesn't, so thousands of dropped echoes show up as
  one or two error frames.
- **Timestamps** are taken when the firmware moves a frame out of the
  controller's RX FIFO, not at reception on the bus, so they carry the main
  loop's latency as jitter. Under the floods above they stayed monotonic, with
  gaps close to the frame time (median 86 µs at 1 Mbit/s, 348 µs at 250 kbit/s).

## History of this README

The first version blamed the timestamp layout of error frames, echoes for
untransmitted frames and host-side mixing between the adapters. Those
conclusions came from the stale-packet bug (finding 1) and from the old test
counting every IN packet as an echo. This version replaces them.
