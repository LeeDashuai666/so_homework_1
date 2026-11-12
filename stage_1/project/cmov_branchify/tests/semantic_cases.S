.text
.macro START name
.global \name
.type \name,@function
\name:
  mov 8(%rsp), %r10
  cmp %rdx, %rsi
  mov %rcx, %rax
  mov %r9, %rdx
.endm
.macro FINISH name
  pushfq
  pop %r11
  mov %rax, 0(%rdi)
  mov %rdx, 8(%rdi)
  mov %r11, 16(%rdi)
  ret
.size \name, .-\name
.endm

START sem_pair
  cmovae %r8, %rax
  cmovae %r10, %rdx
FINISH sem_pair

START sem_chain
  cmovae %r8, %rax
  cmovae %rax, %rdx
FINISH sem_chain

// These groups must be rejected by the narrow 64-bit register-only sieve.
START sem_width32
  cmovae %r8d, %eax
  cmovae %r10d, %edx
FINISH sem_width32

START sem_memory
  cmovae (%r8), %rax
  cmovae (%r10), %rdx
FINISH sem_memory

START sem_mixed
  cmovae %r8, %rax
  cmovb %r10, %rdx
FINISH sem_mixed

START sem_internal_entry
  jae .Lsecond
  cmovae %r8, %rax
.Lsecond:
  cmovae %r10, %rdx
FINISH sem_internal_entry

START sem_external_entry
  cmovae %r8, %rax
.global external_middle_label
external_middle_label:
  cmovae %r10, %rdx
FINISH sem_external_entry

.global external_caller
.type external_caller,@function
external_caller:
  jmp external_middle_label
.size external_caller, .-external_caller

.section .note.GNU-stack,"",@progbits
