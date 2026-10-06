#define _POSIX_C_SOURCE 200809L
#include <dirent.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/statvfs.h>
#include <time.h>
#include <unistd.h>

typedef struct {
    unsigned long long user, nice, system, idle, iowait, irq, softirq, steal;
} cpu_sample_t;

typedef struct {
    int devices;
    unsigned long long reads_completed;
    unsigned long long sectors_read;
    unsigned long long writes_completed;
    unsigned long long sectors_written;
    unsigned long long io_ms;
    unsigned long long weighted_io_ms;
} block_summary_t;

typedef struct {
    unsigned long long rx_errors;
    unsigned long long tx_errors;
    unsigned long long rx_dropped;
    unsigned long long tx_dropped;
    unsigned long long tcp_retrans_segs;
} network_summary_t;

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

static double read_pressure_avg10(const char *resource) {
    char path[128];
    if (snprintf(path, sizeof(path), "/proc/pressure/%s", resource) >= (int)sizeof(path)) return -1.0;
    FILE *f = fopen(path, "r");
    if (!f) return -1.0;
    char line[256] = {0};
    double avg10 = -1.0;
    if (fgets(line, sizeof(line), f) != NULL) {
        char *marker = strstr(line, "avg10=");
        if (marker) (void)sscanf(marker, "avg10=%lf", &avg10);
    }
    fclose(f);
    return avg10;
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

static int ignored_block_device(const char *name) {
    return strncmp(name, "loop", 4) == 0 || strncmp(name, "ram", 3) == 0;
}

static void block_summary(block_summary_t *out) {
    memset(out, 0, sizeof(*out));
    DIR *dir = opendir("/sys/block");
    if (!dir) return;

    struct dirent *entry;
    while ((entry = readdir(dir)) != NULL) {
        if (entry->d_name[0] == '.' || ignored_block_device(entry->d_name)) continue;

        char path[512];
        if (snprintf(path, sizeof(path), "/sys/block/%s/stat", entry->d_name) >= (int)sizeof(path)) continue;
        FILE *f = fopen(path, "r");
        if (!f) continue;

        unsigned long long reads = 0, reads_merged = 0, sectors_read = 0, read_ms = 0;
        unsigned long long writes = 0, writes_merged = 0, sectors_written = 0, write_ms = 0;
        unsigned long long ios_in_progress = 0, io_ms = 0, weighted_io_ms = 0;
        int n = fscanf(f, "%llu %llu %llu %llu %llu %llu %llu %llu %llu %llu %llu",
            &reads, &reads_merged, &sectors_read, &read_ms,
            &writes, &writes_merged, &sectors_written, &write_ms,
            &ios_in_progress, &io_ms, &weighted_io_ms);
        fclose(f);

        if (n < 11) continue;
        out->devices++;
        out->reads_completed += reads;
        out->sectors_read += sectors_read;
        out->writes_completed += writes;
        out->sectors_written += sectors_written;
        out->io_ms += io_ms;
        out->weighted_io_ms += weighted_io_ms;
    }
    closedir(dir);
}

static void network_device_summary(network_summary_t *out) {
    FILE *f = fopen("/proc/net/dev", "r");
    if (!f) return;

    char line[1024];
    while (fgets(line, sizeof(line), f) != NULL) {
        char *colon = strchr(line, ':');
        if (!colon) continue;
        *colon = '\0';

        char *iface = line;
        while (*iface == ' ' || *iface == '\t') iface++;
        char *end = iface + strlen(iface);
        while (end > iface && (end[-1] == ' ' || end[-1] == '\t')) *--end = '\0';
        if (strcmp(iface, "lo") == 0 || *iface == '\0') continue;

        unsigned long long rx_bytes = 0, rx_packets = 0, rx_errs = 0, rx_drop = 0;
        unsigned long long rx_fifo = 0, rx_frame = 0, rx_compressed = 0, rx_multicast = 0;
        unsigned long long tx_bytes = 0, tx_packets = 0, tx_errs = 0, tx_drop = 0;
        unsigned long long tx_fifo = 0, tx_colls = 0, tx_carrier = 0, tx_compressed = 0;
        int n = sscanf(
            colon + 1,
            "%llu %llu %llu %llu %llu %llu %llu %llu %llu %llu %llu %llu %llu %llu %llu %llu",
            &rx_bytes, &rx_packets, &rx_errs, &rx_drop,
            &rx_fifo, &rx_frame, &rx_compressed, &rx_multicast,
            &tx_bytes, &tx_packets, &tx_errs, &tx_drop,
            &tx_fifo, &tx_colls, &tx_carrier, &tx_compressed
        );
        if (n != 16) continue;

        out->rx_errors += rx_errs;
        out->tx_errors += tx_errs;
        out->rx_dropped += rx_drop;
        out->tx_dropped += tx_drop;
    }
    fclose(f);
}

static void tcp_retrans_summary(network_summary_t *out) {
    FILE *f = fopen("/proc/net/snmp", "r");
    if (!f) return;

    char header[4096];
    char values[4096];
    while (fgets(header, sizeof(header), f) != NULL) {
        if (strncmp(header, "Tcp:", 4) != 0) continue;
        if (fgets(values, sizeof(values), f) == NULL || strncmp(values, "Tcp:", 4) != 0) break;

        char *header_save = NULL;
        char *value_save = NULL;
        char *header_token = strtok_r(header, " \t\r\n", &header_save);
        char *value_token = strtok_r(values, " \t\r\n", &value_save);
        while (header_token && value_token) {
            if (strcmp(header_token, "RetransSegs") == 0) {
                out->tcp_retrans_segs = strtoull(value_token, NULL, 10);
                fclose(f);
                return;
            }
            header_token = strtok_r(NULL, " \t\r\n", &header_save);
            value_token = strtok_r(NULL, " \t\r\n", &value_save);
        }
    }
    fclose(f);
}

static void network_summary(network_summary_t *out) {
    memset(out, 0, sizeof(*out));
    network_device_summary(out);
    tcp_retrans_summary(out);
}

static int command_available(const char *a, const char *b) {
    return (a && access(a, X_OK) == 0) || (b && access(b, X_OK) == 0);
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

    struct statvfs fs = {0};
    int fs_ok = statvfs("/", &fs) == 0;
    unsigned long long fs_total = fs_ok ? (unsigned long long)fs.f_blocks * fs.f_frsize : 0;
    unsigned long long fs_free = fs_ok ? (unsigned long long)fs.f_bavail * fs.f_frsize : 0;

    block_summary_t block = {0};
    block_summary(&block);

    network_summary_t network = {0};
    network_summary(&network);

    double cpu_pressure = read_pressure_avg10("cpu");
    double memory_pressure = read_pressure_avg10("memory");
    double io_pressure = read_pressure_avg10("io");

    int has_hwmon = access("/sys/class/hwmon", R_OK) == 0;
    int has_thermal = access("/sys/class/thermal", R_OK) == 0;
    int has_edac = access("/sys/devices/system/edac", R_OK) == 0;
    int has_ipmi = access("/dev/ipmi0", R_OK) == 0 || access("/dev/ipmi/0", R_OK) == 0;
    int has_bpf_fs = access("/sys/fs/bpf", R_OK) == 0;
    int has_kernel_btf = access("/sys/kernel/btf/vmlinux", R_OK) == 0;
    int has_smartctl = command_available("/usr/sbin/smartctl", "/usr/bin/smartctl");
    int has_nvme_cli = command_available("/usr/sbin/nvme", "/usr/bin/nvme");

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
    printf("\"thermal\":{\"zones_seen\":%d,\"max_celsius\":%.2f},", thermal_zones, max_temp);
    printf("\"pressure\":{\"cpu_avg10\":%.3f,\"memory_avg10\":%.3f,\"io_avg10\":%.3f},",
        cpu_pressure, memory_pressure, io_pressure);
    printf("\"filesystem\":{\"root_total_bytes\":%llu,\"root_available_bytes\":%llu},", fs_total, fs_free);
    printf("\"block\":{\"devices\":%d,\"reads_completed\":%llu,\"sectors_read\":%llu,\"writes_completed\":%llu,\"sectors_written\":%llu,\"io_ms\":%llu,\"weighted_io_ms\":%llu},",
        block.devices, block.reads_completed, block.sectors_read, block.writes_completed, block.sectors_written, block.io_ms, block.weighted_io_ms);
    printf("\"network\":{\"rx_errors\":%llu,\"tx_errors\":%llu,\"rx_dropped\":%llu,\"tx_dropped\":%llu,\"tcp_retrans_segs\":%llu},",
        network.rx_errors, network.tx_errors, network.rx_dropped, network.tx_dropped, network.tcp_retrans_segs);
    printf("\"capabilities\":{");
    printf("\"hwmon\":%s,\"thermal\":%s,\"edac\":%s,\"ipmi\":%s,",
        has_hwmon ? "true" : "false", has_thermal ? "true" : "false", has_edac ? "true" : "false", has_ipmi ? "true" : "false");
    printf("\"bpf_fs\":%s,\"kernel_btf\":%s,\"smartctl\":%s,\"nvme_cli\":%s",
        has_bpf_fs ? "true" : "false", has_kernel_btf ? "true" : "false",
        has_smartctl ? "true" : "false", has_nvme_cli ? "true" : "false");
    printf("}");
    printf("}\n");
    return 0;
}
