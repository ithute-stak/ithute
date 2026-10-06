#pragma once

#include <cstddef>
#include <optional>
#include <string>
#include <vector>

namespace ithute::cluster {

struct WeightedEdge {
    std::size_t source_index;
    std::size_t target_index;
    double weight;
};

struct ShortestPathResult {
    double total_weight{0.0};
    std::vector<std::size_t> node_indices;
};

[[nodiscard]] std::optional<ShortestPathResult> shortest_weighted_path(
    std::size_t node_count,
    const std::vector<WeightedEdge>& edges,
    std::size_t source_index,
    std::size_t target_index
);

}  // namespace ithute::cluster
