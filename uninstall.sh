#!/bin/sh
# Remove cx88-skytv from DKMS and go back to the in-tree cx88 modules.
# Usage: sudo ./uninstall.sh
set -e

NAME=cx88-skytv
VER=$(sed -n 's/^PACKAGE_VERSION="\(.*\)"/\1/p' "$(dirname "$0")/dkms.conf")

if [ "$(id -u)" -ne 0 ]; then
	echo "run as root: sudo $0" >&2
	exit 1
fi

modprobe -r cx88_dvb cx88_blackbird cx88_alsa cx8802 cx8800 cx88_vp3054_i2c cx88xx 2>/dev/null || true
dkms remove -m $NAME -v "$VER" --all || true
rm -rf /usr/src/$NAME-$VER
depmod -a
modprobe cx8800 || true
echo "cx88-skytv removed"
