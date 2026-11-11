#include "runtime.h"
#include <algorithm>
#include <array>
#include <chrono>
#include <iostream>
#include <random>
#include <stdexcept>
#include <string>

constexpr unsigned BatchSize = 4096;
struct Phase { unsigned hot, batches; bool high = false, sorted = false; unsigned shape = 0; std::vector<Values> queries; };
struct Result { std::uint64_t ns, sum; Counters c; };
int main(int argc, char **argv) {
  try {
    if (argc != 6) throw std::runtime_error("MODE CASE SIZE SEED REPEATS");
    const std::string mode = argv[1], name = argv[2];
    const unsigned n = std::stoul(argv[3]), repeats = std::stoul(argv[5]);
    const std::uint64_t seed = std::stoull(argv[4]);
    if (!n || n > 1u<<22 || !repeats || repeats > 8192) throw std::runtime_error("invalid size/repeats");
    std::vector<Phase> phases;
    if (name == "low95" || name == "train") phases = {{95, 512}};
    else if (name == "high95") phases = {{95, 512, true}};
    else if (name == "low80") phases = {{80, 512}};
    else if (name == "low50") phases = {{50, 512}};
    else if (name == "uniform") phases = {{0, 1024}};
    else if (name == "sorted") phases = {{0, 512, false, true}};
    else if (name == "shift") phases = {{95, 256}, {0, 256}, {95, 512}};
    else if (name == "shift-high") phases = {{95, 256, true}, {0, 256}, {95, 512, true}};
    else if (name == "long-recovery") phases = {{0, 1024}, {95, 512}};
    else if (name == "fast-shift" || name == "fast-shift1") {
      for (unsigned i=0; i<64; ++i) phases.push_back({i%2 ? 0u : 95u, name=="fast-shift" ? 4u : 1u});
    } else if (name == "short-uniform1") phases = {{0, 1}};
    else if (name == "short-uniform4") phases = {{0, 4}};
    else if (name == "short-uniform16") phases = {{0, 16}};
    else if (name == "short-uniform63") phases = {{0, 63}};
    else if (name == "threshold64") phases = {{0, 64}};
    else if (name == "threshold65") phases = {{0, 65}};
    else if (name == "short-low95") phases = {{95, 16}};
    else if (name == "hot-prefix") phases = {{0, 512, false, false, 1}};
    else if (name == "hot-suffix") phases = {{0, 512, false, false, 2}};
    else if (name == "striped") phases = {{0, 512, false, false, 3}};
    // Additional rejection-boundary and temporal-alias stress, not selector hints.
    else if (name == "threshold511") phases = {{0, 511}};
    else if (name == "threshold512") phases = {{0, 512}};
    else if (name == "threshold513") phases = {{0, 513}};
    else if (name == "early-shift") phases = {{95, 8}, {0, 1016}};
    else if (name == "calibration-alias") {
      for (unsigned i=0; i<6; ++i) phases.push_back({i%2 ? 95u : 0u, 1});
      phases.push_back({0, 1018});
    } else throw std::runtime_error("unknown scenario");
    if (name == "train") phases[0].batches = 16;
    Values values(n);
    for (unsigned i=0; i<n; ++i) values[i]=i*2;
    std::mt19937_64 rng(seed);
    std::vector<Slice> slices;
    std::uint64_t expected = 0;
    for (auto &p : phases) {
      p.queries.resize(8);
      std::array<std::uint64_t, 8> sums{};
      for (unsigned k=0; k<8; ++k) {
        auto &q=p.queries[k]; q.resize(BatchSize);
        for (unsigned i=0; i<BatchSize; ++i) {
          unsigned hot = p.shape==1 ? (i<512 ? 95 : 0) : p.shape==2 ? (i>=3072 ? 95 : 0)
                       : p.shape==3 ? ((i/64)%2 ? 0 : 95) : p.hot;
          q[i] = rng()%100 < hot ? (p.high ? 2*n : 0) : rng()%(2*n);
          sums[k] += std::lower_bound(values.begin(), values.end(), q[i])-values.begin();
        }
        if (p.sorted) std::sort(q.begin(), q.end());
      }
      for (unsigned b=0; b<p.batches; ++b) {
        auto &q=p.queries[b%8]; slices.push_back({q.data(), q.data()+q.size()});
        expected += sums[b%8];
      }
    }
    auto run = [&](const std::string &variant) {
      Result r{};
      const auto start=std::chrono::steady_clock::now();
      for (unsigned i=0; i<repeats; ++i) {
        if (variant=="off" || variant=="guarded") {
          Counters c;
          r.sum += run_dispatch(values,slices.data(),slices.data()+slices.size(),variant=="guarded",&c);
          r.c.trial_batches+=c.trial_batches; r.c.active_batches+=c.active_batches;
          r.c.controls+=c.controls; r.c.clock_reads+=c.clock_reads;
          r.c.fallback_batches+=c.fallback_batches; r.c.entered+=c.entered;
          r.c.rejection+=bool(c.rejection); r.c.short_bypass+=c.short_bypass;
          r.c.suspicion_controls+=c.suspicion_controls;
        } else if (variant=="on") {
          for (const auto &s : slices) r.sum+=lookup_branch(values,s.begin,s.end);
        } else throw std::runtime_error("unknown variant");
      }
      r.ns=std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now()-start).count();
      if (r.sum!=expected*repeats) throw std::runtime_error("checksum mismatch");
      return r;
    };
    // Pair mode is a randomized ABBA/BAAB block inside one process. All calls
    // have fresh state. Null uses the identical plain implementation twice.
    const bool paired=mode=="pair" || mode=="null";
    const bool reverse=(seed * 0x9e3779b97f4a7c15ULL)>>63;
    if (paired) { run("off"); run(mode=="null" ? "off" : "guarded"); }
    std::cout << "{\"batches\":" << slices.size() << ",\"repeats\":" << repeats << ",\"runs\":[";
    for (unsigned i=0; i<(paired ? 4u : 1u); ++i) {
      const bool a = (i==0 || i==3) != reverse;
      const std::string label=paired ? (a ? "A" : "B") : mode;
      const std::string variant=paired ? (a || mode=="null" ? "off" : "guarded") : mode;
      auto r=run(variant);
      if (i) std::cout << ',';
      std::cout << "{\"label\":\""<<label<<"\",\"variant\":\""<<variant<<"\",\"elapsed_ns\":"<<r.ns
                <<",\"checksum\":"<<r.sum<<",\"trial_batches\":"<<r.c.trial_batches
                <<",\"active_batches\":"<<r.c.active_batches<<",\"controls\":"<<r.c.controls
                <<",\"clock_reads\":"<<r.c.clock_reads<<",\"fallback_batches\":"<<r.c.fallback_batches
                <<",\"entered\":"<<r.c.entered<<",\"rejections\":"<<r.c.rejection
                <<",\"suspicion_controls\":"<<r.c.suspicion_controls
                <<",\"short_bypass\":"<<r.c.short_bypass<<'}';
    }
    std::cout << "]}\n";
  } catch (const std::exception &e) { std::cerr<<e.what()<<'\n'; return 1; }
}
