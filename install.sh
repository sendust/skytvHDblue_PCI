#!/bin/sh
# Install cx88-skytv with DKMS and switch the running cx88 stack over to it.
# Usage: sudo ./install.sh
set -e

NAME=cx88-skytv
VER=$(sed -n 's/^PACKAGE_VERSION="\(.*\)"/\1/p' "$(dirname "$0")/dkms.conf")
SRC=/usr/src/$NAME-$VER

if [ "$(id -u)" -ne 0 ]; then
	echo "run as root: sudo $0" >&2
	exit 1
fi

if dkms status -m $NAME -v "$VER" | grep -q .; then
	dkms remove -m $NAME -v "$VER" --all
fi
rm -rf "$SRC"
mkdir -p "$SRC"
cp -r "$(dirname "$0")"/dkms.conf "$(dirname "$0")"/src "$SRC"/

dkms add -m $NAME -v "$VER"
dkms build -m $NAME -v "$VER"
dkms install -m $NAME -v "$VER"

# reload: the in-tree cx88 modules are replaced by the ones in updates/dkms
modprobe -r cx88_dvb cx88_blackbird cx88_alsa cx8802 cx8800 cx88_vp3054_i2c cx88xx 2>/dev/null || true
modprobe cx8800
modprobe cx88-alsa
modprobe cx88-dvb

sleep 1
modinfo -n cx88-dvb
dmesg | grep -iE 'SKYTV|registering adapter' | tail -4
ls /dev/dvb/adapter*/ 2>/dev/null || echo "no /dev/dvb yet - see dmesg"
