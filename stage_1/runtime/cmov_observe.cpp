// Part of the LLVM Project, under the Apache License v2.0 with LLVM Exceptions.
// SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception
#include "cmov.h"

namespace bolt_cmov {
#ifdef BOLT_CMOV_TEST_CLOCK
extern bool test_clock(uint64_t &);
#endif
static bool clock_read(uint64_t &NS, Counters &C) {
  ++C.clock_reads;
#ifdef BOLT_CMOV_TEST_CLOCK
  return test_clock(NS);
#elif defined(__x86_64__) && defined(__linux__)
  struct Stamp { long seconds, nanoseconds; } T{};
  long Status;
  // CLOCK_THREAD_CPUTIME_ID; Linux x86-64 clock_gettime syscall. No glibc,
  // globals, writable shared state, environment variables or loader hooks.
  asm volatile("syscall" : "=a"(Status)
               : "a"(228L), "D"(3L), "S"(&T)
               : "rcx", "r11", "memory", "cc");
  if (Status || T.seconds < 0 || T.nanoseconds < 0 ||
      T.nanoseconds >= 1000000000L ||
      uint64_t(T.seconds) > (UINT64_MAX - uint64_t(T.nanoseconds))/1000000000ULL)
    return false;
  NS = uint64_t(T.seconds)*1000000000ULL + uint64_t(T.nanoseconds);
  return true;
#else
  return false;
#endif
}

static bool above_ratio(uint64_t A, uint64_t B, unsigned Percent) {
  return __uint128_t(A)*100 >= __uint128_t(B)*Percent;
}

extern "C" uint64_t __bolt_cmov_observe_v1(
    const void *Context, const Slice **Next, const Slice *End, Counters *Out,
    Kernel Original, Kernel Branch) {
  const Slice *B = *Next;
  Counters C{};
  uint64_t Sum = 0, Reference = 0, Recent[3] = {};
  unsigned Cursor = 0;
  auto Fallback = [&](unsigned Reason) {
    C.rejection = Reason;
    C.fallback_batches = End-B;
    *Next = B;
    *Out = C;
    return Sum;
  };
  auto Measured = [&](Kernel K, uint64_t &Cost, unsigned Count = 1) {
    uint64_t Start, Stop;
    if (!clock_read(Start, C))
      return false;
    for (unsigned I=0; I<Count; ++I) {
      Sum += K(Context, B->begin, B->end);
      ++B;
    }
    if (!clock_read(Stop, C) || Stop <= Start)
      return false;
    Cost = (Stop-Start)/Count;
    return true;
  };
  for (unsigned Pair = 0; Pair != 3; ++Pair) {
    uint64_t Trial;
    ++C.controls;
    if (!Measured(Original, Reference))
      return Fallback(1);
    ++C.trial_batches;
    if (!Measured(Branch, Trial))
      return Fallback(1);
    if (above_ratio(Trial, Reference, 90))
      return Fallback(2);
    Recent[Pair] = Trial;
  }
  C.entered = 1;
  unsigned SinceControl = 0;
  while (B != End) {
    if (SinceControl == 16) {
      ++C.controls;
      if (!Measured(Original, Reference))
        return Fallback(1);
      SinceControl = 0;
      continue;
    }
    uint64_t Cost;
    const unsigned Count = (End-B >= 2 && SinceControl <= 14) ? 2 : 1;
    C.active_batches += Count;
    if (!Measured(Branch, Cost, Count))
      return Fallback(1);
    SinceControl += Count;
    Recent[Cursor] = Cost;
    Cursor = (Cursor+1)%3;
    const uint64_t X = Recent[0], Y = Recent[1], Z = Recent[2];
    const uint64_t Median = X < Y ? (Y < Z ? Y : (X < Z ? Z : X))
                                 : (X < Z ? X : (Y < Z ? Z : Y));
    if (above_ratio(Median, Reference, 95) && B != End) {
      ++C.controls;
      ++C.suspicion_controls;
      if (!Measured(Original, Reference))
        return Fallback(1);
      SinceControl = 0;
      if (above_ratio(Median, Reference, 95)) {
        // Confirm an apparent loss against three CURRENT original batches.
        // Each batch is real ordered work; do not execute any new B here.
        // At the end of the call there is no useful recovery window.
        if (size_t(End-B) < 2)
          return Fallback(3);
        uint64_t A1, A2;
        ++C.controls;
        if (!Measured(Original, A1)) return Fallback(1);
        ++C.controls;
        if (!Measured(Original, A2)) return Fallback(1);
        const uint64_t A0 = Reference;
        Reference = A0 < A1 ? (A1 < A2 ? A1 : (A0 < A2 ? A2 : A0))
                            : (A0 < A2 ? A0 : (A1 < A2 ? A2 : A1));
        if (above_ratio(Median, Reference, 95)) return Fallback(3);
      }
    }
  }
  *Next = B;
  *Out = C;
  return Sum;
}
}
