#include "../include/ithute_cpp_native.h"
#include <cassert>
#include <cstdint>

int main() {
    const std::uint8_t value[] = {'i','t','h','u','t','e'};
    const auto first = ithute_cpp_fnv1a64(value, sizeof(value));
    const auto second = ithute_cpp_fnv1a64(value, sizeof(value));
    assert(first != 0);
    assert(first == second);
    return 0;
}
