"""Saturation test for gs_usb (candleLight) USB CAN adapters on an ISOLATED bus.

One adapter (flooder) sends frames carrying a 16-bit sequence number as fast as it accepts them, the other
(receiver, HW timestamps on) records everything. Each adapter runs in its own process with N queued async
USB transfers per endpoint, so the host keeps up with a saturated 1 Mbit/s bus (~11,000 frames/s).
Classic CAN or CAN FD with BRS (legacy gs_usb host frame format).

Only run this on an isolated bus with just the two adapters: it takes the whole bus.
The receiver runs in normal mode so it ACKs; with only two nodes a listen-only receiver would leave
every frame unacknowledged.

    pip install libusb1
    python flood_test.py --list
    python flood_test.py --flooder 0 --receiver 1 --bitrate 1000000
    python flood_test.py --flooder 0 --receiver 1 --fd --bitrate 500000 --data-bitrate 5000000

Windows: the adapters must use the WinUSB driver (Candelabra / CANable 2.5 firmware installs it automatically,
other firmware may need Zadig). The libusb1 wheel brings its own libusb-1.0.dll.
Linux: needs libusb-1.0 and read/write access to the device (udev rule for 1d50:606f, or run as root).
The kernel gs_usb driver is detached while the test runs and re-attached afterwards.
"""
import argparse
import collections
import multiprocessing as mp
import struct
import time

import usb1

VID, PID = 0x1D50, 0x606F
EP_IN, EP_OUT = 0x81, 0x02
CAN_EFF_FLAG, CAN_ERR_FLAG = 0x80000000, 0x20000000
FLOOD_ID = 0x203000
REQ_BITTIMING, REQ_MODE, REQ_BT_CONST, REQ_DEVICE_CONFIG, REQ_BITTIMING_FD = 1, 2, 4, 5, 10
REQ_GET_LAST_ERROR = 22  # ElmueSoft / Candelabra only; ignored for other firmware
FBK_SUCCESS = 2
MODE_TS, MODE_FD = 0x10, 0x100
FEATURE_FD = 0x100
FRM_FDF, FRM_BRS = 0x02, 0x04
DLC_TO_LEN = [0, 1, 2, 3, 4, 5, 6, 7, 8, 12, 16, 20, 24, 32, 48, 64]


# ----------------------------------------------------------------------------------------------- device

def adapters(ctx):
    """[(serial, device)] of all gs_usb adapters that can be opened, sorted by serial."""
    found = []
    for d in ctx.getDeviceIterator(skip_on_error=True):
        if (d.getVendorID(), d.getProductID()) != (VID, PID):
            continue
        try:  # reading the serial opens the device: WinUSB allows only one open handle per device
            found.append((d.getSerialNumber(), d))
        except usb1.USBError:
            continue
    return sorted(found, key=lambda x: x[0])


def open_adapter(ctx, serial):
    for sn, d in adapters(ctx):
        if sn == serial:
            h = d.open()
            try:
                h.setAutoDetachKernelDriver(True)  # Linux: detach the kernel gs_usb driver, re-attach on release
            except usb1.USBError:
                pass  # Windows: not supported and not needed
            h.claimInterface(0)
            return h
    raise SystemExit(f"adapter {serial} not found or not accessible "
                     "(Linux: udev permissions? Windows: opened by another program?)")


def capability(h):
    feature, fclk = struct.unpack_from("<II", h.controlRead(0xC1, REQ_BT_CONST, 0, 0, 40, 1000))
    return feature, fclk


def ctrl(h, req, data):
    h.controlWrite(0x41, req, 0, 0, data, 1000)
    try:
        fb = h.controlRead(0xC1, REQ_GET_LAST_ERROR, 0, 0, 1, 1000)[0]
    except usb1.USBError:
        return  # firmware without ElmueSoft feedback
    if fb != FBK_SUCCESS:
        raise SystemExit(f"request {req} rejected by the firmware, feedback code {fb}")


