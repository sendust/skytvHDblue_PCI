#!/usr/bin/env python3
"""CX2388x GPIO probe: find which GPIO releases the LGDT3305 demod reset.

Usage (root):
  sudo python3 -I gpio_probe.py dump     # read GPIO registers only
  sudo python3 -I gpio_probe.py probe    # toggle each GPIO bit, look for demod on I2C
  sudo python3 -I gpio_probe.py probe2   # drive-low per bit + multi-bit combinations
  sudo python3 -I gpio_probe.py set GP0 GP1 GP2   # write raw values, keep them, full I2C scan
  sudo python3 -I gpio_probe.py power    # INF-based Vdd (GP2.0) + reset (GP1.1) sequence
  sudo python3 -I gpio_probe.py win      # Windows driver GPIO mode (GP3 bit25, 24-bit OE/data)
  sudo python3 -I gpio_probe.py win2     # same, corrected: GP1=OE GP0=data, GPIO15+Vdd+Rst sequence
  sudo python3 -I gpio_probe.py iftest   # patched driver loaded: toggle GPIO7/23 while tuned to 485 MHz
Original register values are always restored at the end.
"""
import mmap, os, struct, subprocess, sys, time

PCI = "/sys/bus/pci/devices/0000:03:00.0/resource0"
I2C_BUS = "7"
DEMOD_ADDRS = (0x0e, 0x0f, 0x59)  # LGDT3305 primary/alt, 0x59 = 8-bit 0xb2 variant

# cx88-reg.h: each GPx_IO reg = [15:8] output enable, [7:0] data
REGS = {"GP0_IO": 0x350010, "GP1_IO": 0x350014, "GP2_IO": 0x350018, "GP3_IO": 0x35001c}


def rd(m, off):
    return struct.unpack_from("<I", m, off)[0]


def wr(m, off, val):
    struct.pack_into("<I", m, off, val)


def i2c_present(addr):
    r = subprocess.run(["i2cget", "-y", I2C_BUS, hex(addr)], capture_output=True)
    return r.returncode == 0


