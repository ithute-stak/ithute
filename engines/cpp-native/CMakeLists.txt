cmake_minimum_required(VERSION 3.20)
project(ithute_cpp_native LANGUAGES CXX)

add_library(ithute_cpp_native SHARED src/ithute_cpp_native.cpp)
target_compile_features(ithute_cpp_native PRIVATE cxx_std_20)
target_compile_options(ithute_cpp_native PRIVATE -Wall -Wextra -Wpedantic -Werror)
set_target_properties(ithute_cpp_native PROPERTIES OUTPUT_NAME "ithute_cpp_native")

add_executable(ithute_cpp_native_test tests/test_native.cpp)
target_link_libraries(ithute_cpp_native_test PRIVATE ithute_cpp_native)
enable_testing()
add_test(NAME ithute_cpp_native_test COMMAND ithute_cpp_native_test)
