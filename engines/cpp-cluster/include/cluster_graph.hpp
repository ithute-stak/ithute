#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace ithute::cluster {

using NodeId = std::string;

enum class NodeStatus {
    Unknown,
    Online,
    Offline,
    Maintenance,
};

enum class Relation {
    CommunicatesWith,
    Hosts,
    DependsOn,
    BacksUpTo,
    ReplicatesTo,
};

struct ResourceState {
    double cpu_used_percent{0.0};
    std::uint64_t memory_total_bytes{0};
    std::uint64_t memory_used_bytes{0};
    std::uint64_t storage_total_bytes{0};
    std::uint64_t storage_used_bytes{0};
};

struct Node {
    NodeId id;
    std::string name;
    std::string hostname;
    std::string private_ip;
    std::vector<std::string> roles;
    NodeStatus status{NodeStatus::Unknown};
    bool healthy{false};
    ResourceState resources{};
    std::unordered_set<std::string> capabilities;
};

struct Edge {
    NodeId source;
    NodeId target;
    Relation relation{Relation::CommunicatesWith};
    std::string service;
    std::string protocol;
    std::uint16_t port{0};

    bool operator==(const Edge& other) const;
};

struct ClusterSummary {
    std::size_t nodes{0};
    std::size_t edges{0};
    std::size_t online_nodes{0};
    std::size_t healthy_nodes{0};
    std::uint64_t memory_total_bytes{0};
    std::uint64_t memory_used_bytes{0};
    std::uint64_t storage_total_bytes{0};
    std::uint64_t storage_used_bytes{0};
};

class ClusterGraph {
public:
    void upsert_node(Node node);
    bool remove_node(const NodeId& node_id);

    bool upsert_edge(Edge edge);
    bool remove_edge(const Edge& edge);

    [[nodiscard]] const Node* get_node(const NodeId& node_id) const;
    [[nodiscard]] std::vector<const Node*> neighbors(const NodeId& node_id) const;
    [[nodiscard]] bool reachable(const NodeId& source, const NodeId& target) const;
    [[nodiscard]] std::optional<std::vector<NodeId>> dependency_order() const;
    [[nodiscard]] ClusterSummary summary() const;

    [[nodiscard]] std::size_t node_count() const noexcept;
    [[nodiscard]] std::size_t edge_count() const noexcept;

private:
    std::unordered_map<NodeId, Node> nodes_;
    std::unordered_map<NodeId, std::vector<Edge>> adjacency_;
    std::size_t edge_count_{0};
};

}  // namespace ithute::cluster
