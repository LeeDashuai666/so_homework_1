#include "runtime.h"
extern "C" std::uint64_t run_plain(const Values &v, const Slice *b, const Slice *e) {
  std::uint64_t sum = 0;
  for (; b != e; ++b) sum += lookup_cmov(v, b->begin, b->end);
  return sum;
}
