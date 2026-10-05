// SPDX-License-Identifier: GPL-2.0
// Ithute Hardware Intelligence: initial read-only eBPF counters.

#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>

struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
    __uint(max_entries, 4);
    __type(key, __u32);
    __type(value, __u64);
} event_counters SEC(".maps");

static __always_inline void increment(__u32 key) {
    __u64 *value = bpf_map_lookup_elem(&event_counters, &key);
    if (value) {
        __sync_fetch_and_add(value, 1);
    }
}

SEC("tracepoint/block/block_rq_issue")
int ithute_block_issue(void *ctx) {
    (void)ctx;
    increment(0);
    return 0;
}

SEC("tracepoint/block/block_rq_complete")
int ithute_block_complete(void *ctx) {
    (void)ctx;
    increment(1);
    return 0;
}

SEC("tracepoint/sched/sched_process_exit")
int ithute_process_exit(void *ctx) {
    (void)ctx;
    increment(2);
    return 0;
}

SEC("tracepoint/oom/mark_victim")
int ithute_oom_victim(void *ctx) {
    (void)ctx;
    increment(3);
    return 0;
}

char LICENSE[] SEC("license") = "GPL";
