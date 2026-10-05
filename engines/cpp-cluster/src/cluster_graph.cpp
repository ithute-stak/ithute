#include "cluster_graph.hpp"

#include <algorithm>
#include <queue>
#include <utility>

namespace ithute::cluster {

bool Edge::operator==(const Edge& other) const {
    return source == other.source
        && target == other.target
        && relation == other.relation
        && service == other.service
        && protocol == other.protocol
        && port == other.port;
}

void ClusterGraph::upsert_node(Node node) {
    if (node.id.empty()) {
        return;
    }
    const auto id = node.id;
    nodes_.insert_or_assign(id, std::move(node));
    adjacency_.try_emplace(id);
}

bool ClusterGraph::remove_node(const NodeId& node_id) {
    if (nodes_.erase(node_id) == 0) {
        return false;
    }

    if (const auto own = adjacency_.find(node_id); own != adjacency_.end()) {
        edge_count_ -= own->second.size();
        adjacency_.erase(own);
    }

    for (auto& [source, edges] : adjacency_) {
        (void)source;
        const auto before = edges.size();
        std::erase_if(edges, [&](const Edge& edge) {
            return edge.target == node_id;
        });
        edge_count_ -= before - edges.size();
    }
    return true;
}

bool ClusterGraph::upsert_edge(Edge edge) {
    if (edge.source.empty() || edge.target.empty() || edge.source == edge.target) {
        return false;
    }
    if (!nodes_.contains(edge.source) || !nodes_.contains(edge.target)) {
        return false;
    }

    auto& edges = adjacency_[edge.source];
    const auto existing = std::find(edges.begin(), edges.end(), edge);
    if (existing != edges.end()) {
        return true;
    }

    edges.push_back(std::move(edge));
    ++edge_count_;
    return true;
}

bool ClusterGraph::remove_edge(const Edge& edge) {
    const auto found = adjacency_.find(edge.source);
    if (found == adjacency_.end()) {
        return false;
    }

    auto& edges = found->second;
    const auto before = edges.size();
    std::erase(edges, edge);
    const auto removed = before - edges.size();
    edge_count_ -= removed;
    return removed != 0;
}

const Node* ClusterGraph::get_node(const NodeId& node_id) const {
    const auto found = nodes_.find(node_id);
    return found == nodes_.end() ? nullptr : &found->second;
}

std::vector<const Node*> ClusterGraph::neighbors(const NodeId& node_id) const {
    std::vector<const Node*> result;
    const auto found = adjacency_.find(node_id);
    if (found == adjacency_.end()) {
        return result;
    }

    result.reserve(found->second.size());
    std::unordered_set<NodeId> seen;
    for (const auto& edge : found->second) {
        if (!seen.insert(edge.target).second) {
            continue;
        }
        if (const auto* node = get_node(edge.target); node != nullptr) {
            result.push_back(node);
        }
    }
    return result;
}

bool ClusterGraph::reachable(const NodeId& source, const NodeId& target) const {
    if (!nodes_.contains(source) || !nodes_.contains(target)) {
        return false;
    }
    if (source == target) {
        return true;
    }

    std::queue<NodeId> pending;
    std::unordered_set<NodeId> visited;
    pending.push(source);
    visited.insert(source);

    while (!pending.empty()) {
        auto current = std::move(pending.front());
        pending.pop();

        const auto found = adjacency_.find(current);
        if (found == adjacency_.end()) {
            continue;
        }

        for (const auto& edge : found->second) {
            if (edge.target == target) {
                return true;
            }
            if (nodes_.contains(edge.target) && visited.insert(edge.target).second) {
                pending.push(edge.target);
            }
        }
    }
    return false;
}

ClusterSummary ClusterGraph::summary() const {
    ClusterSummary result{};
    result.nodes = nodes_.size();
    result.edges = edge_count_;

    for (const auto& [id, node] : nodes_) {
        (void)id;
        if (node.status == NodeStatus::Online) {
            ++result.online_nodes;
        }
        if (node.healthy) {
            ++result.healthy_nodes;
        }
        result.memory_total_bytes += node.resources.memory_total_bytes;
        result.memory_used_bytes += node.resources.memory_used_bytes;
        result.storage_total_bytes += node.resources.storage_total_bytes;
        result.storage_used_bytes += node.resources.storage_used_bytes;
    }
    return result;
}

std::size_t ClusterGraph::node_count() const noexcept {
    return nodes_.size();
}

std::size_t ClusterGraph::edge_count() const noexcept {
    return edge_count_;
}

}  // namespace ithute::cluster
