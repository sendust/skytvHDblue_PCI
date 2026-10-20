#!/bin/sh
# Swap the stock cx88 stack for the locally built SKYTV HD Blue modules (until reboot).
# Build first (make -C src). Usage: sudo sh tools/load_test.sh [extra cx88-dvb params, e.g. skytv_inversion=1]
set -e
cd "$(dirname "$0")/../src"

# cx8802 request_module()s cx88-dvb on probe; keep the stock one from being pulled in
BLOCK=/run/modprobe.d/skytv-cx88-block.conf
mkdir -p /run/modprobe.d
printf 'install cx88_dvb /bin/true\ninstall cx88_vp3054_i2c /bin/true\ninstall cx88_blackbird /bin/true\n' > $BLOCK
trap 'rm -f $BLOCK' EXIT

modprobe -r cx88_dvb cx88_blackbird cx88_alsa cx8802 cx8800 cx88_vp3054_i2c cx88xx 2>/dev/null || true
if lsmod | grep -q '^cx88'; then
	echo "cx88 modules still loaded (device busy?):"; lsmod | grep '^cx88'; exit 1
fi

# dependencies from the running kernel
modprobe -a videobuf2-dma-sg videobuf2-v4l2 videobuf2-dvb dvb-core tveeprom rc-core \
	i2c-algo-bit snd-pcm lgdt3305

insmod ./cx88xx.ko
insmod ./cx88-vp3054-i2c.ko
insmod ./cx8800.ko
insmod ./cx8802.ko
insmod ./cx88-alsa.ko
insmod ./cx88-dvb.ko debug=1 "$@"

sleep 1
dmesg | grep -iE 'cx88|lgdt3305|dvb|skytv' | tail -25
ls -l /dev/dvb/adapter*/ 2>&1
