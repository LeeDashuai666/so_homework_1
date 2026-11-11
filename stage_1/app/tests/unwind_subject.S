.text
.global unwind_subject
.type unwind_subject,@function
unwind_subject:
.cfi_startproc
  push %rbx
.cfi_def_cfa_offset 16
.cfi_offset %rbx, -16
  mov $4, %ecx
.Lagain:
  cmp %rsi, %rdi
  cmovae %r8, %rax
  cmovae %r9, %rdx
  dec %ecx
  jne .Lagain
  call unwind_probe@PLT
  pop %rbx
.cfi_def_cfa_offset 8
.cfi_restore %rbx
  ret
.cfi_endproc
.size unwind_subject, .-unwind_subject
.section .note.GNU-stack,"",@progbits
