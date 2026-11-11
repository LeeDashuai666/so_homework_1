#pragma once
#include <cstddef>
#include <cstdint>
#include <vector>

using Values = std::vector<std::uint64_t>;
struct Slice { const std::uint64_t *begin, *end; };
struct Counters {
  std::uint64_t trial_batches = 0, active_batches = 0, controls = 0;
  std::uint64_t clock_reads = 0, fallback_batches = 0, suspicion_controls = 0;
  unsigned entered = 0, rejection = 0, short_bypass = 0;
};
extern "C" std::uint64_t lookup_cmov(const Values &, const std::uint64_t *, const std::uint64_t *);
extern "C" std::uint64_t lookup_branch(const Values &, const std::uint64_t *, const std::uint64_t *);
extern "C" std::uint64_t run_plain(const Values &, const Slice *, const Slice *);
extern "C" std::uint64_t run_guarded(const Values &, const Slice *, const Slice *, Counters *);
extern "C" std::uint64_t run_dispatch(const Values &, const Slice *, const Slice *, bool, Counters *);
extern "C" std::uint64_t inspect_prefix(const Values &, const Slice **, const Slice *, Counters *);
// Deliberately narrow cooperative ABI: caller supplies real ordered batches.
// No input labels, phase metadata, assumed distribution or cross-call state.
constexpr std::size_t MinimumBatches = 512;
constexpr std::size_t RequiredQueries = 4096;
constexpr unsigned ApprovalPairs = 3, ControlPeriod = 16;
constexpr double EntryRatio = .90, ExitRatio = .95;
struct Work { const Slice *next; std::uint64_t sum; Counters counters; };
extern "C" void prepare_work(const Values &, const Slice *, const Slice *, bool, Work *);
