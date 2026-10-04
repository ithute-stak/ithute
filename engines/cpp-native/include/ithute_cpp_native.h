#pragma once
#include <cstddef>
#include <cstdint>

extern "C" std::uint64_t ithute_cpp_fnv1a64(const std::uint8_t* data, std::size_t len);
