// Deterministic fault injection tests the controller's safety paths. This is
// not a performance model and is never used to approve a candidate profile.
#include "runtime.h"
#include <cerrno>
#include <ctime>
#include <iostream>
#include <stdexcept>

static std::uint64_t now_ns;
static unsigned clock_calls, fail_clock, backwards_clock, change_at;
static bool bad_branch;
static std::vector<unsigned> visits, b_visits;

extern "C" int clock_gettime(clockid_t, timespec *out) noexcept {
  ++clock_calls; now_ns+=10;
  if (clock_calls==fail_clock) { errno=EIO; return -1; }
  auto n=clock_calls==backwards_clock ? 0 : now_ns;
  out->tv_sec=n/1000000000ULL; out->tv_nsec=n%1000000000ULL;
  return 0;
}
extern "C" std::uint64_t lookup_cmov(const Values &,const std::uint64_t *b,const std::uint64_t *e) {
  if (b==e) return 0;
  ++visits.at(*b); now_ns+=1000;
  return *b;
}
extern "C" std::uint64_t lookup_branch(const Values &,const std::uint64_t *b,const std::uint64_t *e) {
  if (b==e) return 0;
  ++visits.at(*b); ++b_visits.at(*b);
  now_ns+=(bad_branch || *b>=change_at) ? 3000 : 500;
  return *b;
}
static void require(bool ok,const char *message) { if (!ok) throw std::runtime_error(message); }
static Counters check(unsigned n,unsigned fail=0,unsigned backwards=0,bool bad=false,unsigned change=~0u,unsigned length=RequiredQueries) {
  now_ns=0; clock_calls=0; fail_clock=fail; backwards_clock=backwards;
  bad_branch=bad; change_at=change;
  visits.assign(n,0); b_visits.assign(n,0);
  const unsigned stride=length ? length : 1;
  Values v, q(std::size_t(n)*stride); std::vector<Slice> slices;
  for (unsigned i=0; i<n; ++i) {
    q[std::size_t(i)*stride]=i;
    auto begin=q.data()+std::size_t(i)*stride;
    slices.push_back({begin,begin+length});
  }
  Counters c;
  auto sum=run_guarded(v,slices.data(),slices.data()+slices.size(),&c);
  require(sum==(length ? std::uint64_t(n)*(n-1)/2 : 0),"wrong result");
  for (auto count: visits) require(count==(length ? 1u : 0u),"work lost or duplicated");
  require(c.trial_batches<=3,"more than one admission attempt");
  return c;
}
int main() {
  unsigned passed=0;
  { auto c=check(511); require(c.short_bypass && !c.clock_reads && !c.trial_batches,"short bypass"); ++passed; }
  { auto c=check(512); require(c.entered && !c.rejection && c.trial_batches==3,"positive admission"); ++passed; }
  { auto c=check(512,0,0,true); require(!c.entered && c.rejection==2 && c.trial_batches==1 && c.fallback_batches==510,"terminal failed admission"); ++passed; }
  { auto c=check(512,0,0,false,8); require(c.entered && c.rejection==3 && c.suspicion_controls==1,"shift fallback");
    for (unsigned i=11;i<512;++i) require(!b_visits[i],"reentered after rejection"); ++passed; }
  for (unsigned fail: {1u,2u,3u,4u,12u,13u,14u}) {
    auto c=check(512,fail); require(c.rejection==1,"clock failure must fall back"); ++passed;
  }
  { auto c=check(512,0,2); require(c.rejection==1,"backwards clock must fall back"); ++passed; }
  { Values v; Slice dummy{}; Counters c;
    require(run_guarded(v,&dummy,&dummy,&c)==0 && c.short_bypass && !c.clock_reads,"empty range"); ++passed; }
  for (unsigned length: {0u,1u,4095u,4097u}) {
    auto c=check(512,0,0,false,~0u,length);
    require(c.short_bypass && !c.clock_reads && !c.trial_batches,"irregular batch shape must not probe"); ++passed;
  }
  std::cout<<"{\"tests_passed\":"<<passed<<",\"performance_claimed\":false}\n";
}
