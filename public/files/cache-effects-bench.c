// Re-run of the experiments in Igor Ostrovsky's "Gallery of Processor Cache Effects" (2010), in C.
// Build: gcc -O2 -fno-tree-vectorize bench.c -o bench.exe
#define _WIN32_WINNT 0x0601
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

static double now_ms(void) {
    static LARGE_INTEGER f;
    LARGE_INTEGER c;
    if (!f.QuadPart) QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&c);
    return 1000.0 * (double)c.QuadPart / (double)f.QuadPart;
}

static int cmp_d(const void *a, const void *b) {
    double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}
static double median(double *v, int n) { qsort(v, n, sizeof *v, cmp_d); return v[n / 2]; }

static void *alloc64(size_t bytes) { return _aligned_malloc(bytes, 4096); }

// ---- topology: print efficiency class per logical processor
static void topology(void) {
    DWORD len = 0;
    GetLogicalProcessorInformationEx(RelationProcessorCore, NULL, &len);
    char *buf = malloc(len);
    GetLogicalProcessorInformationEx(RelationProcessorCore, (PSYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX)buf, &len);
    for (DWORD off = 0; off < len;) {
        PSYSTEM_LOGICAL_PROCESSOR_INFORMATION_EX p = (void *)(buf + off);
        printf("core: efficiency_class=%d mask=0x%llx\n", p->Processor.EfficiencyClass,
               (unsigned long long)p->Processor.GroupMask[0].Mask);
        off += p->Size;
    }
    free(buf);
}

// ---- Exp 1/2: stride K over a 64M-int array, multiply touched elements by 3
static void exp_stride(void) {
    const size_t N = 64u * 1024 * 1024;
    int *a = alloc64(N * sizeof(int));
    for (size_t i = 0; i < N; i++) a[i] = (int)i;
    printf("exp,k,ms,touched\n");
    for (int k = 1; k <= 1024; k *= 2) {
        double t[9];
        for (int r = 0; r < 9; r++) {
            double s = now_ms();
            for (size_t i = 0; i < N; i += k) a[i] *= 3;
            t[r] = now_ms() - s;
        }
        printf("stride,%d,%.2f,%zu\n", k, median(t, 9), N / k);
    }
}

// ---- Exp 3: working-set sweep. (a) original pattern: sequential, one touch per 64B line.
//      (b) random pointer chase, one node per line.
static void exp_sweep(void) {
    printf("exp,bytes,ns_per_access\n");
    const long steps = 64L * 1024 * 1024;
    for (int lg = 12; lg <= 28; lg++) {
        size_t bytes = (size_t)1 << lg;
        // (a) sequential
        int *a = alloc64(bytes);
        memset(a, 0, bytes);
        size_t mask = bytes / sizeof(int) - 1;
        double t[5];
        for (int r = 0; r < 5; r++) {
            double s = now_ms();
            for (long i = 0; i < steps; i++) a[((size_t)i * 16) & mask]++;
            t[r] = now_ms() - s;
        }
        printf("seq,%zu,%.3f\n", bytes, median(t, 5) * 1e6 / steps);
        _aligned_free(a);

        // (b) pointer chase: random cycle over 64-byte lines
        size_t lines = bytes / 64;
        char *m = alloc64(bytes);
        uint32_t *perm = malloc(lines * sizeof(uint32_t));
        for (size_t i = 0; i < lines; i++) perm[i] = (uint32_t)i;
        srand(12345);
        for (size_t i = lines - 1; i > 0; i--) {   // Sattolo: one single cycle
            size_t j = ((size_t)rand() * 32768 + rand()) % i;
            uint32_t tmp = perm[i]; perm[i] = perm[j]; perm[j] = tmp;
        }
        for (size_t i = 0; i < lines; i++) *(uint32_t *)(m + (size_t)perm[i] * 64) = perm[(i + 1) % lines];
        // perm is now a cycle by position; build next pointers so chain visits every line once
        for (size_t i = 0; i < lines; i++) *(uint32_t *)(m + i * 64) = perm[i];
        long csteps = bytes <= (1u << 24) ? 32L * 1024 * 1024 : 8L * 1024 * 1024;
        double tc[5];
        for (int r = 0; r < 5; r++) {
            uint32_t p = 0;
            double s = now_ms();
            for (long i = 0; i < csteps; i++) p = *(volatile uint32_t *)(m + (size_t)p * 64);
            tc[r] = now_ms() - s;
            if (p == 0xFFFFFFFFu) puts("");
        }
        printf("chase,%zu,%.3f\n", bytes, median(tc, 5) * 1e6 / csteps);
        free(perm);
        _aligned_free(m);
        fflush(stdout);
    }
}

// ---- Compute-only control: same 64M multiply-by-3 iterations, but on a 16 KB array that stays in L1
static void exp_compute(void) {
    const size_t N = 4096;
    int *a = alloc64(N * sizeof(int));
    for (size_t i = 0; i < N; i++) a[i] = (int)i;
    volatile int k = 1;  // runtime stride, like the main experiment
    double t[9];
    for (int r = 0; r < 9; r++) {
        double s = now_ms();
        for (int rep = 0; rep < 16384; rep++)
            for (size_t i = 0; i < N; i += k) a[i] *= 3;
        t[r] = now_ms() - s;
    }
    printf("exp,ms,iterations\ncompute_l1,%.2f,%zu\n", median(t, 9), (size_t)N * 16384);
}

