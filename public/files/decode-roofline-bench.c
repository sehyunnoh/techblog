// decode-roofline-bench.c: is LLM-style decoding limited by memory bandwidth?
//
// E1  peak read bandwidth (streaming sum over the whole buffer)
// E2  decode-like matrix-vector product over a buffer of fixed size, stored as
//     f32 / bf16 / int8 / int4. One pass over the buffer = one "token" of a model
//     whose weights occupy exactly that many bytes.
// E3  mixture-of-experts style reads: per token, read k randomly chosen experts of
//     size S, vs reading the same number of bytes contiguously, plus the cost of an
//     empty parallel region (the per-token synchronization floor).
//
// Build: gcc -O3 -march=native -fopenmp -o decode-roofline-bench decode-roofline-bench.c
// Needs AVX2 + FMA + AVX-VNNI (any recent Intel/AMD with avxvnni). Linux or WSL.
// Run:   ./decode-roofline-bench [-g GiB] [-r reps] [-t threads]
#define _GNU_SOURCE
#include <immintrin.h>
#include <omp.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define K 4096  // columns per row: the x vector fits in L1

static double now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec * 1e-9;
}
static int cmpd(const void *a, const void *b) {
    double x = *(const double *)a, y = *(const double *)b;
    return (x > y) - (x < y);
}
static double median(double *v, int n) {
    qsort(v, n, sizeof(double), cmpd);
    return v[n / 2];
}
static inline float hsum(__m256 v) {
    __m128 lo = _mm256_castps256_ps128(v), hi = _mm256_extractf128_ps(v, 1);
    lo = _mm_add_ps(lo, hi);
    lo = _mm_hadd_ps(lo, lo);
    lo = _mm_hadd_ps(lo, lo);
    return _mm_cvtss_f32(lo);
}
static inline int hsum_i(__m256i v) {
    __m128i lo = _mm256_castsi256_si128(v), hi = _mm256_extracti128_si256(v, 1);
    lo = _mm_add_epi32(lo, hi);
    lo = _mm_hadd_epi32(lo, lo);
    lo = _mm_hadd_epi32(lo, lo);
    return _mm_cvtsi128_si32(lo);
}

