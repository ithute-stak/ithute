CC ?= cc
CLANG ?= clang
CFLAGS ?= -O2 -Wall -Wextra -Werror -std=c11
ARCH := $(shell uname -m)
BUILD_DIR := build
ARCH_INCLUDE ?= /usr/include/$(shell uname -m)-linux-gnu
PROBE := $(BUILD_DIR)/ithute-hw-probe
BPF_OBJ := $(BUILD_DIR)/ithute_observer.bpf.o
PROBE_SOURCES := src/probe.c src/asm_helpers.c
ifeq ($(ARCH),x86_64)
PROBE_SOURCES += src/asm_helpers.S
endif

.PHONY: all clean ebpf

all: $(PROBE)

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(PROBE): $(PROBE_SOURCES) include/asm_helpers.h | $(BUILD_DIR)
	$(CC) $(CFLAGS) -Iinclude -o $@ $(PROBE_SOURCES)

ebpf: $(BPF_OBJ)

$(BPF_OBJ): bpf/ithute_observer.bpf.c | $(BUILD_DIR)
	$(CLANG) -O2 -g -target bpf -D__TARGET_ARCH_x86 -I/usr/include -I$(ARCH_INCLUDE) -c $< -o $@

clean:
	rm -rf $(BUILD_DIR)
