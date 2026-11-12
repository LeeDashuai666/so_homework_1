#include "runtime.h"
extern "C" std::uint64_t cmov_batch_v1(const void *Context, const Slice *B,
                                       const Slice *E, Counters *Out) {
  return cmov_plain_v1(Context, B, E, Out);
}
