#define _GNU_SOURCE
#include <errno.h>
#include <inttypes.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>

/* Deliberately fixed assembly is a counter reference, not an application
 * optimization benchmark. Each positive iteration retires 3 or 11 instructions
 * and exactly one conditional branch. Inspect probe.asm after compilation. */
__attribute__((noinline)) static uint64_t counted_loop(uint64_t n) {
  uint64_t sum = 0;
  if (n)
    __asm__ volatile("1: add $1, %[sum]\n\t"
                     "sub $1, %[n]\n\t"
                     "jnz 1b"
                     : [sum] "+r"(sum), [n] "+r"(n)
                     :
                     : "cc");
  return sum;
}

__attribute__((noinline)) static uint64_t padded_loop(uint64_t n) {
  uint64_t sum = 0;
  if (n)
    __asm__ volatile("1: add $1, %[sum]\n\t"
                     ".rept 8\n\tnop\n\t.endr\n\t"
                     "sub $1, %[n]\n\t"
                     "jnz 1b"
                     : [sum] "+r"(sum), [n] "+r"(n)
                     :
                     : "cc");
  return sum;
}

/* A 16 KiB repeating sequence proved learnable in the first diagnostic run.
 * Keep that run as evidence; use a longer sequence without relaxing criteria. */
static unsigned char pattern[1048576] __attribute__((aligned(64)));

/* Exactly two conditional branches per iteration, regardless of pattern. */
__attribute__((noinline)) static uint64_t branch_loop(uint64_t n) {
  uint64_t sum = 0, index = 0;
  if (n)
    __asm__ volatile("1: cmpb $0, (%[data], %[index], 1)\n\t"
                     "je 2f\n\t"
                     "add $1, %[sum]\n\t"
                     "2: add $1, %[index]\n\t"
                     "and $1048575, %[index]\n\t"
                     "sub $1, %[n]\n\t"
                     "jnz 1b"
                     : [sum] "+r"(sum), [index] "+r"(index), [n] "+r"(n)
                     : [data] "r"(pattern)
                     : "cc", "memory");
  return sum;
}

static uint64_t ns(clockid_t clock) {
  struct timespec t;
  if (clock_gettime(clock, &t))
    exit(2);
  return (uint64_t)t.tv_sec * 1000000000 + t.tv_nsec;
}

int main(int argc, char **argv) {
  if (argc < 2)
    return 2;
  const char *mode = argv[1];
  uint64_t n = argc > 2 ? strtoull(argv[2], NULL, 10) : 0;
  if (!strcmp(mode, "busy")) {
    puts("ready");
    fflush(stdout);
    return counted_loop(UINT64_MAX) == 0;
  }
  if (!strcmp(mode, "branch-fixed") || !strcmp(mode, "branch-random")) {
    uint32_t x = 0x10203041;
    for (unsigned i = 0; i < sizeof(pattern); ++i) {
      x ^= x << 13;
      x ^= x >> 17;
      x ^= x << 5;
      pattern[i] = !strcmp(mode, "branch-random") ? x & 1 : 0;
    }
  }
  struct rusage before, after;
  getrusage(RUSAGE_SELF, &before);
  int cpu_before = sched_getcpu();
  uint64_t start_cpu = ns(CLOCK_THREAD_CPUTIME_ID);
  uint64_t start = ns(CLOCK_MONOTONIC_RAW);
  uint64_t checksum = 0;
  if (!strcmp(mode, "hello"))
    puts("hello world");
  else if (!strcmp(mode, "count"))
    checksum = counted_loop(n);
  else if (!strcmp(mode, "padded"))
    checksum = padded_loop(n);
  else if (!strcmp(mode, "branch-fixed") || !strcmp(mode, "branch-random"))
    checksum = branch_loop(n);
  else if (!strcmp(mode, "sleep")) {
    struct timespec delay = {n / 1000, (n % 1000) * 1000000};
    while (nanosleep(&delay, &delay) && errno == EINTR) {}
  } else
    return 2;
  uint64_t elapsed = ns(CLOCK_MONOTONIC_RAW) - start;
  uint64_t cpu_elapsed = ns(CLOCK_THREAD_CPUTIME_ID) - start_cpu;
  int cpu_after = sched_getcpu();
  getrusage(RUSAGE_SELF, &after);
  printf("{\"mode\":\"%s\",\"n\":%" PRIu64 ",\"checksum\":%" PRIu64
         ",\"wall_ns\":%" PRIu64 ",\"thread_cpu_ns\":%" PRIu64
         ",\"cpu_before\":%d,\"cpu_after\":%d,\"voluntary_switches\":%ld,"
         "\"involuntary_switches\":%ld}\n",
         mode, n, checksum, elapsed, cpu_elapsed, cpu_before, cpu_after,
         after.ru_nvcsw - before.ru_nvcsw, after.ru_nivcsw - before.ru_nivcsw);
  return 0;
}
