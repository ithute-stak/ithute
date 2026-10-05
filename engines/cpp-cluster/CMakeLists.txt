cmake_minimum_required(VERSION 3.20)
project(ithute_cpp_cluster LANGUAGES CXX)

add_library(ithute_cpp_cluster
  src/cluster_graph.cpp
)

target_include_directories(ithute_cpp_cluster PUBLIC include)
target_compile_features(ithute_cpp_cluster PUBLIC cxx_std_20)
target_compile_options(ithute_cpp_cluster PRIVATE -Wall -Wextra -Wpedantic -Werror)

add_executable(ithute_cpp_cluster_test
  tests/test_cluster_graph.cpp
)
target_link_libraries(ithute_cpp_cluster_test PRIVATE ithute_cpp_cluster)

enable_testing()
add_test(NAME ithute_cpp_cluster_test COMMAND ithute_cpp_cluster_test)