def timing(fclk, bitrate, sp, tq_range):
    """(seg1, seg2, sjw, brp) closest to the sample point."""
    best = None
    for brp in range(1, 513):
        if fclk % (brp * bitrate):
            continue
        tq = fclk // (brp * bitrate)
        if not tq_range[0] <= tq <= tq_range[1]:
            continue
        t1 = round(tq * sp) - 1
        t2 = tq - 1 - t1
        err = abs((1 + t1) / tq - sp)
        if t1 >= 2 and t2 >= 1 and (best is None or err < best[0]):
            best = (err, t1, t2, min(t2, 16), brp)
    if best is None:
        raise SystemExit(f"no bit timing for {bitrate} bit/s at {fclk} Hz")
    return best[1:]


def start_can(h, cfg, flags):
    feature, fclk = capability(h)
    h.controlWrite(0x41, REQ_MODE, 0, 0, struct.pack("<II", 0, 0), 1000)  # reset, may fail if already closed
    ctrl(h, REQ_BITTIMING, struct.pack("<5I", 0, *timing(fclk, cfg["bitrate"], 0.875, (8, 25))))
    if cfg["fd"]:
        if not feature & FEATURE_FD:
            raise SystemExit("adapter does not support CAN FD")
        ctrl(h, REQ_BITTIMING_FD, struct.pack("<5I", 0, *timing(fclk, cfg["data_bitrate"], 0.75, (8, 32))))
        flags |= MODE_FD
    ctrl(h, REQ_MODE, struct.pack("<II", 1, flags & feature))


def drain(h):
    """Read and count packets that are already waiting before the test traffic starts.
    These are left over from the previous session (stale host queue / loaded IN endpoint)."""
    stale = []
    while True:
        try:
            stale.append(bytes(h.bulkRead(EP_IN, 128, 100)))
        except usb1.USBErrorTimeout:
            return stale


# ----------------------------------------------------------------------------------------------- frames

def payload(seq, length):
    return (struct.pack("<H", seq) + bytes(((seq + i) & 0xFF) for i in range(max(0, length - 2))))[:length]


def frame(seq, fd, dlc):
    length = DLC_TO_LEN[dlc]
    flags = FRM_FDF | FRM_BRS if fd else 0
    data = payload(seq, length).ljust(64 if fd else 8, b"\0")
    # echo_id is decorrelated from data[0] so a misrouted echo can be told apart
    return struct.pack("<IIBBBB", (seq % 8) ^ 5, FLOOD_ID | CAN_EFF_FLAG, dlc, 0, flags, 0) + data


# ----------------------------------------------------------------------------------------------- worker

def worker(role, serial, cfg, ready, stop, out):
    try:
        run_worker(role, serial, cfg, ready, stop, out)
    except BaseException as exc:  # noqa: BLE001 -- report any failure to the parent instead of hanging it
        import traceback
        out.send(dict(error=f"{role} {serial}: {exc!r}\n{traceback.format_exc()}"))


