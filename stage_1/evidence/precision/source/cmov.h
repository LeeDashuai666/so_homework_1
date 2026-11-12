// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#pragma once
#include <stddef.h>
#include <stdint.h>

// Cooperative Linux x86-64 SysV ABI v1. Context is opaque to the runtime.
// Kernel: checksum(ctx, queries_begin, queries_end), preserving input order.
// Entry: checksum(ctx, slices_begin, slices_end, optional_counters).
// Kernels must not throw; all ranges must be valid as in the original driver.
namespace bolt_cmov {
struct Slice { const uint64_t *begin; const uint64_t *end; };
struct Counters {
  uint64_t trial_batches, active_batches, controls, clock_reads;
  uint64_t fallback_batches, suspicion_controls;
  unsigned entered, rejection, short_bypass;
};
using Kernel = uint64_t (*)(const void *, const uint64_t *, const uint64_t *);
constexpr size_t MinimumBatches = 512, RequiredQueries = 4096;
extern "C" uint64_t __bolt_cmov_observe_v1(
    const void *, const Slice **, const Slice *, Counters *, Kernel, Kernel);
extern "C" uint64_t __bolt_cmov_adapt_v1(
    const void *, const Slice *, const Slice *, Counters *, Kernel, Kernel);
}
