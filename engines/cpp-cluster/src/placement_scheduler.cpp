#include "placement_scheduler.hpp"

#include <cmath>
#include <limits>
#include <queue>
#include <utility>
#include <vector>

namespace ithute::cluster {
namespace {

double normalized_score(double value) {
    return std::isfinite(value) ? value : std::numeric_limits<double>::infinity();
}

struct CandidatePriority {
    bool operator()(const PlacementCandidate& left, const PlacementCandidate& right) const {
        if (left.eligible != right.eligible) {
            return !left.eligible && right.eligible;
        }
        const double left_score = normalized_score(left.score);
        const double right_score = normalized_score(right.score);
        if (left_score != right_score) {
            return left_score > right_score;
        }
        if (left.key != right.key) {
            return left.key > right.key;
        }
        return left.original_index > right.original_index;
    }
};

}  // namespace

std::vector<std::size_t> rank_placement_candidates(
    std::vector<PlacementCandidate> candidates
) {
    std::priority_queue<
        PlacementCandidate,
        std::vector<PlacementCandidate>,
        CandidatePriority
    > queue;

    for (auto& candidate : candidates) {
        queue.push(std::move(candidate));
    }

    std::vector<std::size_t> ranked;
    ranked.reserve(queue.size());
    while (!queue.empty()) {
        ranked.push_back(queue.top().original_index);
        queue.pop();
    }
    return ranked;
}

}  // namespace ithute::cluster
