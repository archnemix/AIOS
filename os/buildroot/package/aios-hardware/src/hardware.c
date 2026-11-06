#define _GNU_SOURCE
#include <sched.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

struct core_id { int package; int core; };

static int read_int(const char *path, int *value)
{
    FILE *file = fopen(path, "r");
    if (!file) return 0;
    int ok = fscanf(file, "%d", value) == 1;
    fclose(file);
    return ok;
}

static int quota_threads(void)
{
    /* Covers the common cgroup-v2 root/namespace case. Other quota layouts
       deliberately fall back to the affinity mask rather than guess. */
    FILE *file = fopen("/sys/fs/cgroup/cpu.max", "r");
    long quota, period;
    if (!file) return 0;
    int ok = fscanf(file, "%ld %ld", &quota, &period) == 2;
    fclose(file);
    if (!ok || quota <= 0 || period <= 0) return 0;
    long limit = quota / period;
    if (limit < 1) limit = 1;
    return limit > CPU_SETSIZE ? CPU_SETSIZE : (int)limit;
}

static int available_cores(int *logical, int *first_cpu)
{
    cpu_set_t mask;
    struct core_id seen[CPU_SETSIZE];
    int count = 0, valid_topology = 1;
    *logical = 0;
    *first_cpu = -1;
    CPU_ZERO(&mask);
    if (sched_getaffinity(0, sizeof(mask), &mask) != 0) {
        long fallback = sysconf(_SC_NPROCESSORS_ONLN);
        *logical = fallback > 0 && fallback <= CPU_SETSIZE ? (int)fallback : 1;
        return *logical;
    }
    for (int cpu = 0; cpu < CPU_SETSIZE; cpu++) {
        if (!CPU_ISSET(cpu, &mask)) continue;
        if (*first_cpu < 0) *first_cpu = cpu;
        (*logical)++;
        char path[160];
        struct core_id id;
        snprintf(path, sizeof(path), "/sys/devices/system/cpu/cpu%d/topology/physical_package_id", cpu);
        if (!read_int(path, &id.package)) { valid_topology = 0; continue; }
        snprintf(path, sizeof(path), "/sys/devices/system/cpu/cpu%d/topology/core_id", cpu);
        if (!read_int(path, &id.core)) { valid_topology = 0; continue; }
        int duplicate = 0;
        for (int i = 0; i < count; i++) {
            if (seen[i].package == id.package && seen[i].core == id.core) { duplicate = 1; break; }
        }
        if (!duplicate) seen[count++] = id;
    }
    if (*logical < 1) *logical = 1;
    return valid_topology && count > 0 ? count : *logical;
}

static void print_cache(int cpu)
{
    if (cpu < 0) return;
    for (int i = 0; i < 32; i++) {
        char path[160], level[32], type[32], size[32];
        snprintf(path, sizeof(path), "/sys/devices/system/cpu/cpu%d/cache/index%d/level", cpu, i);
        FILE *file = fopen(path, "r");
        if (!file) continue;
        int ok = fscanf(file, "%31s", level) == 1;
        fclose(file);
        snprintf(path, sizeof(path), "/sys/devices/system/cpu/cpu%d/cache/index%d/type", cpu, i);
        file = fopen(path, "r");
        if (!file) continue;
        ok = ok && fscanf(file, "%31s", type) == 1;
        fclose(file);
        snprintf(path, sizeof(path), "/sys/devices/system/cpu/cpu%d/cache/index%d/size", cpu, i);
        file = fopen(path, "r");
        if (!file) continue;
        ok = ok && fscanf(file, "%31s", size) == 1;
        fclose(file);
        if (ok) printf("L%s %s cache: %s\n", level, type, size);
    }
}

int main(int argc, char **argv)
{
    if (argc != 2 || (strcmp(argv[1], "--threads") && strcmp(argv[1], "--logical") && strcmp(argv[1], "--report"))) {
        fprintf(stderr, "usage: aios-hardware --threads|--logical|--report\n");
        return 2;
    }
    int logical, first_cpu;
    int cores = available_cores(&logical, &first_cpu);
    int quota = quota_threads();
    int threads = quota > 0 && quota < cores ? quota : cores;
    if (!strcmp(argv[1], "--threads")) {
        printf("%d\n", threads);
        return 0;
    }
    if (!strcmp(argv[1], "--logical")) {
        printf("%d\n", quota > 0 && quota < logical ? quota : logical);
        return 0;
    }
    printf("Logical CPUs in affinity: %d\nDetected physical cores: %d\n", logical, cores);
    if (quota) printf("cgroup CPU quota (whole cores): %d\n", quota);
    printf("Suggested inference threads: %d\n", threads);
    long pages = sysconf(_SC_AVPHYS_PAGES), page_size = sysconf(_SC_PAGESIZE);
    if (pages > 0 && page_size > 0)
        printf("Host available memory: %llu KiB\n", (unsigned long long)pages * (unsigned long long)page_size / 1024);
    print_cache(first_cpu);
    return 0;
}
