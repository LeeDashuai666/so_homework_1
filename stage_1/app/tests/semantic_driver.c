#include <stdint.h>
#include <stdio.h>

typedef void (*case_fn)(uint64_t*, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t);
extern void sem_pair(uint64_t*, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t);
extern void sem_chain(uint64_t*, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t);
extern void sem_width32(uint64_t*, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t);

static uint64_t random_state = UINT64_C(0x85d17a392bc23e17);
static uint64_t next(void) {
  random_state ^= random_state << 13;
  random_state ^= random_state >> 7;
  random_state ^= random_state << 17;
  return random_state;
}

static uint64_t cmp_flags(uint64_t a, uint64_t b) {
  uint64_t r = a - b;
  return (a < b) | ((uint64_t)(__builtin_popcount((unsigned)(r & 255)) % 2 == 0) << 2)
         | ((a ^ b ^ r) & 16) | ((uint64_t)(r == 0) << 6) | ((r >> 63) << 7)
         | ((((a ^ b) & (a ^ r)) >> 63) << 11);
}

int main(void) {
  case_fn functions[] = {sem_pair, sem_chain, sem_width32};
  uint64_t boundary[] = {0, 1, UINT64_MAX, UINT64_C(1) << 63, (UINT64_C(1) << 63)-1};
  uint64_t checksum = 0;
  for (unsigned i = 0; i < 100000; ++i) {
    uint64_t a = i < 25 ? boundary[i/5] : next();
    uint64_t b = i < 25 ? boundary[i%5] : next();
    uint64_t old0 = next(), src0 = next(), old1 = next(), src1 = next();
    for (unsigned k = 0; k < 3; ++k) {
      uint64_t out[3];
      functions[k](out, a, b, old0, src0, old1, src1);
      uint64_t expected0 = a >= b ? src0 : old0;
      uint64_t expected1 = a >= b ? (k == 1 ? src0 : src1) : old1;
      if (k == 2) { expected0 = (uint32_t)expected0; expected1 = (uint32_t)expected1; }
      if (out[0] != expected0 || out[1] != expected1 || (out[2] & 0x8d5) != cmp_flags(a, b)) {
        fprintf(stderr, "semantic failure case=%u iteration=%u\n", k, i);
        return 1;
      }
      checksum ^= out[0] + out[1] + (out[2] & 0x8d5);
    }
  }
  printf("{\"checks\":300000,\"checksum\":%llu}\n", (unsigned long long)checksum);
}
