#include "runtime.h"

extern "C" std::uint64_t run_dispatch(const Values &v, const Slice *b,
                                      const Slice *e, bool enabled, Counters *out) {
  Work w;
  prepare_work(v,b,e,enabled,&w);
  // ONE actual call site for off, pre-admission rejection and terminal
  // fallback. inspect_prefix has already returned, restoring the same stack.
  auto sum = w.sum + run_plain(v,w.next,e);
  if (out) *out=w.counters;
  return sum;
}

extern "C" std::uint64_t run_guarded(const Values &v,const Slice *b,const Slice *e,Counters *out) {
  return run_dispatch(v,b,e,true,out);
}
