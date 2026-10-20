# SKYTV HD Blue PCI — hardware notes

Findings from probing the card on Linux and from interoperability analysis of the
vendor Windows driver (`skytvhdbluets.sys`, `skytvhdbluevideo.sys`, 2013-04-12).

## Chips

| Ref | Part | I2C (7-bit) | Notes |
|---|---|---|---|
| U1 | Conexant CX23880-39 | – | PCI bridge, `14f1:8800/8801/8802`, subsystem `19b8:0464` |
| U7 | LG LGDT3305 | 0x0e | 8VSB/QAM demod. INF `DemodI2CAddress=0x1C` |
| TU1 | LG-style can tuner | 0x61 | PLL. INF `TunerI2CAddress=0xC2`, `TunerModel=0x28` |
| – | IF chip in can | 0x43 | INF `Tuner2IFAddress=0x86`. Not needed for ATSC |
| U3 | Cirrus CS5340 | – | audio ADC |
| – | auth chip | 0x3d | challenge/response (regs 0x30, 0x76, 0x80, 0x89), vendor copy protection; not needed |
| – | EEPROM | 0x50 | only `07 00 00 00 b8 19 64 04`, rest 0xff |

## GPIO

The vendor driver puts the CX2388x GPIO block in **24-bit mode** by setting
`MO_GP3_IO (0x35001c)` bit 25 (`0x02000000`). In that mode:

- `MO_GP0_IO (0x350010)` = data[23:0]
- `MO_GP1_IO (0x350014)` = output enable[23:0]
- `MO_GP2_IO` reads back as a mirror of GP0
- reading `MO_GP0_IO` returns **pin levels**, so read-modify-write (`cx_set`/`cx_clear`) is unsafe — always write full values

This is different from the legacy layout Linux cx88 assumes (`GPx_IO` = [15:8] OE, [7:0] data),
which is why `card=` guessing could never power the demod.

| GPIO | Function |
|---|---|
| 0–2 | audio source select (INF XBar `GPIOMask=0x07`) |
| 9 | demod reset, active low (INF `ResetGPIO=9`) |
| 15 | demod power (hard-coded in driver) |
| 16 | demod Vdd switch (INF `VddSWGPIO=16`) |

Power-up order (vendor routine at `0x1750b`): OE on 15/16/9 with data 0, then
data15=1 → 10 ms → data16=1 → 10 ms → data9=1 → 10 ms.
The demod ACKs on I2C early but is only usable after ~200–400 ms; wait until
`GEN_CTRL_2 (0x0001)` reads non-zero (0xb0).

Driver values: GP3=`0x02000000`, GP1(OE)=`0x00018207`, GP0(data)=`0x00018203`.

## Tuner (0x61)

Not one of the `tuner-simple` types. Vendor driver writes 5 bytes:

```
DB1 DB2 CB BB AB
div = (f_center + 44 MHz) / 62.5 kHz       (vendor: picture carrier + 45.75 MHz)
CB  = 0x93 (ATSC mode, KS tuner mode 0x10), 0x9b otherwise
BB  = 0x01 (pc <= 165 MHz), 0x02 (<= 449 MHz), 0x08 (<= 861.25 MHz), pc = f_center - 1.75 MHz
AB  = 0xc2
```

Status byte bit 6 = PLL lock (0x38 unlocked → 0x78 locked).

## Demodulator (LGDT3305 @ 0x0e)

The Linux `lgdt3305` LGDT3305 path forces **low-IF** mode (`GEN_CONTROL 0x0007 = 0x2f`,
NCO for low IF) — meant for silicon tuners. This can tuner outputs a 44 MHz IF.

What works (mirrors the vendor driver):

1. Attach `lgdt3305` with `demod_chip = LGDT3304` (high-IF register flow).
2. After every tune, write the vendor 8VSB table:
   ```
   0000=03 000d=02 000e=02 0012=32 0013=c4 0112=17 0113=15 0114=18 0115=ff 0116=3c
   0214=07 0424=8d 0427=12 0428=4f 0308=80 0309=00 030d=14 030e=1c 0314=e1
   ```
3. Restore the **power-on defaults** of `0x0007` (0xef) and NCO `0x0106..0x0109`
   (`80 00 00 00`). The vendor driver never writes these; capture them right after reset.
4. `0x0126` = 0x79 (no inversion) / 0xf9.
5. `GEN_CTRL_4 (0x000a) |= 0x03` — ADC + VSB/QAM block on. `lgdt3305_sleep()` clears these
   and the LGDT3304 init never sets them again, so without this the demod is dead
   (all status registers frozen).
6. `GEN_CTRL_3 (0x0002)` = 0x00 → 20 ms → 0x01 (AGC pins out of tristate + soft reset).

Lock indicators: `dvbv5` status `Lock (0x1f)`; `0x050a` FEC lock bits 0/2/3.

## TS

`TS_GEN_CNTRL = 0x00` (INF `dwTS_GEN_CNTRL=0`), LGDT3305 parallel TS, falling edge, gated clock,
valid high. Produces ~18.5 Mbps on SBS (485 MHz).

## Debugging tips

- `dvbv5` `Signal=` is SNR-derived: 0 % whenever unlocked.
- With ADC off, every demod register is frozen — compare two dumps a second apart
  to see whether the demod is alive at all.
- `tools/gpio_probe.py` modes: `dump`, `set`, `win2` (vendor power-up), `iftest` (GPIO7/23 test).
