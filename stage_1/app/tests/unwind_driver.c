#define _GNU_SOURCE
#include <dlfcn.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unwind.h>

struct trace { unsigned frames; int found; };
static _Unwind_Reason_Code trace_one(struct _Unwind_Context *ctx, void *arg) {
  struct trace *trace = arg;
  Dl_info info;
  uintptr_t ip = _Unwind_GetIP(ctx);
  if (dladdr((void*)ip, &info) && info.dli_sname &&
      strcmp(info.dli_sname, "unwind_subject") == 0)
    trace->found = 1;
  trace->frames++;
  return _URC_NO_REASON;
}
int unwind_probe(void) {
  struct trace trace = {0, 0};
  _Unwind_Backtrace(trace_one, &trace);
  return trace.found && trace.frames >= 4;
}
extern int unwind_subject(uint64_t, uint64_t, uint64_t, uint64_t, uint64_t, uint64_t);
int main(void) {
  int ok = unwind_subject(1, 0, 0, 0, 3, 4);
  printf("{\"converted_frame_found\":%d}\n", ok);
  return ok ? 0 : 1;
}
