// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#include "cmov.h"

namespace bolt_cmov {
extern "C" uint64_t __bolt_cmov_adapt_v1(
    const void *Context, const Slice *Begin, const Slice *End, Counters *Out,
    Kernel Original, Kernel Branch) {
  Counters C{};
  const Slice *Next = Begin;
  uint64_t Sum = 0;
  bool Eligible = Begin != End && size_t(End - Begin) >= MinimumBatches;
  if (Eligible)
    for (const Slice *S = Begin; S != End; ++S)
      if (S->begin == S->end || size_t(S->end - S->begin) != RequiredQueries) {
        Eligible = false;
        break;
      }
  if (Eligible)
    Sum = __bolt_cmov_observe_v1(Context, &Next, End, &C, Original, Branch);
  else {
    C.short_bypass = 1;
    C.fallback_batches = Begin == End ? 0 : End - Begin;
  }
  // The observation frame has returned before this common fallback loop.
  // Every input batch is consumed exactly once, even after a clock failure.
  for (; Next != End; ++Next)
    Sum += Original(Context, Next->begin, Next->end);
  if (Out)
    *Out = C;
  return Sum;
}
}
