#include "runtime.h"
#include <algorithm>
#ifndef LOOKUP_NAME
#define LOOKUP_NAME lookup_cmov
#endif
extern "C" std::uint64_t LOOKUP_NAME(const Values &v, const std::uint64_t *b, const std::uint64_t *e) {
  std::uint64_t sum = 0;
  for (; b != e; ++b) sum += std::lower_bound(v.begin(), v.end(), *b) - v.begin();
  return sum;
}
