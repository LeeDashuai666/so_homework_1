#include "search_lookup.h"
#include <algorithm>

std::uint64_t search_all(const std::vector<std::uint64_t> &values,
                         const std::vector<std::uint64_t> &queries, unsigned rounds) {
  std::uint64_t checksum = 0;
  for (unsigned r = 0; r < rounds; ++r)
    for (auto query : queries) {
      const auto found = std::lower_bound(values.begin(), values.end(), query);
      checksum += found - values.begin();
    }
  return checksum;
}