// ---- dot-product kernels: one row of K weights against x ------------------
static inline float dot_f32(const float *w, const float *x) {
    __m256 a0 = _mm256_setzero_ps(), a1 = a0, a2 = a0, a3 = a0;
    for (int i = 0; i < K; i += 32) {
        a0 = _mm256_fmadd_ps(_mm256_loadu_ps(w + i), _mm256_loadu_ps(x + i), a0);
        a1 = _mm256_fmadd_ps(_mm256_loadu_ps(w + i + 8), _mm256_loadu_ps(x + i + 8), a1);
        a2 = _mm256_fmadd_ps(_mm256_loadu_ps(w + i + 16), _mm256_loadu_ps(x + i + 16), a2);
        a3 = _mm256_fmadd_ps(_mm256_loadu_ps(w + i + 24), _mm256_loadu_ps(x + i + 24), a3);
    }
    return hsum(_mm256_add_ps(_mm256_add_ps(a0, a1), _mm256_add_ps(a2, a3)));
}
static inline __m256 bf16x8(const uint16_t *p) {
    __m256i v = _mm256_cvtepu16_epi32(_mm_loadu_si128((const __m128i *)p));
    return _mm256_castsi256_ps(_mm256_slli_epi32(v, 16));
}
static inline float dot_bf16(const uint16_t *w, const float *x) {
    __m256 a0 = _mm256_setzero_ps(), a1 = a0, a2 = a0, a3 = a0;
    for (int i = 0; i < K; i += 32) {
        a0 = _mm256_fmadd_ps(bf16x8(w + i), _mm256_loadu_ps(x + i), a0);
        a1 = _mm256_fmadd_ps(bf16x8(w + i + 8), _mm256_loadu_ps(x + i + 8), a1);
        a2 = _mm256_fmadd_ps(bf16x8(w + i + 16), _mm256_loadu_ps(x + i + 16), a2);
        a3 = _mm256_fmadd_ps(bf16x8(w + i + 24), _mm256_loadu_ps(x + i + 24), a3);
    }
    return hsum(_mm256_add_ps(_mm256_add_ps(a0, a1), _mm256_add_ps(a2, a3)));
}
static inline int dot_i8(const uint8_t *w, const int8_t *x) {
    __m256i a0 = _mm256_setzero_si256(), a1 = a0, a2 = a0, a3 = a0;
    for (int i = 0; i < K; i += 128) {
        a0 = _mm256_dpbusd_avx_epi32(a0, _mm256_loadu_si256((const __m256i *)(w + i)), _mm256_loadu_si256((const __m256i *)(x + i)));
        a1 = _mm256_dpbusd_avx_epi32(a1, _mm256_loadu_si256((const __m256i *)(w + i + 32)), _mm256_loadu_si256((const __m256i *)(x + i + 32)));
        a2 = _mm256_dpbusd_avx_epi32(a2, _mm256_loadu_si256((const __m256i *)(w + i + 64)), _mm256_loadu_si256((const __m256i *)(x + i + 64)));
        a3 = _mm256_dpbusd_avx_epi32(a3, _mm256_loadu_si256((const __m256i *)(w + i + 96)), _mm256_loadu_si256((const __m256i *)(x + i + 96)));
    }
    return hsum_i(_mm256_add_epi32(_mm256_add_epi32(a0, a1), _mm256_add_epi32(a2, a3)));
}
static inline int dot_i4(const uint8_t *w, const int8_t *x) {  // K/2 bytes per row
    const __m256i m = _mm256_set1_epi8(0x0F);
    __m256i a0 = _mm256_setzero_si256(), a1 = a0;
    for (int i = 0; i < K / 2; i += 64) {
        __m256i v0 = _mm256_loadu_si256((const __m256i *)(w + i));
        __m256i v1 = _mm256_loadu_si256((const __m256i *)(w + i + 32));
        __m256i lo0 = _mm256_and_si256(v0, m), hi0 = _mm256_and_si256(_mm256_srli_epi16(v0, 4), m);
        __m256i lo1 = _mm256_and_si256(v1, m), hi1 = _mm256_and_si256(_mm256_srli_epi16(v1, 4), m);
        const int8_t *xp = x + 2 * i;
        a0 = _mm256_dpbusd_avx_epi32(a0, lo0, _mm256_loadu_si256((const __m256i *)(xp)));
        a1 = _mm256_dpbusd_avx_epi32(a1, hi0, _mm256_loadu_si256((const __m256i *)(xp + 32)));
        a0 = _mm256_dpbusd_avx_epi32(a0, lo1, _mm256_loadu_si256((const __m256i *)(xp + 64)));
        a1 = _mm256_dpbusd_avx_epi32(a1, hi1, _mm256_loadu_si256((const __m256i *)(xp + 96)));
    }
    return hsum_i(_mm256_add_epi32(a0, a1));
}

// ---- plain streaming read of a byte range -----------------------------------
static inline uint64_t read_range(const uint8_t *p, size_t n) {
    __m256i a0 = _mm256_setzero_si256(), a1 = a0, a2 = a0, a3 = a0;
    for (size_t i = 0; i + 128 <= n; i += 128) {
        a0 = _mm256_add_epi64(a0, _mm256_loadu_si256((const __m256i *)(p + i)));
        a1 = _mm256_add_epi64(a1, _mm256_loadu_si256((const __m256i *)(p + i + 32)));
        a2 = _mm256_add_epi64(a2, _mm256_loadu_si256((const __m256i *)(p + i + 64)));
        a3 = _mm256_add_epi64(a3, _mm256_loadu_si256((const __m256i *)(p + i + 96)));
    }
    a0 = _mm256_add_epi64(_mm256_add_epi64(a0, a1), _mm256_add_epi64(a2, a3));
    uint64_t t[4];
    _mm256_storeu_si256((__m256i *)t, a0);
    return t[0] + t[1] + t[2] + t[3];
}

