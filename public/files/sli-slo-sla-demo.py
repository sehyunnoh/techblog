"""Three small calculations behind the SLI / SLO / SLA guide. Standard library only.
Run it: python sli-slo-sla-demo.py

1. Allowed downtime per 30-day month for common availability targets (arithmetic).
2. A synthetic latency sample, to show why a mean hides what a percentile or a
   good-events ratio shows. The data is generated, not measured from a real service.
3. Where outage minutes land against the 99.99% line and the AWS EC2 Region-Level SLA tiers.
"""
import random
import statistics

MONTH_MIN = 30 * 24 * 60


def downtime_table():
    print("1. Allowed downtime in a 30-day month (43,200 minutes)")
    print(f"{'target':>9} {'budget':>8} {'minutes':>9}")
    for t in [99.0, 99.5, 99.9, 99.95, 99.99, 99.999]:
        m = MONTH_MIN * (1 - t / 100)
        print(f"{t:>8}% {100 - t:>7.3f}% {m:>9.2f}  ({m * 60:,.0f} s)")


def latency_sample():
    rnd = random.Random(7)
    n = 100_000
    lat = []
    for _ in range(n):
        if rnd.random() < 0.02:
            lat.append(rnd.uniform(1500, 3000))
        else:
            lat.append(rnd.lognormvariate(4.4, 0.35))
    lat.sort()
    pct = lambda p: lat[int(p / 100 * n) - 1]
    good = sum(1 for x in lat if x <= 300)
    print("\n2. Synthetic latency sample, 100,000 requests, 2% of them slow (1.5 to 3 s)")
    print(f"   mean   {statistics.fmean(lat):7.1f} ms")
    print(f"   p50    {pct(50):7.1f} ms")
    print(f"   p95    {pct(95):7.1f} ms")
    print(f"   p99    {pct(99):7.1f} ms")
    print(f"   SLI = requests under 300 ms / all requests = {good / n:.4f}  ({100 * good / n:.2f}%)")


def tiers(uptime):
    if uptime >= 99.99:
        return "0%"
    if uptime >= 99.0:
        return "10%"
    if uptime >= 95.0:
        return "30%"
    return "100%"


def outage_table():
    print("\n3. One 30-day month with a single full outage")
    print(f"{'outage min':>10} {'uptime':>9} {'meets 99.99%':>15} {'EC2 Region-Level credit':>24}")
    for m in [2, 4, 10, 44, 432, 440, 2160, 2200]:
        up = 100 * (1 - m / MONTH_MIN)
        print(f"{m:>10g} {up:>8.3f}% {'yes' if up >= 99.99 else 'no':>15} {tiers(up):>24}")


if __name__ == "__main__":
    downtime_table()
    latency_sample()
    outage_table()
