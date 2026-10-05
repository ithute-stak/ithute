#include "ithute_cluster_c.h"
#include "cluster_graph.hpp"
#include "placement_scheduler.hpp"

#include <memory>
#include <mutex>
#include <string>
#include <utility>
#include <vector>

namespace {

using ithute::cluster::ClusterGraph;
using ithute::cluster::Edge;
using ithute::cluster::Node;
using ithute::cluster::NodeStatus;
using ithute::cluster::PlacementCandidate;
using ithute::cluster::Relation;
using ithute::cluster::ResourceState;
using ithute::cluster::rank_placement_candidates;

struct Handle {
    std::mutex mutex;
    ClusterGraph graph;
};

NodeStatus node_status_from_int(int value) {
    switch (value) {
        case 1: return NodeStatus::Online;
        case 2: return NodeStatus::Offline;
        case 3: return NodeStatus::Maintenance;
        default: return NodeStatus::Unknown;
    }
}

Relation relation_from_int(int value) {
    switch (value) {
        case 1: return Relation::Hosts;
        case 2: return Relation::DependsOn;
        case 3: return Relation::BacksUpTo;
        case 4: return Relation::ReplicatesTo;
        default: return Relation::CommunicatesWith;
    }
}

std::string safe_string(const char* value) {
    return value == nullptr ? std::string{} : std::string{value};
}

}  // namespace

extern "C" void* ithute_cluster_create() {
    try {
        return new Handle{};
    } catch (...) {
        return nullptr;
    }
}

extern "C" void ithute_cluster_destroy(void* handle) {
    delete static_cast<Handle*>(handle);
}

extern "C" int ithute_cluster_upsert_node(
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
) {
    if (handle == nullptr || id == nullptr || *id == '\0') {
        return 1;
    }
    try {
        Node node{};
        node.id = safe_string(id);
        node.name = safe_string(name);
        node.private_ip = safe_string(private_ip);
        node.status = node_status_from_int(status);
        node.healthy = healthy != 0;
        node.resources = ResourceState{
            .cpu_used_percent = cpu_used_percent,
            .memory_total_bytes = memory_total_bytes,
            .memory_used_bytes = memory_used_bytes,
            .storage_total_bytes = storage_total_bytes,
            .storage_used_bytes = storage_used_bytes,
        };
        auto* state = static_cast<Handle*>(handle);
        std::scoped_lock lock(state->mutex);
        state->graph.upsert_node(std::move(node));
        return 0;
    } catch (...) {
        return 2;
    }
}

extern "C" int ithute_cluster_upsert_edge(
    void* handle,
    const char* source,
    const char* target,
    int relation,
    const char* service,
    const char* protocol,
    std::uint16_t port
) {
    if (handle == nullptr || source == nullptr || target == nullptr) {
        return 1;
    }
    try {
        Edge edge{
            .source = safe_string(source),
            .target = safe_string(target),
            .relation = relation_from_int(relation),
            .service = safe_string(service),
            .protocol = safe_string(protocol),
            .port = port,
        };
        auto* state = static_cast<Handle*>(handle);
        std::scoped_lock lock(state->mutex);
        return state->graph.upsert_edge(std::move(edge)) ? 0 : 3;
    } catch (...) {
        return 2;
    }
}

extern "C" int ithute_cluster_reachable(
    void* handle,
    const char* source,
    const char* target
) {
    if (handle == nullptr || source == nullptr || target == nullptr) {
        return -1;
    }
    try {
        auto* state = static_cast<Handle*>(handle);
        std::scoped_lock lock(state->mutex);
        return state->graph.reachable(source, target) ? 1 : 0;
    } catch (...) {
        return -2;
    }
}

extern "C" int ithute_cluster_summary_read(
    void* handle,
    struct ithute_cluster_summary* out
) {
    if (handle == nullptr || out == nullptr) {
        return 1;
    }
    try {
        auto* state = static_cast<Handle*>(handle);
        std::scoped_lock lock(state->mutex);
        const auto summary = state->graph.summary();
        *out = ithute_cluster_summary{
            .nodes = summary.nodes,
            .edges = summary.edges,
            .online_nodes = summary.online_nodes,
            .healthy_nodes = summary.healthy_nodes,
            .memory_total_bytes = summary.memory_total_bytes,
            .memory_used_bytes = summary.memory_used_bytes,
            .storage_total_bytes = summary.storage_total_bytes,
            .storage_used_bytes = summary.storage_used_bytes,
        };
        return 0;
    } catch (...) {
        return 2;
    }
}

extern "C" int ithute_cluster_rank_candidates(
    const char* const* keys,
    const double* scores,
    const int* eligible,
    std::size_t count,
    std::size_t* out_indices,
    std::size_t out_capacity
) {
    if (count == 0) {
        return 0;
    }
    if (keys == nullptr || scores == nullptr || eligible == nullptr || out_indices == nullptr || out_capacity < count) {
        return 1;
    }

    try {
        std::vector<PlacementCandidate> candidates;
        candidates.reserve(count);
        for (std::size_t index = 0; index < count; ++index) {
            candidates.push_back(PlacementCandidate{
                .key = safe_string(keys[index]),
                .score = scores[index],
                .eligible = eligible[index] != 0,
                .original_index = index,
            });
        }

        const auto ranked = rank_placement_candidates(std::move(candidates));
        for (std::size_t index = 0; index < ranked.size(); ++index) {
            out_indices[index] = ranked[index];
        }
        return 0;
    } catch (...) {
        return 2;
    }
}
