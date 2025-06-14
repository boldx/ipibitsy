PROJECT = ipibitsy
BUILD_DIR = bin

CFILES = ipibitsy.c
CFILES += usb.c

DEVICE=stm32f411ceu6
OOCD_FILE = board/nucleo-f411re.cfg

# You shouldn't have to edit anything below here.
VPATH += $(SHARED_DIR)
INCLUDES += $(patsubst %,-I%, . $(SHARED_DIR))
OPENCM3_DIR=../libopencm3

include $(OPENCM3_DIR)/mk/genlink-config.mk
include ../rules.mk
include $(OPENCM3_DIR)/mk/genlink-rules.mk