def run_worker(role, serial, cfg, ready, stop, out):
    """role 'rx' runs until 'stop' is set, role 'tx' runs for cfg['seconds']."""
    with usb1.USBContext() as ctx:
        h = open_adapter(ctx, serial)
        start_can(h, cfg, MODE_TS if role == "rx" else 0)
        stale = drain(h)

        packets, state = [], dict(running=True, sent=0, seq=0, in_errors=collections.Counter())

        def on_in(t):
            st = t.getStatus()
            if st == usb1.TRANSFER_COMPLETED:
                packets.append(bytes(t.getBuffer()[:t.getActualLength()]))
            elif st not in (usb1.TRANSFER_CANCELLED, usb1.TRANSFER_TIMED_OUT):
                state["in_errors"][st] += 1
            if state["running"] and st != usb1.TRANSFER_CANCELLED:
                t.submit()

        def on_out(t):
            st = t.getStatus()
            if st == usb1.TRANSFER_COMPLETED:
                state["sent"] += 1
            if state["running"] and st != usb1.TRANSFER_CANCELLED:
                t.setBuffer(frame(state["seq"], cfg["fd"], cfg["dlc"]))
                state["seq"] = (state["seq"] + 1) & 0xFFFF
                t.submit()

        transfers = []
        for _ in range(cfg["rx_queue"] if role == "rx" else cfg["queue"]):
            t = h.getTransfer()
            t.setBulk(EP_IN, 128, callback=on_in, timeout=0)
            t.submit()
            transfers.append(t)
        ready.set()

        if role == "tx" and not cfg["no_tx"]:
            for _ in range(cfg["queue"]):
                t = h.getTransfer()
                t.setBulk(EP_OUT, frame(state["seq"], cfg["fd"], cfg["dlc"]), callback=on_out, timeout=0)
                state["seq"] = (state["seq"] + 1) & 0xFFFF
                t.submit()
                transfers.append(t)

        t0 = time.monotonic()
        while not stop.is_set() and (role == "rx" or time.monotonic() - t0 < cfg["seconds"]):
            ctx.handleEventsTimeout(0.05)
        elapsed = time.monotonic() - t0

        # stop: cancel the queued transfers and wait until all callbacks have run
        state["running"] = False
        for t in transfers:
            if t.isSubmitted():
                try:
                    t.cancel()
                except usb1.USBError:
                    pass
        deadline = time.monotonic() + 2
        while any(t.isSubmitted() for t in transfers) and time.monotonic() < deadline:
            ctx.handleEventsTimeout(0.05)
        try:
            h.controlWrite(0x41, REQ_MODE, 0, 0, struct.pack("<II", 0, 0), 1000)
        except usb1.USBError:
            pass
        for t in transfers:
            t.close()
        h.releaseInterface(0)
        h.close()
        out.send(dict(packets=packets, stale=stale, sent=state["sent"], elapsed=elapsed,
                      in_errors=dict(state["in_errors"])))


# ----------------------------------------------------------------------------------------------- analysis

def analyse(name, packets, fd):
    st = dict(sizes=collections.Counter(), data_sizes=collections.Counter(), err=collections.Counter(),
              echo=set(), rx=set(), bad_payload=0, echo_id_bad=0, ts=[])
    for idx, p in enumerate(packets):
        st["sizes"][len(p)] += 1
        if len(p) < 20:
            continue
        echo, cid, dlc = struct.unpack_from("<IIB", p, 0)
        if cid & CAN_ERR_FLAG:
            key = f"len {len(p)} id={cid:#x} data={p[12:20].hex()}"
            st["err"][key] += 1
            st.setdefault("err_first", {}).setdefault(key, idx)
            continue
        st["data_sizes"][len(p)] += 1
        if (cid & 0x1FFFFFFF) != FLOOD_ID:
            continue
        seq = struct.unpack_from("<H", p, 12)[0]
        length = DLC_TO_LEN[dlc & 0x0F]
        if p[12:12 + length] != payload(seq, length):
            st["bad_payload"] += 1
        if echo != 0xFFFFFFFF:
            st["echo"].add(seq)
            st["echo_id_bad"] += echo != ((seq % 8) ^ 5)
        else:
            st["rx"].add(seq)
        ts_off = 12 + (64 if fd else 8)
        if len(p) >= ts_off + 4:
            st["ts"].append(struct.unpack_from("<I", p, ts_off)[0])
    print(f"== {name}: packet sizes {dict(st['sizes'])}")
    print(f"   echoes {len(st['echo'])} (wrong echo_id {st['echo_id_bad']}), rx frames {len(st['rx'])}, "
          f"bad payload {st['bad_payload']}")
    for k, v in st["err"].most_common():
        print(f"   error frame {k}: {v} (first at packet {st['err_first'][k]} of {len(packets)})")
    return st


