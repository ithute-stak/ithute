#define _POSIX_C_SOURCE 200809L
#include <dirent.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

typedef struct {
    unsigned long long user, nice, system, idle, iowait, irq, softirq, steal;
} cpu_sample_t;

static int read_cpu(cpu_sample_t *out) {
    FILE *f = fopen("/proc/stat", "r");
    if (!f) return -1;
    char label[16] = {0};
    int n = fscanf(f, "%15s %llu %llu %llu %llu %llu %llu %llu %llu",
        label, &out->user, &out->nice, &out->system, &out->idle,
        &out->iowait, &out->irq, &out->softirq, &out->steal);
    fclose(f);
    return (n == 9 && strcmp(label, "cpu") == 0) ? 0 : -1;
}

static unsigned long long meminfo_kb(const char *key) {
    FILE *f = fopen("/proc/meminfo", "r");
    if (!f) return 0;
    char name[64];
    unsigned long long value = 0;
    char unit[16];
    while (fscanf(f, "%63s %llu %15s", name, &value, unit) == 3) {
        if (strcmp(name, key) == 0) {
            fclose(f);
            return value;
        }
    }
    fclose(f);
    return 0;
}

static double read_uptime(void) {
    FILE *f = fopen("/proc/uptime", "r");
    if (!f) return -1.0;
    double uptime = -1.0;
    (void)fscanf(f, "%lf", &uptime);
    fclose(f);
    return uptime;
}

static int read_load(double *one, double *five, double *fifteen) {
    FILE *f = fopen("/proc/loadavg", "r");
    if (!f) return -1;
    int n = fscanf(f, "%lf %lf %lf", one, five, fifteen);
    fclose(f);
    return n == 3 ? 0 : -1;
}

static void thermal_summary(double *max_c, int *count) {
    const char *base = "/sys/class/thermal";
    DIR *dir = opendir(base);
    if (!dir) {
        *max_c = 0.0;
        *count = 0;
        return;
    }
    struct dirent *entry;
    double max_value = -273.15;
    int seen = 0;
    while ((entry = readdir(dir)) != NULL) {
        if (strncmp(entry->d_name, "thermal_zone", 12) != 0) continue;
        char path[512];
        if (snprintf(path, sizeof(path), "%s/%s/temp", base, entry->d_name) >= (int)sizeof(path)) continue;
        FILE *f = fopen(path, "r");
        if (!f) continue;
        long milli = 0;
        if (fscanf(f, "%ld", &milli) == 1) {
            double c = ((double)milli) / 1000.0;
            if (c > max_value) max_value = c;
            seen++;
        }
        fclose(f);
    }
    closedir(dir);
    *max_c = seen ? max_value : 0.0;
    *count = seen;
}

int main(void) {
    cpu_sample_t cpu = {0};
    double load1 = 0, load5 = 0, load15 = 0;
    if (read_cpu(&cpu) != 0 || read_load(&load1, &load5, &load15) != 0) {
        fprintf(stderr, "ithute-hw-probe: unable to read core /proc telemetry: %s\n", strerror(errno));
        return 2;
    }

    unsigned long long mem_total = meminfo_kb("MemTotal:");
    unsigned long long mem_available = meminfo_kb("MemAvailable:");
    unsigned long long swap_total = meminfo_kb("SwapTotal:");
    unsigned long long swap_free = meminfo_kb("SwapFree:");
    double uptime = read_uptime();
    double max_temp = 0.0;
    int thermal_zones = 0;
    thermal_summary(&max_temp, &thermal_zones);

    time_t now = time(NULL);
    printf("{");
    printf("\"schema_version\":1,");
    printf("\"sampled_at_unix\":%lld,", (long long)now);
    printf("\"uptime_seconds\":%.0f,", uptime);
    printf("\"load\":{\"one\":%.3f,\"five\":%.3f,\"fifteen\":%.3f},", load1, load5, load15);
    printf("\"memory\":{\"total_kb\":%llu,\"available_kb\":%llu,\"swap_total_kb\":%llu,\"swap_free_kb\":%llu},",
        mem_total, mem_available, swap_total, swap_free);
    printf("\"cpu\":{\"user\":%llu,\"nice\":%llu,\"system\":%llu,\"idle\":%llu,\"iowait\":%llu,\"irq\":%llu,\"softirq\":%llu,\"steal\":%llu},",
        cpu.user, cpu.nice, cpu.system, cpu.idle, cpu.iowait, cpu.irq, cpu.softirq, cpu.steal);
    printf("\"thermal\":{\"zones_seen\":%d,\"max_celsius\":%.2f}", thermal_zones, max_temp);
    printf("}\n");
    return 0;
}
