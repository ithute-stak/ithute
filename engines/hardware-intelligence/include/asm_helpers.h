#ifndef ITHUTE_ASM_HELPERS_H
#define ITHUTE_ASM_HELPERS_H

#include <stdint.h>

typedef struct {
    int available;
    char vendor[13];
    unsigned int family;
    unsigned int model;
    unsigned int stepping;
    int invariant_tsc;
    int rdtscp;
    int aes_ni;
    int avx;
    int avx2;
    unsigned long long cycle_counter;
} ithute_cpu_native_t;

void ithute_cpu_native_summary(ithute_cpu_native_t *out);

#if defined(__x86_64__)
void ithute_asm_cpuid(
    unsigned int leaf,
    unsigned int subleaf,
    unsigned int *eax,
    unsigned int *ebx,
    unsigned int *ecx,
    unsigned int *edx
);
uint64_t ithute_asm_rdtsc(void);
#endif

#endif
