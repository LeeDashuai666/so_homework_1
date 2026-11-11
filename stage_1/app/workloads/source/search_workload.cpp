// Normal standard-library lower_bound benchmark, built without opt-out flags.
#include "search_lookup.h"
#include <algorithm>
#include <chrono>
#include <iostream>
#include <random>
#include <string>

int main(int argc, char **argv) {
  const std::size_t count = argc > 1 ? std::stoull(argv[1]) : 4096;
  const unsigned rounds = argc > 2 ? std::stoul(argv[2]) : 1000;
  const unsigned hot = argc > 3 ? std::stoul(argv[3]) : 95;
  const unsigned seed = argc > 4 ? std::stoul(argv[4]) : 71;
  const std::string mode = argc > 5 ? argv[5] : "low";
  if (!count || hot > 100) return 2;
  std::vector<std::uint64_t> values(count), queries(4096);
  for (std::size_t i = 0; i < count; ++i) values[i] = 2*i;
  std::mt19937_64 random(seed);
  for (auto &q : queries) {
    q = random() % (2*count);
    if (random()%100 < hot) q = mode == "high" ? 2*count : 0;
  }
  if (mode == "sorted") std::sort(queries.begin(), queries.end());
  const auto begin = std::chrono::steady_clock::now();
  const auto checksum = search_all(values, queries, rounds);
  const auto elapsed = std::chrono::steady_clock::now() - begin;
  std::cout << "{\"elapsed_ns\":"
            << std::chrono::duration_cast<std::chrono::nanoseconds>(elapsed).count()
            << ",\"checksum\":" << checksum << "}\n";
}
