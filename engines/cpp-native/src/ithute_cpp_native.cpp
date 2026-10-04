#include "../include/ithute_cpp_native.h"

extern "C" std::uint64_t ithute_cpp_fnv1a64(const std::uint8_t* data, std::size_t len) {
    constexpr std::uint64_t offset = 14695981039346656037ULL;
    constexpr std::uint64_t prime = 1099511628211ULL;
    if (data == nullptr && len != 0) {
        return 0;
    }
    std::uint64_t hash = offset;
    for (std::size_t i = 0; i < len; ++i) {
        hash ^= static_cast<std::uint64_t>(data[i]);
        hash *= prime;
    }
    return hash;
}
