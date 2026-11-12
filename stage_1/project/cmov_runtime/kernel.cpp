#include "runtime.h"
#include <algorithm>
extern "C" std::uint64_t cmov_kernel_v1(const void *Context,
                                        const std::uint64_t *B,
                                        const std::uint64_t *E) {
  const auto &V = *static_cast<const Values *>(Context);
  std::uint64_t Sum = 0;
  for (; B != E; ++B)
    Sum += std::lower_bound(V.begin(), V.end(), *B)-V.begin();
  return Sum;
}