static uint64_t rng = 88172645463325252ULL;
static inline uint64_t xr(void) {
    rng ^= rng << 13;
    rng ^= rng >> 7;
    rng ^= rng << 17;
    return rng;
}

int main(int argc, char **argv) {
    double gib = 2.0;
    int reps = 7, threads = omp_get_max_threads();
    for (int i = 1; i < argc - 1; i++) {
        if (!strcmp(argv[i], "-g")) gib = atof(argv[i + 1]);
        if (!strcmp(argv[i], "-r")) reps = atoi(argv[i + 1]);
        if (!strcmp(argv[i], "-t")) threads = atoi(argv[i + 1]);
    }
    omp_set_num_threads(threads);
    size_t bytes = (size_t)(gib * 1073741824.0);
    bytes -= bytes % (size_t)(K * 4 * 64);  // whole rows for every format
    uint8_t *buf = aligned_alloc(4096, bytes);
    if (!buf) { fprintf(stderr, "alloc failed\n"); return 1; }
#pragma omp parallel for schedule(static)
    for (size_t i = 0; i < bytes / 8; i++) ((uint64_t *)buf)[i] = i * 0x9E3779B97F4A7C15ULL ^ (i >> 7);
    float *xf = aligned_alloc(64, K * sizeof(float));
    int8_t *xi = aligned_alloc(64, K);
    for (int i = 0; i < K; i++) { xf[i] = (float)((i * 7) % 13 - 6) * 0.01f; xi[i] = (int8_t)((i * 5) % 11 - 5); }
    // keep float weights finite and small: overwrite f32 view range with sane values
    {
        float *wf = (float *)buf;
#pragma omp parallel for schedule(static)
        for (size_t i = 0; i < bytes / 4; i++) wf[i] = (float)((int)(i % 17) - 8) * 0.001f;
    }

    printf("# threads=%d buffer=%.2f GiB (%zu bytes) K=%d reps=%d\n", threads, bytes / 1073741824.0, bytes, K, reps);

    // ---------------- E1: peak read bandwidth --------------------------------
    double t[64];
    uint64_t sink = 0;
    // dynamic scheduling: on hybrid CPUs a static split is paced by the slowest core
    const size_t BLK = 4u << 20;
    for (int r = -1; r < reps; r++) {
        double t0 = now();
        uint64_t s = 0;
#pragma omp parallel for schedule(dynamic, 1) reduction(+ : s)
        for (size_t b = 0; b < bytes / BLK; b++) s += read_range(buf + b * BLK, BLK);
        double dt = now() - t0;
        sink += s;
        if (r >= 0) t[r] = dt;
    }
    double e1 = median(t, reps);
    double peak = (double)bytes / e1 / 1e9;
    printf("E1 stream-read      median %.1f ms  %.1f GB/s\n", e1 * 1e3, peak);

    // ---------------- E2: decode-like GEMV per weight format -----------------
    printf("E2 %-8s %9s %8s %8s %9s %12s\n", "format", "bits/w", "ms/pass", "GB/s", "%stream", "Gweights/s");
    const char *names[4] = {"f32", "bf16", "int8", "int4"};
    double bpw[4] = {32, 16, 8, 4};
    for (int f = 0; f < 4; f++) {
        size_t rowbytes = (size_t)(K * bpw[f] / 8);
        size_t rows = bytes / rowbytes;
        float *y = calloc(rows, sizeof(float));
        for (int r = -1; r < reps; r++) {
            double t0 = now();
            size_t chunk = (1u << 20) / rowbytes;  // rows per ~1 MiB work unit
            if (chunk < 1) chunk = 1;
#pragma omp parallel for schedule(dynamic, chunk)
            for (size_t row = 0; row < rows; row++) {
                const uint8_t *w = buf + row * rowbytes;
                float v;
                switch (f) {
                    case 0: v = dot_f32((const float *)w, xf); break;
                    case 1: v = dot_bf16((const uint16_t *)w, xf); break;
                    case 2: v = (float)dot_i8(w, xi); break;
                    default: v = (float)dot_i4(w, xi); break;
                }
                y[row] = v;
            }
            double dt = now() - t0;
            if (r >= 0) t[r] = dt;
        }
        double m = median(t, reps), bw = (double)bytes / m / 1e9;
        double acc = 0;
        for (size_t i = 0; i < rows; i += rows / 64 + 1) acc += y[i];
        sink += (uint64_t)(acc > 0 ? 1 : 0);
        printf("E2 %-8s %9.0f %8.1f %8.1f %8.0f%% %12.1f\n", names[f], bpw[f], m * 1e3, bw, 100.0 * bw / peak, (double)bytes * 8 / bpw[f] / m / 1e9);
        free(y);
    }

    // ---------------- E3: mixture-of-experts style reads ---------------------
    // empty parallel region cost (per-token synchronization floor)
    {
        int n = 20000;
        double t0 = now();
        for (int i = 0; i < n; i++) {
#pragma omp parallel
            { sink += omp_get_thread_num() == 0; }
        }
        printf("E3 empty parallel region: %.2f us each\n", (now() - t0) / n * 1e6);
    }
    printf("E3 %-9s %6s %12s %12s %11s %11s\n", "expert", "k", "scatter_us", "contig_us", "scatter_GBs", "contig_GBs");
    size_t sizes[] = {64 << 10, 256 << 10, 1 << 20, 4 << 20, 16 << 20};
    int k = 8;
    for (int si = 0; si < 5; si++) {
        size_t S = sizes[si];
        size_t nexp = bytes / S;
        int tokens = (int)((256ULL << 20) / (S * k));  // about 256 MiB of reads per timing run
        if (tokens < 200) tokens = 200;
        if (tokens > 20000) tokens = 20000;
        size_t *pick = malloc(sizeof(size_t) * k * tokens);
        for (int i = 0; i < k * tokens; i++) pick[i] = xr() % nexp;
        double ts[16], tc[16];
        for (int r = -1; r < 7; r++) {
            double t0 = now();
            for (int tk = 0; tk < tokens; tk++) {
                // each expert is cut into 16 pieces, handed out dynamically
                uint64_t s = 0;
                size_t piece = S / 16;
#pragma omp parallel for schedule(dynamic, 1) reduction(+ : s)
                for (int u = 0; u < k * 16; u++)
                    s += read_range(buf + pick[tk * k + u / 16] * S + (size_t)(u % 16) * piece, piece);
                sink += s;
            }
            double dt = now() - t0;
            double t1 = now();
            for (int tk = 0; tk < tokens; tk++) {
                // same number of pieces, same bytes, but one contiguous region
                uint64_t s = 0;
                size_t piece = S / 16;
                size_t base = (pick[tk * k] * S) % (bytes - (size_t)k * S);
#pragma omp parallel for schedule(dynamic, 1) reduction(+ : s)
                for (int u = 0; u < k * 16; u++) s += read_range(buf + base + (size_t)u * piece, piece);
                sink += s;
            }
            double dc = now() - t1;
            if (r >= 0) { ts[r] = dt / tokens; tc[r] = dc / tokens; }
        }
        double ms = median(ts, 7), mc = median(tc, 7);
        double moved = (double)k * S;
        printf("E3 %-9zu %6d %12.1f %12.1f %11.1f %11.1f\n", S, k, ms * 1e6, mc * 1e6, moved / ms / 1e9, moved / mc / 1e9);
        free(pick);
    }
    printf("# checksum %llu\n", (unsigned long long)sink);
    return 0;
}