// ---- Fine sweep: pointer chase only, non-power-of-two sizes (KB)
static void exp_fine(void) {
    static const int kb[] = {16, 24, 32, 40, 48, 56, 64, 96, 128, 256, 512, 1024, 1536, 2048, 2560, 3072, 3584, 4096,
                             6144, 8192, 10240, 12288, 14336, 16384, 20480, 24576, 32768};
    printf("exp,kb,ns_per_access\n");
    for (size_t k = 0; k < sizeof kb / sizeof *kb; k++) {
        size_t bytes = (size_t)kb[k] * 1024, lines = bytes / 64;
        char *m = alloc64(bytes);
        uint32_t *perm = malloc(lines * sizeof(uint32_t));
        for (size_t i = 0; i < lines; i++) perm[i] = (uint32_t)i;
        srand(12345);
        for (size_t i = lines - 1; i > 0; i--) {
            size_t j = ((size_t)rand() * 32768 + rand()) % i;
            uint32_t tmp = perm[i]; perm[i] = perm[j]; perm[j] = tmp;
        }
        for (size_t i = 0; i < lines; i++) *(uint32_t *)(m + i * 64) = perm[i];
        long csteps = bytes <= (1u << 24) ? 32L * 1024 * 1024 : 8L * 1024 * 1024;
        double tc[7];
        for (int r = 0; r < 7; r++) {
            uint32_t p = 0;
            double s = now_ms();
            for (long i = 0; i < csteps; i++) p = *(volatile uint32_t *)(m + (size_t)p * 64);
            tc[r] = now_ms() - s;
            if (p == 0xFFFFFFFFu) puts("");
        }
        printf("chase,%d,%.3f\n", kb[k], median(tc, 7) * 1e6 / csteps);
        free(perm);
        _aligned_free(m);
        fflush(stdout);
    }
}

// ---- Exp 4: instruction-level parallelism through memory
static void exp_ilp(void) {
    volatile int *a = alloc64(64);
    a[0] = a[1] = 0;
    const long n = 500L * 1000 * 1000;
    printf("exp,variant,ms\n");
    double t1[7], t2[7];
    for (int r = 0; r < 7; r++) {
        double s = now_ms();
        for (long i = 0; i < n; i++) { a[0]++; a[0]++; }
        t1[r] = now_ms() - s;
        s = now_ms();
        for (long i = 0; i < n; i++) { a[0]++; a[1]++; }
        t2[r] = now_ms() - s;
    }
    printf("ilp,same_slot,%.1f\n", median(t1, 7));
    printf("ilp,two_slots,%.1f\n", median(t2, 7));
}

// ---- Exp 6: false sharing
typedef struct { volatile int *p; long n; int cpu; } Job;
static DWORD WINAPI worker(LPVOID arg) {
    Job *j = arg;
    SetThreadAffinityMask(GetCurrentThread(), (DWORD_PTR)1 << j->cpu);
    for (long i = 0; i < j->n; i++) (*j->p)++;
    return 0;
}
static double run_fs(int stride_ints, int nthreads, const int *cpus) {
    volatile int *buf = alloc64(4096);
    memset((void *)buf, 0, 4096);
    HANDLE h[8]; Job jobs[8];
    const long n = 100L * 1000 * 1000;
    double s = now_ms();
    for (int t = 0; t < nthreads; t++) {
        jobs[t] = (Job){ buf + (size_t)t * stride_ints, n, cpus[t] };
        h[t] = CreateThread(NULL, 0, worker, &jobs[t], 0, NULL);
    }
    WaitForMultipleObjects(nthreads, h, TRUE, INFINITE);
    double e = now_ms() - s;
    for (int t = 0; t < nthreads; t++) CloseHandle(h[t]);
    _aligned_free((void *)buf);
    return e;
}
static void exp_fs(const int *cpus, int ncpu) {
    printf("exp,layout,threads,ms\n");
    for (int nt = 1; nt <= ncpu && nt <= 4; nt++) {
        double a[5], b[5];
        for (int r = 0; r < 5; r++) { a[r] = run_fs(1, nt, cpus); b[r] = run_fs(16, nt, cpus); }
        printf("fs,adjacent,%d,%.1f\n", nt, median(a, 5));
        printf("fs,padded,%d,%.1f\n", nt, median(b, 5));
        fflush(stdout);
    }
}

int main(int argc, char **argv) {
    if (argc < 2) { puts("usage: bench topo|stride|sweep|ilp|fs cpu0,cpu1,..."); return 1; }
    SetPriorityClass(GetCurrentProcess(), HIGH_PRIORITY_CLASS);
    int cpus[8] = {0, 1, 2, 3}, ncpu = 4;
    if (argc > 2) { ncpu = 0; for (char *t = strtok(argv[2], ","); t && ncpu < 8; t = strtok(NULL, ",")) cpus[ncpu++] = atoi(t); }
    if (strcmp(argv[1], "topo") == 0) { topology(); return 0; }
    SetThreadAffinityMask(GetCurrentThread(), (DWORD_PTR)1 << cpus[0]);
    if (!strcmp(argv[1], "stride")) exp_stride();
    else if (!strcmp(argv[1], "sweep")) exp_sweep();
    else if (!strcmp(argv[1], "fine")) exp_fine();
    else if (!strcmp(argv[1], "compute")) exp_compute();
    else if (!strcmp(argv[1], "ilp")) exp_ilp();
    else if (!strcmp(argv[1], "fs")) exp_fs(cpus, ncpu);
    return 0;
}
