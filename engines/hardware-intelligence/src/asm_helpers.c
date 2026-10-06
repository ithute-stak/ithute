#include "asm_helpers.h"

#include <string.h>

void ithute_cpu_native_summary(ithute_cpu_native_t *out) {
    memset(out, 0, sizeof(*out));
#if defined(__x86_64__)
    unsigned int eax = 0, ebx = 0, ecx = 0, edx = 0;
    unsigned int max_basic = 0;
    unsigned int max_extended = 0;

    out->available = 1;

    ithute_asm_cpuid(0, 0, &max_basic, &ebx, &ecx, &edx);
    memcpy(out->vendor + 0, &ebx, 4);
    memcpy(out->vendor + 4, &edx, 4);
    memcpy(out->vendor + 8, &ecx, 4);
    out->vendor[12] = '\0';

    if (max_basic >= 1) {
        ithute_asm_cpuid(1, 0, &eax, &ebx, &ecx, &edx);
        unsigned int base_family = (eax >> 8) & 0x0fU;
        unsigned int base_model = (eax >> 4) & 0x0fU;
        unsigned int ext_family = (eax >> 20) & 0xffU;
        unsigned int ext_model = (eax >> 16) & 0x0fU;
        out->family = base_family == 0x0fU ? base_family + ext_family : base_family;
        out->model = (base_family == 0x06U || base_family == 0x0fU)
            ? (ext_model << 4) | base_model
            : base_model;
        out->stepping = eax & 0x0fU;
        out->vmx = (ecx & (1U << 5)) != 0;
        out->aes_ni = (ecx & (1U << 25)) != 0;
        out->avx = (ecx & (1U << 28)) != 0;
        out->hypervisor_present = (ecx & (1U << 31)) != 0;
        out->logical_processors = (ebx >> 16) & 0xffU;
    }

    if (max_basic >= 7) {
        ithute_asm_cpuid(7, 0, &eax, &ebx, &ecx, &edx);
        out->avx2 = (ebx & (1U << 5)) != 0;
    }

    ithute_asm_cpuid(0x80000000U, 0, &max_extended, &ebx, &ecx, &edx);
    if (max_extended >= 0x80000001U) {
        ithute_asm_cpuid(0x80000001U, 0, &eax, &ebx, &ecx, &edx);
        out->svm = (ecx & (1U << 2)) != 0;
        out->rdtscp = (edx & (1U << 27)) != 0;
    }
    if (max_extended >= 0x80000007U) {
        ithute_asm_cpuid(0x80000007U, 0, &eax, &ebx, &ecx, &edx);
        out->invariant_tsc = (edx & (1U << 8)) != 0;
    }

    if (out->hypervisor_present) {
        unsigned int hypervisor_max = 0;
        ithute_asm_cpuid(0x40000000U, 0, &hypervisor_max, &ebx, &ecx, &edx);
        if (hypervisor_max >= 0x40000000U) {
            memcpy(out->hypervisor_vendor + 0, &ebx, 4);
            memcpy(out->hypervisor_vendor + 4, &ecx, 4);
            memcpy(out->hypervisor_vendor + 8, &edx, 4);
            out->hypervisor_vendor[12] = '\0';
        }
    }

    out->cycle_counter = (unsigned long long)ithute_asm_rdtsc();
#else
    (void)out;
#endif
}
