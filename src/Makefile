# SPDX-License-Identifier: GPL-2.0
# Out-of-tree cx88 build with SKYTV HD Blue PCI (19b8:0464) support.
# All cx88 modules are rebuilt together so their internal ABI matches.
cx88xx-objs	:= cx88-cards.o cx88-core.o cx88-i2c.o cx88-tvaudio.o \
		   cx88-dsp.o cx88-input.o
cx8800-objs	:= cx88-video.o cx88-vbi.o
cx8802-objs	:= cx88-mpeg.o

obj-m += cx88xx.o cx8800.o cx8802.o cx88-alsa.o cx88-blackbird.o \
	 cx88-dvb.o cx88-vp3054-i2c.o

ccflags-y += -I$(src)/inc

KVER ?= $(shell uname -r)
KDIR ?= /lib/modules/$(KVER)/build

all:
	$(MAKE) -C $(KDIR) M=$(CURDIR) modules

clean:
	$(MAKE) -C $(KDIR) M=$(CURDIR) clean
