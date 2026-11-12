#pragma once
#include "cmov_abi.h"
#include <cstdint>
#include <vector>
using Values = std::vector<std::uint64_t>;
using Slice = bolt_cmov::Slice;
using Counters = bolt_cmov::Counters;
extern "C" std::uint64_t cmov_kernel_v1(const void *, const std::uint64_t *, const std::uint64_t *);
extern "C" std::uint64_t cmov_plain_v1(const void *, const Slice *, const Slice *, Counters *);
extern "C" std::uint64_t cmov_batch_v1(const void *, const Slice *, const Slice *, Counters *);
inline std::uint64_t run_dispatch(const Values &V, const Slice *B, const Slice *E,
                                  bool Enabled, Counters *Out) {
  // A benchmark control only. The input's two entries BOTH run the original
  // driver. BOLT, not this source, supplies any adaptation or branch clone.
  return Enabled ? cmov_batch_v1(&V, B, E, Out) : cmov_plain_v1(&V, B, E, Out);
}
