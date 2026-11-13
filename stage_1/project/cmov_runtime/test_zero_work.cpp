// Functional checks of BOLT's lifted entry, including inaccessible unused
// contexts. Performance is measured separately with the production harness.
#include "runtime.h"
#include <algorithm>
#include <cstring>
#include <iostream>
#include <stdexcept>
#include <sys/mman.h>
#include <unistd.h>

static void require(bool OK, const char *Message) {
  if (!OK) throw std::runtime_error(Message);
}

int main(int argc, char **) {
  const bool Lifted = argc > 1;
  unsigned Cases = 0;
  std::uint64_t Digest = 0;
  for (unsigned Size : {0u, 1u, 64u, 4096u}) {
    Values V(Size), Q(4096);
    for (unsigned I = 0; I < Size; ++I) V[I] = 2*I;
    for (unsigned I = 0; I < Q.size(); ++I) Q[I] = (I*17)%(2*Size+1);
    for (unsigned Batches : {0u, 1u, 4u, 511u, 512u, 513u, 1024u})
      for (unsigned Length : {0u, 1u, 4096u})
        for (bool Mixed : {false, true}) {
          std::vector<Slice> Slices;
          std::uint64_t Expected = 0;
          for (unsigned B = 0; B < Batches; ++B) {
            const unsigned N = Mixed && B%2 == 0 ? 0 : Length;
            Slices.push_back({Q.data(), Q.data()+N});
            for (unsigned I = 0; I < N; ++I)
              Expected += std::lower_bound(V.begin(), V.end(), Q[I])-V.begin();
          }
          Slice Dummy{};
          const Slice *Begin = Slices.empty() ? &Dummy : Slices.data();
          const bool AllEmpty = Batches == 0 || Length == 0 || (Mixed && Batches == 1);
          for (bool HasOut : {false, true}) {
            Counters C;
            std::memset(&C, 0xaa, sizeof(C));
            auto Result = cmov_batch_v1(&V, Begin, Begin+Batches, HasOut ? &C : nullptr);
            require(Result == Expected, "incorrect lifted result");
            if (Lifted && HasOut && (Size == 0 || AllEmpty))
              require(C.short_bypass == 1 && !C.trial_batches && !C.active_batches &&
                      !C.controls && !C.clock_reads && !C.entered && !C.rejection &&
                      !C.fallback_batches && !C.suspicion_controls,
                      "zero work entered controller or left stale counters");
            Digest += Result;
            ++Cases;
          }
        }
  }
  // An unused context must not be read when all query ranges are empty.
  const auto PageSize = static_cast<std::size_t>(sysconf(_SC_PAGESIZE));
  void *Page = mmap(nullptr, PageSize, PROT_NONE, MAP_PRIVATE|MAP_ANONYMOUS, -1, 0);
  require(Page != MAP_FAILED, "mmap failed");
  Values Q(1);
  for (unsigned Batches : {0u, 1u, 512u, 1024u}) {
    std::vector<Slice> Slices(Batches+1, {Q.data(), Q.data()});
    for (const void *Context : {Page, static_cast<void *>(nullptr)}) {
      Counters C;
      require(cmov_batch_v1(Context, Slices.data(), Slices.data()+Batches, &C) == 0,
              "unused context changed result");
      if (Lifted) require(C.short_bypass && !C.clock_reads, "unused context monitored");
      ++Cases;
    }
  }
  munmap(Page, PageSize);
  std::cout << "{\"cases\":" << Cases << ",\"digest\":" << Digest << "}\n";
}
