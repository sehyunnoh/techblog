// Measuring "push ifs up, push fors down" (matklad, 2023) in C.
// Build: gcc -O2 bench2.c -o bench2_O2.exe   and   gcc -O3 bench2.c -o bench2_O3.exe
#define _WIN32_WINNT 0x0601
#include <windows.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>

#ifndef OPT
#define OPT "?"
#endif

static double now_ms(void) {
    static LARGE_INTEGER f;
    LARGE_INTEGER c;
    if (!f.QuadPart) QueryPerformanceFrequency(&f);
    QueryPerformanceCounter(&c);
    return 1000.0 * (double)c.QuadPart / (double)f.QuadPart;
}
static int cmp_d(const void *a, const void *b) { double x = *(const double *)a, y = *(const double *)b; return (x > y) - (x < y); }
static double median(double *v, int n) { qsort(v, n, sizeof *v, cmp_d); return v[n / 2]; }
static uint32_t rng_state = 2463534242u;
static uint32_t rnd(void) { rng_state ^= rng_state << 13; rng_state ^= rng_state >> 17; rng_state ^= rng_state << 5; return rng_state; }
static volatile long sink;

// ------------------------------------------------------------------ E1: loop-invariant if
__attribute__((noinline)) void e1_inside(int *a, int n, int flag, int x, int y) {
    for (int i = 0; i < n; i++) { if (flag) a[i] += x; else a[i] -= y; }
}
__attribute__((noinline)) void e1_hoisted(int *a, int n, int flag, int x, int y) {
    if (flag) { for (int i = 0; i < n; i++) a[i] += x; }
    else      { for (int i = 0; i < n; i++) a[i] -= y; }
}
static void run_e1(void) {
    printf("exp,variant,opt,n_ints,ns_per_elem\n");
    volatile int flag = 1;
    int sizes[2] = {1024, 16 * 1024 * 1024};
    for (int s = 0; s < 2; s++) {
        int n = sizes[s];
        long total = 512L * 1000 * 1000;
        long reps = total / n;
        int *a = _aligned_malloc((size_t)n * sizeof(int), 64);
        memset(a, 0, (size_t)n * sizeof(int));
        for (int v = 0; v < 2; v++) {
            double t[5];
            for (int r = 0; r < 5; r++) {
                double st = now_ms();
                for (long k = 0; k < reps; k++) (v ? e1_hoisted : e1_inside)(a, n, flag, 3, 5);
                t[r] = now_ms() - st;
            }
            printf("e1,%s,%s,%d,%.4f\n", v ? "hoisted" : "inside", OPT, n, median(t, 5) * 1e6 / (double)(reps * n));
        }
        sink += a[0];
        _aligned_free(a);
    }
}

// ------------------------------------------------------------------ E2: per-call and per-lock overhead
__attribute__((noinline)) int scale1(int x) { return x * 3 + 1; }
__attribute__((noinline)) void scale_batch(int *a, int n) { for (int i = 0; i < n; i++) a[i] = a[i] * 3 + 1; }
static void run_e2(void) {
    printf("exp,variant,opt,batch,ns_per_elem\n");
    const int n = 4096;
    int *a = _aligned_malloc(n * sizeof(int), 64);
    for (int i = 0; i < n; i++) a[i] = i;
    const long reps = 100000;  // 409.6M element ops
    double t[5];
    for (int r = 0; r < 5; r++) {
        double st = now_ms();
        for (long k = 0; k < reps; k++) for (int i = 0; i < n; i++) a[i] = scale1(a[i]);
        t[r] = now_ms() - st;
    }
    printf("e2call,call_per_element,%s,1,%.4f\n", OPT, median(t, 5) * 1e6 / ((double)reps * n));
    for (int r = 0; r < 5; r++) {
        double st = now_ms();
        for (long k = 0; k < reps; k++) scale_batch(a, n);
        t[r] = now_ms() - st;
    }
    printf("e2call,one_batch_call,%s,%d,%.4f\n", OPT, n, median(t, 5) * 1e6 / ((double)reps * n));
    sink += a[5];

    // lock amortization: one SRWLOCK acquire per `b` elements
    SRWLOCK lock = SRWLOCK_INIT;
    volatile int *cnt = _aligned_malloc(4096 * sizeof(int), 64);
    memset((void *)cnt, 0, 4096 * sizeof(int));
    const long total = 100L * 1000 * 1000;
    int bs[] = {1, 2, 4, 8, 16, 64, 256, 4096};
    for (size_t bi = 0; bi < sizeof bs / sizeof *bs; bi++) {
        int b = bs[bi];
        for (int r = 0; r < 5; r++) {
            double st = now_ms();
            for (long i = 0; i < total; i += b) {
                AcquireSRWLockExclusive(&lock);
                for (int j = 0; j < b; j++) cnt[(i + j) & 4095]++;
                ReleaseSRWLockExclusive(&lock);
            }
            t[r] = now_ms() - st;
        }
        printf("e2lock,lock_per_batch,%s,%d,%.4f\n", OPT, b, median(t, 5) * 1e6 / (double)total);
    }
    _aligned_free(a);
}

