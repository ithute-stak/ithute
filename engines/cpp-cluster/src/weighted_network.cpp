#include "weighted_network.hpp"

#include <cmath>
#include <limits>
#include <queue>
#include <utility>

namespace ithute::cluster {

std::optional<ShortestPathResult> shortest_weighted_path(
    std::size_t node_count,
    const std::vector<WeightedEdge>& edges,
    std::size_t source_index,
    std::size_t target_index
) {
    if (node_count == 0 || source_index >= node_count || target_index >= node_count) {
        return std::nullopt;
    }
    if (source_index == target_index) {
        return ShortestPathResult{.total_weight = 0.0, .node_indices = {source_index}};
    }

    std::vector<std::vector<std::pair<std::size_t, double>>> adjacency(node_count);
    for (const auto& edge : edges) {
        if (edge.source_index >= node_count || edge.target_index >= node_count) {
            return std::nullopt;
        }
        if (!std::isfinite(edge.weight) || edge.weight < 0.0) {
            return std::nullopt;
        }
        adjacency[edge.source_index].push_back({edge.target_index, edge.weight});
    }

    const auto infinity = std::numeric_limits<double>::infinity();
    std::vector<double> distance(node_count, infinity);
    std::vector<std::size_t> previous(node_count, node_count);
    using QueueItem = std::pair<double, std::size_t>;
    std::priority_queue<QueueItem, std::vector<QueueItem>, std::greater<>> pending;

    distance[source_index] = 0.0;
    pending.push({0.0, source_index});

    while (!pending.empty()) {
        const auto [current_distance, current] = pending.top();
        pending.pop();
        if (current_distance != distance[current]) {
            continue;
        }
        if (current == target_index) {
            break;
        }

        for (const auto& [neighbor, weight] : adjacency[current]) {
            const auto candidate = current_distance + weight;
            if (candidate < distance[neighbor]) {
                distance[neighbor] = candidate;
                previous[neighbor] = current;
                pending.push({candidate, neighbor});
            }
        }
    }

    if (!std::isfinite(distance[target_index])) {
        return std::nullopt;
    }

    std::vector<std::size_t> reversed;
    for (std::size_t current = target_index; current != node_count; current = previous[current]) {
        reversed.push_back(current);
        if (current == source_index) {
            break;
        }
    }
    if (reversed.empty() || reversed.back() != source_index) {
        return std::nullopt;
    }

    std::vector<std::size_t> path(reversed.rbegin(), reversed.rend());
    return ShortestPathResult{.total_weight = distance[target_index], .node_indices = std::move(path)};
}

}  // namespace ithute::cluster
