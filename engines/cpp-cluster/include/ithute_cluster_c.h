#pragma once

#include <cstddef>
#include <cstdint>

#ifdef __cplusplus
extern "C" {
#endif

struct ithute_cluster_summary {
    std::size_t nodes;
    std::size_t edges;
    std::size_t online_nodes;
    std::size_t healthy_nodes;
    std::uint64_t memory_total_bytes;
    std::uint64_t memory_used_bytes;
    std::uint64_t storage_total_bytes;
    std::uint64_t storage_used_bytes;
};

void* ithute_cluster_create();
void ithute_cluster_destroy(void* handle);

int ithute_cluster_upsert_node(
    void* handle,
    const char* id,
    const char* name,
    const char* private_ip,
    int status,
    int healthy,
    double cpu_used_percent,
    std::uint64_t memory_total_bytes,
    std::uint64_t memory_used_bytes,
    std::uint64_t storage_total_bytes,
    std::uint64_t storage_used_bytes
);

int ithute_cluster_upsert_edge(
    void* handle,
    const char* source,
    const char* target,
    int relation,
    const char* service,
    const char* protocol,
    std::uint16_t port
);

int ithute_cluster_reachable(
    void* handle,
    const char* source,
    const char* target
);

int ithute_cluster_summary_read(
    void* handle,
    struct ithute_cluster_summary* out
);

int ithute_cluster_rank_candidates(
    const char* const* keys,
    const double* scores,
    const int* eligible,
    std::size_t count,
    std::size_t* out_indices,
    std::size_t out_capacity
);

#ifdef __cplusplus
}
#endif
