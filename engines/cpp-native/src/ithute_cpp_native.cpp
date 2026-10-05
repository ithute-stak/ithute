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

extern "C" int ithute_cpp_blob_profile_scan(
    const std::uint8_t* data,
    std::size_t len,
    ithute_cpp_blob_profile* out
) {
    if (out == nullptr || (data == nullptr && len != 0)) {
        return 1;
    }

    constexpr std::uint64_t offset = 14695981039346656037ULL;
    constexpr std::uint64_t prime = 1099511628211ULL;

    ithute_cpp_blob_profile result{};
    result.bytes = len;
    result.fnv1a64 = offset;

    for (std::size_t i = 0; i < len; ++i) {
        const auto value = data[i];
        if (value == 0) {
            ++result.nul_bytes;
        }
        if (value < 32 && value != 9 && value != 10 && value != 13) {
            ++result.control_bytes;
        }
        if (value >= 128) {
            ++result.high_bytes;
        }
        result.fnv1a64 ^= static_cast<std::uint64_t>(value);
        result.fnv1a64 *= prime;
    }

    *out = result;
    return 0;
}

extern "C" std::uint32_t ithute_cpp_route_shard(
    const std::uint8_t* key,
    std::size_t len,
    std::uint32_t shard_count
) {
    if (shard_count == 0 || (key == nullptr && len != 0)) {
        return 0;
    }
    const auto hash = ithute_cpp_fnv1a64(key, len);
    return static_cast<std::uint32_t>(hash % shard_count);
}
