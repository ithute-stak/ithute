#pragma once

#include <cstddef>
#include <string>
#include <vector>

namespace ithute::cluster {

struct PlacementCandidate {
    std::string key;
    double score{0.0};
    bool eligible{false};
    std::size_t original_index{0};
};

[[nodiscard]] std::vector<std::size_t> rank_placement_candidates(
    std::vector<PlacementCandidate> candidates
);

}  // namespace ithute::cluster
