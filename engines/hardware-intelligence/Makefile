CC ?= cc
CLANG ?= clang
CFLAGS ?= -O2 -Wall -Wextra -Werror -std=c11
BUILD_DIR := build
PROBE := $(BUILD_DIR)/ithute-hw-probe
BPF_OBJ := $(BUILD_DIR)/ithute_observer.bpf.o

.PHONY: all clean ebpf

all: $(PROBE)

$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)

$(PROBE): src/probe.c | $(BUILD_DIR)
	$(CC) $(CFLAGS) -o $@ $<

ebpf: $(BPF_OBJ)

$(BPF_OBJ): bpf/ithute_observer.bpf.c | $(BUILD_DIR)
	$(CLANG) -O2 -g -target bpf -D__TARGET_ARCH_x86 -I/usr/include -c $< -o $@

clean:
	rm -rf $(BUILD_DIR)