// ------------------------------------------------------------------ E3: fused filter+work vs filter then batch
static inline uint32_t heavy(uint32_t x, int k) {
    uint32_t h = x;
    for (int i = 0; i < k; i++) h = h * 2654435761u + 12345u;
    return h >> 3;
}
static uint64_t fused(const uint32_t *a, long n, uint32_t thr, int k) {
    uint64_t s = 0;
    for (long i = 0; i < n; i++) if (a[i] < thr) s += heavy(a[i], k);
    return s;
}
static uint64_t mat_branch(const uint32_t *a, long n, uint32_t thr, int k, uint32_t *buf) {
    long m = 0;
    for (long i = 0; i < n; i++) if (a[i] < thr) buf[m++] = a[i];
    uint64_t s = 0;
    for (long j = 0; j < m; j++) s += heavy(buf[j], k);
    return s;
}
static uint64_t mat_branchless(const uint32_t *a, long n, uint32_t thr, int k, uint32_t *buf) {
    long m = 0;
    for (long i = 0; i < n; i++) { buf[m] = a[i]; m += a[i] < thr; }
    uint64_t s = 0;
    for (long j = 0; j < m; j++) s += heavy(buf[j], k);
    return s;
}
static void run_e3(void) {
    printf("exp,variant,opt,n_ints,work_k,selectivity_pct,ns_per_input_elem\n");
    long sizes[2] = {64 * 1024, 64L * 1024 * 1024};
    int ks[2] = {1, 16};
    int sels[4] = {1, 10, 50, 90};
    for (int si = 0; si < 2; si++) {
        long n = sizes[si];
        uint32_t *a = _aligned_malloc((size_t)n * 4, 64), *buf = _aligned_malloc((size_t)n * 4, 64);
        for (long i = 0; i < n; i++) a[i] = rnd() % 100;
        memset(buf, 0, (size_t)n * 4);
        long reps = si == 0 ? 2000 : 2;
        for (int ki = 0; ki < 2; ki++) for (int pi = 0; pi < 4; pi++) {
            uint32_t thr = (uint32_t)sels[pi];
            for (int v = 0; v < 3; v++) {
                double t[5];
                uint64_t acc = 0;
                for (int r = 0; r < 5; r++) {
                    double st = now_ms();
                    for (long q = 0; q < reps; q++)
                        acc += v == 0 ? fused(a, n, thr, ks[ki]) : v == 1 ? mat_branch(a, n, thr, ks[ki], buf) : mat_branchless(a, n, thr, ks[ki], buf);
                    t[r] = now_ms() - st;
                }
                sink += (long)acc;
                printf("e3,%s,%s,%ld,%d,%d,%.4f\n", v == 0 ? "fused" : v == 1 ? "materialize_branch" : "materialize_branchless",
                       OPT, n, ks[ki], sels[pi], median(t, 5) * 1e6 / ((double)reps * n));
            }
            fflush(stdout);
        }
        _aligned_free(a); _aligned_free(buf);
    }
}

// ------------------------------------------------------------------ E4: control, same filter on sorted (predictable) vs random input
static int cmp_u(const void *a, const void *b) { uint32_t x = *(const uint32_t *)a, y = *(const uint32_t *)b; return (x > y) - (x < y); }
static void run_e4(void) {
    printf("exp,variant,opt,input,ns_per_input_elem\n");
    long n = 64 * 1024;
    volatile uint32_t vthr = 50; volatile int vk = 1;  // runtime values so the compiler cannot specialize the loops
    uint32_t thr = vthr; int kk = vk;
    uint32_t *a = _aligned_malloc((size_t)n * 4, 64), *buf = _aligned_malloc((size_t)n * 4, 64);
    memset(buf, 0, (size_t)n * 4);
    for (int sorted = 0; sorted < 2; sorted++) {
        for (long i = 0; i < n; i++) a[i] = rnd() % 100;
        if (sorted) qsort(a, (size_t)n, 4, cmp_u);
        for (int v = 0; v < 3; v++) {
            double t[5]; uint64_t acc = 0;
            for (int r = 0; r < 5; r++) {
                double st = now_ms();
                for (long q = 0; q < 2000; q++)
                    acc += v == 0 ? fused(a, n, thr, kk) : v == 1 ? mat_branch(a, n, thr, kk, buf) : mat_branchless(a, n, thr, kk, buf);
                t[r] = now_ms() - st;
            }
            sink += (long)acc;
            printf("e4,%s,%s,%s,%.4f\n", v == 0 ? "fused" : v == 1 ? "materialize_branch" : "materialize_branchless", OPT,
                   sorted ? "sorted" : "random", median(t, 5) * 1e6 / (2000.0 * n));
        }
    }
}

int main(int argc, char **argv) {
    SetPriorityClass(GetCurrentProcess(), HIGH_PRIORITY_CLASS);
    SetThreadAffinityMask(GetCurrentThread(), 1);  // logical processor 0 = performance core on this machine
    if (argc < 2) return 1;
    if (!strcmp(argv[1], "e1")) run_e1();
    else if (!strcmp(argv[1], "e2")) run_e2();
    else if (!strcmp(argv[1], "e3")) run_e3();
    else if (!strcmp(argv[1], "e4")) run_e4();
    return 0;
}