def found():
    return [hex(a) for a in DEMOD_ADDRS if i2c_present(a)]


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "dump"
    fd = os.open(PCI, os.O_RDWR | os.O_SYNC)
    m = mmap.mmap(fd, 0x400000, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE)
    orig = {n: rd(m, o) for n, o in REGS.items()}
    for n, v in orig.items():
        print(f"{n} = 0x{v:08x}  (OE=0x{(v >> 8) & 0xff:02x} DATA=0x{v & 0xff:02x})")
    print("demod before:", found() or "none")
    if mode == "set":
        # set GP0..GP2 to given raw values and leave them (no restore), then full scan
        for n, v in zip(("GP0_IO", "GP1_IO", "GP2_IO"), sys.argv[2:5]):
            wr(m, REGS[n], int(v, 0))
            print(f"{n} <- 0x{rd(m, REGS[n]):08x}")
        time.sleep(0.1)
        subprocess.run(["i2cdetect", "-y", "-r", I2C_BUS])
        return
    if mode == "win":
        # Sequence taken from skytvhdbluets.sys (Windows): GP3_IO |= 0x2000000 switches to
        # 24-bit GPIO mode, then GP0_IO = output enable[23:0], GP1_IO = data[23:0].
        # INF: VddSWGPIO=16, ResetGPIO=9. GPIO is left in this state.
        VDD, RST = 1 << 16, 1 << 9
        g3, g0, g1 = REGS["GP3_IO"], REGS["GP0_IO"], REGS["GP1_IO"]
        wr(m, g3, rd(m, g3) | 0x2000000)
        wr(m, g1, (rd(m, g1) | VDD) & ~RST)   # Vdd on, reset asserted
        wr(m, g0, rd(m, g0) | VDD | RST)      # enable both outputs
        time.sleep(0.2)
        wr(m, g1, rd(m, g1) | RST)            # release reset
        time.sleep(0.2)
        for n, o in REGS.items():
            print(f"{n} = 0x{rd(m, o):08x}")
        for i in range(10):
            print(f"t={0.2 + i * 0.5:.1f}s 0x0e:", "FOUND" if i2c_present(0x0e) else "-")
            time.sleep(0.5)
        subprocess.run(["i2cdetect", "-y", "-r", I2C_BUS])
        return
    if mode == "iftest":
        # With the patched driver loaded: hold a tune on 485 MHz (Seoul SBS ch16), drive
        # GPIO7/GPIO23 in all four combinations and watch demod lock/MSE.
        # Full writes only (GP0 reads back pin levels); driver values restored at the end.
        conf = "/tmp/skytv-sbs16.conf"
        with open(conf, "w") as f:
            f.write("[SBS16]\n\tDELIVERY_SYSTEM = ATSC\n\tFREQUENCY = 485000000\n"
                    "\tMODULATION = VSB/8\n\n")
        zap = subprocess.Popen(["dvbv5-zap", "-a", "0", "-c", conf, "-m", "SBS16"],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)
        g3, g0, g1 = REGS["GP3_IO"], REGS["GP0_IO"], REGS["GP1_IO"]
        DATA, OE = 0x00018203, 0x00018207
        P7, P23 = 1 << 7, 1 << 23

        def demod(reg):
            r = subprocess.run(["i2ctransfer", "-y", I2C_BUS, "w2@0x0e",
                                str(reg >> 8), str(reg & 0xff), "r1"],
                               capture_output=True, text=True)
            return r.stdout.strip() or "--"

        def report(label):
            regs = [0x011d, 0x050a, 0x011b, 0x011c, 0x0310, 0x0311, 0x0312, 0x0313]
            print(f"{label:28s} " + " ".join(f"{r:04x}={demod(r)}" for r in regs))

        try:
            wr(m, g3, 0x02000000)
            report("baseline (7,23 inputs)")
            for d7 in (0, 1):
                for d23 in (0, 1):
                    data = DATA | (P7 if d7 else 0) | (P23 if d23 else 0)
                    wr(m, g0, data)
                    wr(m, g1, OE | P7 | P23)
                    subprocess.run(["i2ctransfer", "-y", I2C_BUS, "w3@0x0e", "0", "2", "0"])
                    time.sleep(0.02)
                    subprocess.run(["i2ctransfer", "-y", I2C_BUS, "w3@0x0e", "0", "2", "1"])
                    time.sleep(2)
                    report(f"GPIO7={d7} GPIO23={d23}")
        finally:
            wr(m, g0, DATA)
            wr(m, g1, OE)
            zap.terminate()
            print("GPIO restored to driver values.")
        return
    if mode == "win2":
        # Corrected from skytvhdbluets.sys demod power-on routine (0x1750b):
        # in 24-bit mode GP1_IO = output enable[23:0], GP0_IO = data[23:0].
        # OE(15,Vdd,Rst)=1; data15=1; 10ms; Vdd=1; 10ms; Rst=1; 10ms.
        P15, VDD, RST = 1 << 15, 1 << 16, 1 << 9
        g3, g0, g1 = REGS["GP3_IO"], REGS["GP0_IO"], REGS["GP1_IO"]
        wr(m, g3, rd(m, g3) | 0x2000000)
        wr(m, g0, rd(m, g0) & ~(P15 | VDD | RST))   # all off first (driver constructor)
        wr(m, g1, rd(m, g1) | P15 | VDD | RST)
        time.sleep(0.2)
        for bit in (P15, VDD, RST):
            wr(m, g0, rd(m, g0) | bit)
            time.sleep(0.05)
        for n, o in REGS.items():
            print(f"{n} = 0x{rd(m, o):08x}")
        for i in range(6):
            print(f"t={i * 0.5:.1f}s 0x0e:", "FOUND" if i2c_present(0x0e) else "-")
            time.sleep(0.5)
        subprocess.run(["i2cdetect", "-y", "-r", I2C_BUS])
        return
    if mode == "power":
        # Windows INF: ResetGPIO=9 (GP1 bit1), VddSWGPIO=16 (GP2 bit0), demod 0x1c>>1 = 0x0e.
        # Try each Vdd/reset polarity with a proper power-up + reset sequence; stop at first hit
        # and leave GPIO in that state.
        gp1 = orig["GP1_IO"] & 0xff
        for vdd_on in (1, 0):
            for rst_active in (0, 1):
                vdd = (0x01 << 8) | (vdd_on & 1)
                wr(m, REGS["GP2_IO"], vdd)
                time.sleep(0.2)
                rst = lambda lv: wr(m, REGS["GP1_IO"], (0x02 << 8) | (gp1 & ~0x02) | (lv << 1))
                rst(rst_active)
                time.sleep(0.05)
                rst(1 - rst_active)
                time.sleep(0.2)
                hit = i2c_present(0x0e)
                print(f"VddSW(GP2.0)={vdd_on} reset(GP1.1) active={'high' if rst_active else 'low'}:"
                      f" 0x0e {'FOUND' if hit else '-'}")
                if hit:
                    print(f"GP1_IO=0x{rd(m, REGS['GP1_IO']):08x} GP2_IO=0x{rd(m, REGS['GP2_IO']):08x} (kept)")
                    subprocess.run(["i2cdetect", "-y", "-r", I2C_BUS])
                    return
        wr(m, REGS["GP1_IO"], orig["GP1_IO"])
        wr(m, REGS["GP2_IO"], orig["GP2_IO"])
        print("not found, GPIO restored.")
        return
    if mode == "probe2":
        try:
            probe2(m, orig)
        finally:
            for n, o in REGS.items():
                wr(m, o, orig[n])
            print("GPIO restored.")
        return
    if mode != "probe":
        return

    try:
        for n in ("GP0_IO", "GP1_IO", "GP2_IO"):
            off, base = REGS[n], orig[n]
            for bit in range(8):
                for level in (1, 0, 1):  # high, low (reset pulse), high
                    oe = ((base >> 8) | (1 << bit)) & 0xff
                    data = (base & 0xff) | (1 << bit) if level else (base & 0xff) & ~(1 << bit)
                    wr(m, off, (oe << 8) | data)
                    time.sleep(0.05)
                hit = found()
                print(f"{n} bit{bit} driven high (after reset pulse): {hit or '-'}")
                if hit:
                    print(f"  -> FOUND: {n} = 0x{rd(m, off):08x}")
                wr(m, off, base)
                time.sleep(0.02)
    finally:
        for n, o in REGS.items():
            wr(m, o, orig[n])
        print("GPIO restored.")


