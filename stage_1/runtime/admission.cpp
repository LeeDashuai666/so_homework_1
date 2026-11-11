#include "runtime.h"
extern "C" void prepare_work(const Values &v,const Slice *b,const Slice *e,bool enabled,Work *w) {
  *w={b,0,{}};
  bool eligible=enabled && b!=e && std::size_t(e-b)>=MinimumBatches;
  if (eligible) for (auto s=b;s!=e;++s) {
    if (s->begin==s->end || std::size_t(s->end-s->begin)!=RequiredQueries) {
      eligible=false;
      break;
    }
  }
  if (eligible) w->sum=inspect_prefix(v,&w->next,e,&w->counters);
  else if (enabled) {
    w->counters.short_bypass=1;
    w->counters.fallback_batches=b==e ? 0 : e-b;
  }
}
