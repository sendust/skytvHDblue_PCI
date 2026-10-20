---
name: skytv-hd-blue
description: Build, install, debug or port the cx88-skytv Linux driver for the SKYTV HD Blue PCI ATSC card (CX23880 + LGDT3305, PCI subsystem 19b8:0464). Use when the card shows up as cx88 UNKNOWN/GENERIC, has no /dev/dvb, fails to lock, when rebasing the patch onto a new kernel, or when adding a similar cx88 + LGDT3305 board.
---

# SKYTV HD Blue PCI (cx88-skytv)

Repo layout: `src/` (cx88 from Linux v7.0 + patch), `patches/` (diff vs upstream),
`dkms.conf`, `install.sh`, `uninstall.sh`, `docs/HARDWARE.md` (full register/GPIO notes),
`tools/gpio_probe.py`, `tools/load_test.sh`. Read `docs/HARDWARE.md` before changing driver code.

## Check state

```sh
lspci -nnk -s $(lspci -d 14f1:8800 | cut -d' ' -f1)    # cx8800 driver in use
dmesg | grep -iE 'cx88xx: subsystem|SKYTV|lgdt3305|registering adapter'
dkms status cx88-skytv
modinfo -n cx88-dvb          # should be .../updates/dkms/cx88-dvb.ko*
ls /dev/dvb/adapter0
i2cdetect -l | grep cx88     # find the cx88 I2C bus; expect 0x0e 0x3d 0x43 0x50 0x61 on it
```

Expected: `board: SKYTV HD Blue PCI [card=92,autodetected]`,
`demod up after N ms (0xb0)`, `demod defaults 0007=ef NCO=80 00 00 00`,
`registering adapter 0 frontend 0 (LG Electronics LGDT3304 VSB/QAM Frontend)`.

## Build / install

- Quick test without installing: `make -C src && sudo sh tools/load_test.sh`.
  It blocks auto-loading of the stock `cx88_dvb`/`cx88_vp3054_i2c` via `/run/modprobe.d`
  while it swaps modules — without that, `cx8802` pulls in the stock `cx88-dvb`
  ("frontend of your DVB/ATSC card isn't supported yet") and insmod fails with "File exists".
- Permanent: `sudo ./install.sh` (DKMS, installs to `updates/dkms`, reloads the stack).
- Root is needed for insmod, DKMS and GPIO MMIO; user needs the `i2c` group for i2c-tools.
  If running inside Claude Code without sudo, ask the user to run the command with a `!` prefix.

## Known failure modes → cause

| Symptom | Cause / fix |
|---|---|
| `card=0`, frontend(s): 0 | stock cx88 loaded; install DKMS package or run load_test |
| `lgdt3305_read_reg ... ret == -6` / `unable to detect` | demod not ready; GPIO power sequence or wait too short (`skytv_wait_demod` waits for 0x0001 != 0) |
| frontend exists, never locks, all demod regs frozen | ADC off: `GEN_CTRL_4 (0x000a)` bits 0/1 cleared — `skytv_set_frontend` must set them |
| demod regs live but no lock | IF/NCO wrong: must restore power-on 0x0007 and NCO 0x0106-9 after each tune; check tuner PLL status 0x61 bit6 |
| `Signal= 0.00%` | meaningless before lock (SNR-derived) — don't use it as a signal test |
| dmesg flooded with `rc rc0: error -5` | `ir_kbd_i2c` bound to a phantom 0x18 (`/sys/class/rc/rc0` → `i2c-N/N-0018`); fixed in 1.1 by skipping the IR probe for this board. Stop it live: `sudo rmmod ir_kbd_i2c` |

## Debugging without rebuilding

Tune and hold with `dvbv5-zap -a 0 -c conf -m NAME &`, then poke over I2C
(bus number from `i2cdetect -l`):

```sh
rd(){ i2ctransfer -y $BUS w2@0x0e $(($1>>8)) $(($1&0xff)) r1; }
rd 0x000a; rd 0x0002; rd 0x0003; rd 0x011d; rd 0x050a   # power, reset, status, CR, FEC
i2cget -y $BUS 0x61                                     # tuner: 0x78 = PLL locked
```

Compare two register dumps a second apart: if nothing changes, the demod isn't running.
`skytv_inversion`, `skytv_if_khz`, `skytv_cb`, `skytv_ab` can be changed at runtime in
`/sys/module/cx88_dvb/parameters/` (root) and apply on the next tune.

GPIO (needs root, MMIO via `/sys/bus/pci/devices/<cx8800 BDF>/resource0`): use
`tools/gpio_probe.py` — edit its `PCI` path and `I2C_BUS` for the target machine first.
24-bit GPIO mode: GP3 bit25 on, GP1 = OE, GP0 = data, never read-modify-write GP0.

## Porting to a newer kernel

1. Fetch that kernel's `drivers/media/pci/cx88/*` into `src/` and the frontend/tuner
   headers it includes into `src/inc/` (git.kernel.org `plain/...?h=vX.Y`).
2. Apply `patches/0001-media-cx88-add-SKYTV-HD-Blue-PCI.patch` (fix board number if
   `CX88_BOARD_*` numbering moved).
3. Update `BUILD_EXCLUSIVE_KERNEL` in `dkms.conf`, bump `PACKAGE_VERSION`.
4. Build with `make -C src`, test with `tools/load_test.sh`, then `install.sh`.
5. Verify: lock on a known channel, record with `dvbv5-zap -p -r -o x.ts -t 8 NAME`,
   `ffprobe x.ts` should show mpeg2video 1920x1080 + ac3.

## Reverse-engineering references

Vendor driver offsets used (x86 `skytvhdbluets.sys`, objdump VMA): GPIO helpers
`0x1105e`/`0x110c8`, demod power-up `0x1750b`, tuner set-frequency `0x17a5c`,
8VSB table at `.data` 0x1c39c, auth chip handshake `0x15660`/`0x15be0`.
