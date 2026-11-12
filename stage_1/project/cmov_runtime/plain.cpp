#include "runtime.h"
extern "C" std::uint64_t cmov_plain_v1(const void *Context, const Slice *B,
                                       const Slice *E, Counters *Out) {
  if (Out) *Out = {};
  std::uint64_t Sum = 0;
  for (; B != E; ++B)
    Sum += cmov_kernel_v1(Context, B->begin, B->end);
  return Sum;
}
