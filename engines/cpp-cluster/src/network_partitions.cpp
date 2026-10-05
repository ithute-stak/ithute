#include "network_partitions.hpp"

#include <numeric>

namespace ithute::cluster {
namespace {

class DisjointSet {
public:
    explicit DisjointSet(std::size_t count) : parent_(count), rank_(count, 0) {
        std::iota(parent_.begin(), parent_.end(), 0);
    }

    std::size_t find(std::size_t value) {
        if (parent_[value] != value) {
            parent_[value] = find(parent_[value]);
        }
        return parent_[value];
    }

    void unite(std::size_t left, std::size_t right) {
        left = find(left);
        right = find(right);
        if (left == right) {
            return;
        }
        if (rank_[left] < rank_[right]) {
            parent_[left] = right;
        } else if (rank_[left] > rank_[right]) {
            parent_[right] = left;
        } else {
            parent_[right] = left;
            ++rank_[left];
        }
    }

private:
    std::vector<std::size_t> parent_;
    std::vector<unsigned int> rank_;
};

}  // namespace

PartitionSummary network_partitions(
    std::size_t node_count,
    const std::vector<std::pair<std::size_t, std::size_t>>& undirected_links
) {
    DisjointSet sets(node_count);
    for (const auto& [left, right] : undirected_links) {
        if (left >= node_count || right >= node_count) {
            continue;
        }
        sets.unite(left, right);
    }

    std::vector<std::size_t> root_to_component(node_count, node_count);
    std::vector<std::size_t> component_by_node(node_count, node_count);
    std::size_t components = 0;

    for (std::size_t node = 0; node < node_count; ++node) {
        const auto root = sets.find(node);
        if (root_to_component[root] == node_count) {
            root_to_component[root] = components++;
        }
        component_by_node[node] = root_to_component[root];
    }

    return PartitionSummary{
        .components = components,
        .component_by_node = std::move(component_by_node),
    };
}

}  // namespace ithute::cluster
