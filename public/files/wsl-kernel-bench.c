// WSL kernel microbenchmarks: syscall, pipe ping-pong, memcpy (cold/warm).
// Usage: ./bench <name>   names: syscall pipe memcpy_warm memcpy_cold
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <sys/syscall.h>
#include <sys/mman.h>
#include <sys/wait.h>

static double now(void) {
    struct timespec t;
    clock_gettime(CLOCK_MONOTONIC, &t);
    return t.tv_sec + t.tv_nsec * 1e-9;
}

int main(int argc, char **argv) {
    if (argc < 2) return 1;
    if (!strcmp(argv[1], "syscall")) {
        long n = 5000000;
        double t0 = now();
        for (long i = 0; i < n; i++) syscall(SYS_getppid);
        double dt = now() - t0;
        printf("%.0f ops/s\n", n / dt);
    } else if (!strcmp(argv[1], "pipe")) {
        // two processes bounce one byte through two pipes, like perf bench sched pipe
        int a[2], b[2];
        long n = 500000;
        pipe(a); pipe(b);
        char c = 'x';
        if (fork() == 0) {
            for (long i = 0; i < n; i++) { read(a[0], &c, 1); write(b[1], &c, 1); }
            _exit(0);
        }
        double t0 = now();
        for (long i = 0; i < n; i++) { write(a[1], &c, 1); read(b[0], &c, 1); }
        double dt = now() - t0;
        wait(NULL);
        printf("%.0f round-trips/s %.3f us/roundtrip\n", n / dt, dt / n * 1e6);
    } else if (!strcmp(argv[1], "memcpy_warm") || !strcmp(argv[1], "memcpy_cold")) {
        size_t sz = 1UL << 30;
        int cold = !strcmp(argv[1], "memcpy_cold");
        char *src = mmap(NULL, sz, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        char *dst = mmap(NULL, sz, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
        memset(src, 1, sz);               // source always touched
        if (!cold) memset(dst, 2, sz);    // warm: destination pages already faulted in
        int reps = cold ? 1 : 5;
        double t0 = now();
        for (int i = 0; i < reps; i++) memcpy(dst, src, sz);
        double dt = now() - t0;
        printf("%.2f GB/s\n", (double)sz * reps / dt / 1e9);
    }
    return 0;
}
