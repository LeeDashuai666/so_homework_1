#include "runtime.h"
#include <algorithm>
#include <array>
#include <ctime>

namespace {
bool clock_read(std::uint64_t &ns, Counters &c) {
  timespec stamp{};
  ++c.clock_reads;
  if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &stamp)) return false;
  ns = std::uint64_t(stamp.tv_sec) * 1000000000ULL + stamp.tv_nsec;
  return true;
}
}

extern "C" std::uint64_t inspect_prefix(const Values &v, const Slice **next,
                                       const Slice *e, Counters *out) {
  const Slice *b = *next;
  Counters c;
  std::uint64_t sum = 0, reference = 0;
  // A failed clock, one failed approval pair or one active suspicion is terminal
  // for THIS invocation. There is no periodic probing of rejected workloads.
  auto fallback = [&](unsigned reason) {
    c.rejection = reason;
    c.fallback_batches = e-b;
    *next = b;
    if (out) *out = c;
    return sum;
  };
  auto measured = [&](bool branch, std::uint64_t &ns) {
    std::uint64_t start, stop;
    if (!clock_read(start, c)) return false; // No work consumed on this path.
    sum += branch ? lookup_branch(v, b->begin, b->end)
                  : lookup_cmov(v, b->begin, b->end);
    ++b;
    if (!clock_read(stop, c) || stop <= start) return false;
    ns = stop-start;
    return true;
  };
  // Full batches execute real work once in order. Unlike v2-v4, no microprobe
  // is allowed to dispatch the rest of a batch to the speculative variant.
  std::array<std::uint64_t, 3> recent{};
  unsigned cursor = 0;
  for (unsigned pair = 0; pair < ApprovalPairs; ++pair) {
    std::uint64_t trial;
    ++c.controls;
    if (!measured(false, reference)) return fallback(1);
    ++c.trial_batches;
    if (!measured(true, trial)) return fallback(1);
    if (double(trial) >= EntryRatio * reference) return fallback(2);
    recent[pair] = trial;
  }
  c.entered = 1;
  unsigned since_control = 0;
  while (b != e) {
    if (since_control == ControlPeriod) {
      ++c.controls;
      if (!measured(false, reference)) return fallback(1);
      since_control = 0;
      continue;
    }
    std::uint64_t cost;
    ++c.active_batches;
    if (!measured(true, cost)) return fallback(1);
    ++since_control;
    recent[cursor] = cost; cursor = (cursor+1)%recent.size();
    auto ordered = recent;
    std::sort(ordered.begin(), ordered.end());
    if (double(ordered[1]) >= ExitRatio * reference && b != e) {
      // A historical A reference can become stale. Suspend B immediately and
      // execute one CURRENT A batch before deciding. No new B trials/reentry.
      ++c.controls; ++c.suspicion_controls;
      if (!measured(false, reference)) return fallback(1);
      since_control = 0;
      if (double(ordered[1]) >= ExitRatio * reference) return fallback(3);
    }
  }
  *next = b;
  if (out) *out = c;
  return sum;
}
