#pragma once

#include <cstddef>
#include <vector>

namespace ithute::cluster {

struct PartitionSummary {
    std::size_t components{0};
    std::vector<std::size_t> component_by_node;
};

[[nodiscard]] PartitionSummary network_partitions(
    std::size_t node_count,
    const std::vector<std::pair<std::size_t, std::size_t>>& undirected_links
);

}  // namespace ithute::cluster
