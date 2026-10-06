#if defined(__x86_64__)
    .text

    .globl ithute_asm_cpuid
    .type ithute_asm_cpuid, @function
ithute_asm_cpuid:
    pushq %rbx
    movq %rdx, %r10
    movq %rcx, %r11
    movl %edi, %eax
    movl %esi, %ecx
    cpuid
    movl %eax, (%r10)
    movl %ebx, (%r11)
    movl %ecx, (%r8)
    movl %edx, (%r9)
    popq %rbx
    ret
    .size ithute_asm_cpuid, .-ithute_asm_cpuid

    .globl ithute_asm_rdtsc
    .type ithute_asm_rdtsc, @function
ithute_asm_rdtsc:
    lfence
    rdtsc
    shlq $32, %rdx
    orq %rdx, %rax
    ret
    .size ithute_asm_rdtsc, .-ithute_asm_rdtsc

    .section .note.GNU-stack,"",@progbits
#endif
