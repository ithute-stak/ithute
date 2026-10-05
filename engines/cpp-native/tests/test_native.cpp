#include "../include/ithute_cpp_native.h"
#include <cassert>
#include <cstdint>

int main() {
    const std::uint8_t value[] = {'i','t','h','u','t','e'};
    const auto first = ithute_cpp_fnv1a64(value, sizeof(value));
    const auto second = ithute_cpp_fnv1a64(value, sizeof(value));
    assert(first != 0);
    assert(first == second);

    const std::uint8_t payload[] = {'A', 0x00, 0x01, 0x09, 0x0A, 0x0D, 0x80, 0xFF};
    ithute_cpp_blob_profile profile{};
    assert(ithute_cpp_blob_profile_scan(payload, sizeof(payload), &profile) == 0);
    assert(profile.bytes == sizeof(payload));
    assert(profile.nul_bytes == 1);
    assert(profile.control_bytes == 2);
    assert(profile.high_bytes == 2);
    assert(profile.fnv1a64 == ithute_cpp_fnv1a64(payload, sizeof(payload)));

    assert(ithute_cpp_blob_profile_scan(nullptr, 1, &profile) == 1);
    assert(ithute_cpp_blob_profile_scan(nullptr, 0, &profile) == 0);
    return 0;
}
