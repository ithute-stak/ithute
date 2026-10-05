// SPDX-License-Identifier: GPL-2.0
// Ithute Hardware Intelligence: read-only kernel counters and block latency histogram.

#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>

struct latency_stats {
    __u64 count;
    __u64 total_ns;
    __u64 max_ns;
};

struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
    __uint(max_entries, 4);
    __type(key, __u32);
    __type(value, __u64);
} event_counters SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_LRU_HASH);
    __uint(max_entries, 65536);
    __type(key, __u64);
    __type(value, __u64);
} block_request_start_ns SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
    __uint(max_entries, 16);
    __type(key, __u32);
    __type(value, __u64);
} block_latency_hist SEC(".maps");

struct {
    __uint(type, BPF_MAP_TYPE_PERCPU_ARRAY);
    __uint(max_entries, 1);
    __type(key, __u32);
    __type(value, struct latency_stats);
} block_latency_stats SEC(".maps");

static __always_inline void increment(__u32 key) {
    __u64 *value = bpf_map_lookup_elem(&event_counters, &key);
    if (value) {
        (*value)++;
    }
}

static __always_inline __u32 latency_bucket_us(__u64 us) {
    if (us <= 100) return 0;
    if (us <= 250) return 1;
    if (us <= 500) return 2;
    if (us <= 1000) return 3;
    if (us <= 2000) return 4;
    if (us <= 4000) return 5;
    if (us <= 8000) return 6;
    if (us <= 16000) return 7;
    if (us <= 32000) return 8;
    if (us <= 64000) return 9;
    if (us <= 128000) return 10;
    if (us <= 256000) return 11;
    if (us <= 512000) return 12;
    if (us <= 1000000) return 13;
    if (us <= 2000000) return 14;
    return 15;
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

SEC("raw_tracepoint/block_rq_issue")
int ithute_block_latency_issue(struct bpf_raw_tracepoint_args *ctx) {
    __u64 request = ctx->args[0];
    if (!request) return 0;

    __u64 now = bpf_ktime_get_ns();
    bpf_map_update_elem(&block_request_start_ns, &request, &now, BPF_ANY);
    return 0;
}

SEC("raw_tracepoint/block_rq_complete")
int ithute_block_latency_complete(struct bpf_raw_tracepoint_args *ctx) {
    __u64 request = ctx->args[0];
    if (!request) return 0;

    __u64 *started = bpf_map_lookup_elem(&block_request_start_ns, &request);
    if (!started) return 0;

    __u64 start_ns = *started;
    __u64 now = bpf_ktime_get_ns();
    bpf_map_delete_elem(&block_request_start_ns, &request);
    if (now < start_ns) return 0;

    __u64 latency_ns = now - start_ns;
    __u64 latency_us = latency_ns / 1000;
    __u32 bucket = latency_bucket_us(latency_us);

    __u64 *count = bpf_map_lookup_elem(&block_latency_hist, &bucket);
    if (count) {
        (*count)++;
    }

    __u32 stats_key = 0;
    struct latency_stats *stats = bpf_map_lookup_elem(&block_latency_stats, &stats_key);
    if (stats) {
        stats->count++;
        stats->total_ns += latency_ns;
        if (latency_ns > stats->max_ns) {
            stats->max_ns = latency_ns;
        }
    }
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
