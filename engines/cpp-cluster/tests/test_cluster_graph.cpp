#include "cluster_graph.hpp"
#include "ithute_cluster_c.h"
#include "placement_scheduler.hpp"
#include "weighted_network.hpp"
#include "network_partitions.hpp"

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

    void* handle = ithute_cluster_create();
    assert(handle != nullptr);
    assert(ithute_cluster_upsert_node(handle, "a", "A", "10.70.0.2", 1, 1, 10.0, 8, 2, 100, 10) == 0);
    assert(ithute_cluster_upsert_node(handle, "b", "B", "10.70.0.3", 1, 1, 20.0, 16, 4, 200, 20) == 0);
    assert(ithute_cluster_upsert_edge(handle, "a", "b", 2, "postgresql", "tcp", 5432) == 0);
    assert(ithute_cluster_reachable(handle, "a", "b") == 1);
    assert(ithute_cluster_reachable(handle, "b", "a") == 0);

    ithute_cluster_summary native_summary{};
    assert(ithute_cluster_summary_read(handle, &native_summary) == 0);
    assert(native_summary.nodes == 2);
    assert(native_summary.edges == 1);
    assert(native_summary.online_nodes == 2);
    assert(native_summary.healthy_nodes == 2);
    assert(native_summary.memory_total_bytes == 24);
    ithute_cluster_destroy(handle);

    const char* placement_keys[] = {"node-c", "node-a", "node-b", "node-z"};
    const double placement_scores[] = {20.0, 10.0, 10.0, 1.0};
    const int placement_eligible[] = {1, 1, 1, 0};
    std::size_t placement_order[4] = {};
    assert(
        ithute_cluster_rank_candidates(
            placement_keys,
            placement_scores,
            placement_eligible,
            4,
            placement_order,
            4
        ) == 0
    );
    assert(placement_order[0] == 1);
    assert(placement_order[1] == 2);
    assert(placement_order[2] == 0);
    assert(placement_order[3] == 3);

    ClusterGraph dependency_graph;
    dependency_graph.upsert_node(node("frontend", "Frontend", "", NodeStatus::Online, true, 1, 0, 1, 0));
    dependency_graph.upsert_node(node("backend", "Backend", "", NodeStatus::Online, true, 1, 0, 1, 0));
    dependency_graph.upsert_node(node("postgres", "Postgres", "", NodeStatus::Online, true, 1, 0, 1, 0));
    assert(dependency_graph.upsert_edge(Edge{
        .source = "frontend",
        .target = "backend",
        .relation = Relation::DependsOn,
    }));
    assert(dependency_graph.upsert_edge(Edge{
        .source = "backend",
        .target = "postgres",
        .relation = Relation::DependsOn,
    }));
    const auto dependency_order = dependency_graph.dependency_order();
    assert(dependency_order.has_value());
    assert((*dependency_order)[0] == "postgres");
    assert((*dependency_order)[1] == "backend");
    assert((*dependency_order)[2] == "frontend");

    assert(dependency_graph.upsert_edge(Edge{
        .source = "postgres",
        .target = "frontend",
        .relation = Relation::DependsOn,
    }));
    assert(!dependency_graph.dependency_order().has_value());

    const char* dag_nodes[] = {"frontend", "backend", "postgres"};
    const char* dag_dependents[] = {"frontend", "backend"};
    const char* dag_dependencies[] = {"backend", "postgres"};
    std::size_t dag_order[3] = {};
    assert(
        ithute_cluster_dependency_order(
            dag_nodes,
            3,
            dag_dependents,
            dag_dependencies,
            2,
            dag_order,
            3
        ) == 0
    );
    assert(dag_order[0] == 2);
    assert(dag_order[1] == 1);
    assert(dag_order[2] == 0);

    const char* cycle_dependents[] = {"frontend", "backend", "postgres"};
    const char* cycle_dependencies[] = {"backend", "postgres", "frontend"};
    assert(
        ithute_cluster_dependency_order(
            dag_nodes,
            3,
            cycle_dependents,
            cycle_dependencies,
            3,
            dag_order,
            3
        ) == 3
    );

    const std::size_t edge_sources[] = {0, 0, 1, 2};
    const std::size_t edge_targets[] = {1, 2, 3, 3};
    const double edge_weights[] = {2.0, 10.0, 2.0, 1.0};
    std::size_t shortest_order[4] = {};
    std::size_t shortest_count = 0;
    double shortest_weight = 0.0;
    assert(ithute_cluster_shortest_path(
        4, edge_sources, edge_targets, edge_weights, 4, 0, 3,
        shortest_order, 4, &shortest_count, &shortest_weight
    ) == 0);
    assert(shortest_count == 3);
    assert(shortest_order[0] == 0);
    assert(shortest_order[1] == 1);
    assert(shortest_order[2] == 3);
    assert(shortest_weight == 4.0);

    const std::size_t partition_sources[] = {0, 1, 3};
    const std::size_t partition_targets[] = {1, 2, 4};
    std::size_t component_ids[5] = {};
    std::size_t component_count = 0;
    assert(ithute_cluster_network_partitions(
        5, partition_sources, partition_targets, 3,
        component_ids, 5, &component_count
    ) == 0);
    assert(component_count == 2);
    assert(component_ids[0] == component_ids[1]);
    assert(component_ids[1] == component_ids[2]);
    assert(component_ids[3] == component_ids[4]);
    assert(component_ids[0] != component_ids[3]);

    return 0;
}