def probe2(m, orig):
    names = ("GP0_IO", "GP1_IO", "GP2_IO")

    # 1) drive every pin that idles low to high at the same time (power + reset combos)
    for n in names:
        low = ~orig[n] & 0xff
        wr(m, REGS[n], (low << 8) | 0xff)
    time.sleep(0.1)
    print("all idle-low pins driven high:", found() or "-")
    for n in names:
        wr(m, REGS[n], orig[n])
    time.sleep(0.05)

    # 2) drive each pin low individually (active-high reset / active-low enable)
    for n in names:
        off, base = REGS[n], orig[n]
        for bit in range(8):
            wr(m, off, ((1 << bit) << 8) | ((base & 0xff) & ~(1 << bit)))
            time.sleep(0.05)
            hit = found()
            print(f"{n} bit{bit} driven low: {hit or '-'}")
            if hit:
                print(f"  -> FOUND: {n} = 0x{rd(m, off):08x}")
            wr(m, off, base)
            time.sleep(0.02)

    # 3) all GP0..GP2 outputs low, then all high (catches active-low enable + reset pairs)
    for level in (0x00, 0xff):
        for n in names:
            wr(m, REGS[n], 0xff00 | level)
        time.sleep(0.1)
        print(f"all GP0-2 outputs = 0x{level:02x}:", found() or "-")


if __name__ == "__main__":
    main()
