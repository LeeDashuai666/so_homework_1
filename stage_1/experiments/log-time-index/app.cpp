// Public-log cumulative counts: sum the number of events before each cutoff.
#include "runtime.h"
#include <algorithm>
#include <chrono>
#include <ctime>
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
using Clock=std::chrono::steady_clock;
int main(int argc,char **argv) {
 try {
  if(argc!=3)throw std::runtime_error("log-count LOGHUB_CSV QUERY_TIMESTAMPS");
  auto start=Clock::now();
  std::ifstream logs(argv[1]),queries(argv[2]);
  if(!logs || !queries)throw std::runtime_error("cannot open input");
  Values keys,q;std::string line;std::getline(logs,line);
  const std::string months="JanFebMarAprMayJunJulAugSepOctNovDec";
  while(std::getline(logs,line)) {
   if(line.empty())continue;
   std::istringstream row(line);std::string id,month,day,time;
   std::getline(row,id,',');std::getline(row,month,',');std::getline(row,day,',');std::getline(row,time,',');
   std::tm t{};t.tm_year=100;t.tm_mon=months.find(month)/3;t.tm_mday=std::stoi(day);
   t.tm_hour=std::stoi(time.substr(0,2));t.tm_min=std::stoi(time.substr(3,2));t.tm_sec=std::stoi(time.substr(6,2));
   keys.push_back(timegm(&t));
  }
  std::sort(keys.begin(),keys.end());uint64_t v;
  while(queries>>v)q.push_back(v);
  std::vector<Slice> slices;
  for(size_t i=0;i<q.size();i+=4096)slices.push_back({q.data()+i,q.data()+std::min(q.size(),i+4096)});
  Counters c{};auto ready=Clock::now();
  auto sum=cmov_batch_v1(&keys,slices.data(),slices.data()+slices.size(),&c);
  auto done=Clock::now();
  auto ns=[](auto a,auto b){return std::chrono::duration_cast<std::chrono::nanoseconds>(b-a).count();};
  std::cout<<"{\"checksum\":"<<sum<<",\"keys\":"<<keys.size()<<",\"queries\":"<<q.size()
           <<",\"compute_ns\":"<<ns(ready,done)<<",\"application_ns\":"<<ns(start,done)
           <<",\"entered\":"<<c.entered<<",\"active_batches\":"<<c.active_batches
           <<",\"clock_reads\":"<<c.clock_reads<<"}\n";
 } catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}
}
