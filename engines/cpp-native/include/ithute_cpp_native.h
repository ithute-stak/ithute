#pragma once
#include <cstddef>
#include <cstdint>

struct ithute_cpp_blob_profile {
    std::size_t bytes;
    std::size_t nul_bytes;
    std::size_t control_bytes;
    std::size_t high_bytes;
    std::uint64_t fnv1a64;
};

extern "C" std::uint64_t ithute_cpp_fnv1a64(const std::uint8_t* data, std::size_t len);
extern "C" int ithute_cpp_blob_profile_scan(
    const std::uint8_t* data,
    std::size_t len,
    ithute_cpp_blob_profile* out
);

extern "C" std::uint32_t ithute_cpp_route_shard(
    const std::uint8_t* key,
    std::size_t len,
    std::uint32_t shard_count
);
