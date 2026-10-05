#include "cluster_graph.hpp"

#include <cassert>
#include <cstdint>
#include <string>

using ithute::cluster::ClusterGraph;
using ithute::cluster::Edge;
using ithute::cluster::Node;
using ithute::cluster::NodeStatus;
using ithute::cluster::Relation;
using ithute::cluster::ResourceState;

static Node node(
    std::string id,
    std::string name,
    std::string ip,
    NodeStatus status,
    bool healthy,
    std::uint64_t memory_total,
    std::uint64_t memory_used,
    std::uint64_t storage_total,
    std::uint64_t storage_used
) {
    Node value{};
    value.id = std::move(id);
    value.name = std::move(name);
    value.private_ip = std::move(ip);
    value.status = status;
    value.healthy = healthy;
    value.resources = ResourceState{
        .cpu_used_percent = healthy ? 20.0 : 90.0,
        .memory_total_bytes = memory_total,
        .memory_used_bytes = memory_used,
        .storage_total_bytes = storage_total,
        .storage_used_bytes = storage_used,
    };
    return value;
}

int main() {
    ClusterGraph graph;

    graph.upsert_node(node("vps-a", "Application", "10.70.0.2", NodeStatus::Online, true, 8, 3, 100, 40));
    graph.upsert_node(node("vps-b", "Database", "10.70.0.3", NodeStatus::Online, true, 16, 8, 200, 120));
    graph.upsert_node(node("vps-c", "Backup", "10.70.0.4", NodeStatus::Offline, false, 32, 4, 500, 100));

    assert(graph.node_count() == 3);
    assert(graph.get_node("vps-b") != nullptr);
    assert(graph.get_node("missing") == nullptr);

    assert(graph.upsert_edge(Edge{
        .source = "vps-a",
        .target = "vps-b",
        .relation = Relation::DependsOn,
        .service = "postgresql",
        .protocol = "tcp",
        .port = 5432,
    }));
    assert(graph.upsert_edge(Edge{
        .source = "vps-b",
        .target = "vps-c",
        .relation = Relation::BacksUpTo,
        .service = "backup",
        .protocol = "tcp",
        .port = 443,
    }));

    assert(graph.edge_count() == 2);
    assert(graph.neighbors("vps-a").size() == 1);
    assert(graph.neighbors("vps-a")[0]->id == "vps-b");
    assert(graph.reachable("vps-a", "vps-c"));
    assert(!graph.reachable("vps-c", "vps-a"));

    const auto summary = graph.summary();
    assert(summary.nodes == 3);
    assert(summary.edges == 2);
    assert(summary.online_nodes == 2);
    assert(summary.healthy_nodes == 2);
    assert(summary.memory_total_bytes == 56);
    assert(summary.memory_used_bytes == 15);
    assert(summary.storage_total_bytes == 800);
    assert(summary.storage_used_bytes == 260);

    graph.upsert_node(node("vps-b", "Database Updated", "10.70.0.3", NodeStatus::Maintenance, false, 16, 9, 200, 125));
    assert(graph.node_count() == 3);
    assert(graph.get_node("vps-b")->name == "Database Updated");

    assert(graph.remove_node("vps-b"));
    assert(graph.node_count() == 2);
    assert(graph.edge_count() == 0);
    assert(!graph.reachable("vps-a", "vps-c"));

    assert(!graph.remove_node("missing"));
    return 0;
}