def gaps(seqs):
    lo, hi = min(seqs), max(seqs)
    missing = sorted(set(range(lo, hi + 1)) - seqs)
    bursts, run = collections.Counter(), 0
    for i, m in enumerate(missing):
        run += 1
        if i + 1 == len(missing) or missing[i + 1] != m + 1:
            bursts[run] += 1
            run = 0
    return lo, hi, missing, bursts


def list_adapters():
    with usb1.USBContext() as ctx:
        for n, (sn, d) in enumerate(adapters(ctx)):
            h = d.open()
            try:
                feature, fclk = capability(h)
                fw = struct.unpack_from("<I", h.controlRead(0xC1, REQ_DEVICE_CONFIG, 0, 0, 12, 1000), 4)[0]
                print(f"#{n}: {sn}  {h.getProduct()}  fw {fw:#010x}  fclk {fclk // 1000000} MHz  "
                      f"features {feature:#x}{'  (FD)' if feature & FEATURE_FD else ''}  "
                      f"bus {d.getBusNumber()} port {'.'.join(map(str, d.getPortNumberList()))}")
            finally:
                h.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list", action="store_true", help="list adapters and exit")
    ap.add_argument("--flooder", type=int, default=0, help="index of the flooding adapter (see --list)")
    ap.add_argument("--receiver", type=int, default=1, help="index of the receiving adapter")
    ap.add_argument("--seconds", type=float, default=4.0, help="flood duration (keep < 65536 frames)")
    ap.add_argument("--bitrate", type=int, default=250000, help="(nominal) bitrate")
    ap.add_argument("--fd", action="store_true", help="CAN FD frames with BRS")
    ap.add_argument("--data-bitrate", type=int, default=5000000, help="CAN FD data bitrate")
    ap.add_argument("--dlc", type=int, default=None, help="DLC code (default 2 classic, 15 = 64 bytes FD)")
    ap.add_argument("--queue", type=int, default=16, help="queued USB transfers per endpoint")
    ap.add_argument("--rx-queue", type=int, default=None, help="queued reads on the receiver (0 = don't read it)")
    ap.add_argument("--no-tx", action="store_true", help="control run: flooder opened but sends nothing")
    a = ap.parse_args()

    if a.list:
        list_adapters()
        return
    with usb1.USBContext() as ctx:
        sns = [sn for sn, _ in adapters(ctx)]
    if len(sns) < 2 or a.flooder == a.receiver or max(a.flooder, a.receiver) >= len(sns):
        raise SystemExit("need two different adapters (see --list)")
    dlc = a.dlc if a.dlc is not None else (15 if a.fd else 2)
    if DLC_TO_LEN[dlc] < 2 or (dlc > 8 and not a.fd):
        raise SystemExit("DLC must carry at least 2 bytes (sequence number) and be <= 8 for classic CAN")
    cfg = dict(seconds=a.seconds, bitrate=a.bitrate, fd=a.fd, data_bitrate=a.data_bitrate, dlc=dlc,
               queue=a.queue, rx_queue=a.queue if a.rx_queue is None else a.rx_queue, no_tx=a.no_tx)
    rate = f"{a.bitrate // 1000}k" + (f"/{a.data_bitrate / 1e6:g}M FD" if a.fd else "")
    print(f"flooder #{a.flooder} {sns[a.flooder]} -> receiver #{a.receiver} {sns[a.receiver]}, {rate}, "
          f"dlc {dlc}, queue {a.queue}, {a.seconds:g} s")

    mpc = mp.get_context("spawn")
    stop, rx_ready, tx_ready = mpc.Event(), mpc.Event(), mpc.Event()
    rx_pipe, rx_out = mpc.Pipe(False)
    tx_pipe, tx_out = mpc.Pipe(False)
    rx_proc = mpc.Process(target=worker, args=("rx", sns[a.receiver], cfg, rx_ready, stop, rx_out), daemon=True)
    rx_proc.start()
    if not rx_ready.wait(15):
        raise SystemExit("receiver did not start")
    tx_proc = mpc.Process(target=worker, args=("tx", sns[a.flooder], cfg, tx_ready, mpc.Event(), tx_out),
                          daemon=True)
    tx_proc.start()

    def result(pipe, proc, timeout):
        if not pipe.poll(timeout):
            proc.kill()
            raise SystemExit(f"{proc.name} did not finish")
        r = pipe.recv()
        if "error" in r:
            raise SystemExit(r["error"])
        return r

    tx = result(tx_pipe, tx_proc, a.seconds + 20)
    time.sleep(0.3)  # let the receiver drain the last frames
    stop.set()
    rx = result(rx_pipe, rx_proc, 20)
    tx_proc.join()
    rx_proc.join()

    dt = tx["elapsed"]
    print(f"\nflooder accepted {tx['sent']} frames ({tx['sent'] / dt:.0f}/s); "
          f"USB IN errors flooder {tx['in_errors'] or 0} receiver {rx['in_errors'] or 0}")
    print(f"stale packets at start (left over from the previous session): "
          f"flooder {len(tx['stale'])}, receiver {len(rx['stale'])}")
    for who, s in (("flooder", tx["stale"]), ("receiver", rx["stale"])):
        for p in s[:5]:
            print(f"   {who} stale len {len(p)}: {p.hex()}")
    if tx["sent"] > 65000:
        print("WARNING: the 16-bit sequence wrapped, use a shorter --seconds")
    fst = analyse("FLOODER stream", tx["packets"], a.fd)
    rst = analyse("RECEIVER stream", rx["packets"], a.fd)

    E, R = fst["echo"], rst["rx"]
    print(f"\nreceiver got {len(R)} frames ({len(R) / dt:.0f}/s)")
    print(f"   echoed and on bus {len(E & R)}, echoed NOT on bus {len(E - R)}, on bus NOT echoed {len(R - E)}")
    missing = []
    if R:
        lo, hi, missing, bursts = gaps(R)
        print(f"   gaps in seq {lo}..{hi}: {len(missing)} missing, burst length -> count {dict(sorted(bursts.items()))}")
    back = None
    if len(rst["ts"]) > 2:
        d = [(b - x) & 0xFFFFFFFF for x, b in zip(rst["ts"], rst["ts"][1:])]
        fwd = sorted(x for x in d if x <= 0x80000000)
        back = len(d) - len(fwd)
        print(f"   timestamps: min {fwd[0]} us, median {fwd[len(fwd) // 2]} us, p99 {fwd[len(fwd) * 99 // 100]} us, "
              f"max {fwd[-1]} us, backwards {back}")

    if a.no_tx:
        return
    rx_size = 80 if a.fd else 24
    checks = [
        ("no stale packets at start", not tx["stale"] and not rx["stale"]),
        # error frames are classic frames (24 bytes) also in CAN FD mode
        (f"receiver: only {rx_size}-byte data frames", set(rst["data_sizes"]) <= {rx_size}),
        ("receiver: no echo frames, no bad payload", not rst["echo"] and rst["bad_payload"] == 0),
        ("receiver: no gaps", bool(R) and not missing),
        # Accepted frames that were neither echoed nor received; up to ~70 may still sit in the Tx queues at stop.
        # Not judged if the receiver has gaps: its missed frames cannot be told apart from frames never sent.
        ("flooder sends at bus rate (back-pressure)",
         None if missing else bool(R) and tx["sent"] - len(E | R) <= a.queue + 70),
        ("timestamps never backwards", back == 0),
    ]
    print()
    for text, ok in checks:
        mark = "----" if ok is None else "PASS" if ok else "FAIL"
        print(f"   [{mark}] {text}{'  (not judged: receiver has gaps)' if ok is None else ''}")


if __name__ == "__main__":
    main()
