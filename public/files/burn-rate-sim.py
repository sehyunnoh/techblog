"""Burn-rate alerting simulation for a 99.9% SLO over a 30-day window.
Run it: python burn-rate-sim.py   (needs numpy)

Traffic is simulated in 1-minute buckets: requests ~ Poisson(60 * qps),
errors ~ Binomial(requests, error_rate). Every alert is evaluated once per
minute on ratios of sums over the trailing window (error increase divided by
request increase, like a Prometheus recording rule). A window with zero
requests gives no value, so that condition is false.

Rules compared (SLO error budget p0 = 0.001, 30 days = 43,200 minutes):
  MWMB  multiwindow multi-burn-rate page rules from the Google SRE Workbook,
        table 5-8:  (1h and 5m both > 14.4x)  or  (6h and 30m both > 6x)
  LONG  the same two long windows alone, no short-window condition
  TEN   "error ratio over 10 minutes >= SLO threshold" (workbook approach 1)
"""
import sys
import numpy as np

P0 = 0.001
MONTH = 43_200
RNG = np.random.default_rng(20261022)


def roll(x, w):
    c = np.concatenate(([0.0], np.cumsum(x, dtype=np.float64)))
    out = np.zeros(len(x))
    out[w - 1:] = c[w:] - c[:-w] if len(x) >= w else 0
    for i in range(min(w - 1, len(x))):
        out[i] = c[i + 1]
    return out


def ratio(err, req, w):
    e, r = roll(err, w), roll(req, w)
    with np.errstate(divide="ignore", invalid="ignore"):
        v = np.where(r > 0, e / r, np.nan)
    return v


def gt(v, thr):
    with np.errstate(invalid="ignore"):
        return np.nan_to_num(v, nan=-1.0) > thr


def rules(err, req, min_err=0):
    b1h, b5m = ratio(err, req, 60), ratio(err, req, 5)
    b6h, b30m = ratio(err, req, 360), ratio(err, req, 30)
    t10 = ratio(err, req, 10)
    mw = (gt(b1h, 14.4 * P0) & gt(b5m, 14.4 * P0)) | (gt(b6h, 6 * P0) & gt(b30m, 6 * P0))
    if min_err:
        enough = roll(err, 60) >= min_err
        mw = mw & enough
    lg = gt(b1h, 14.4 * P0) | gt(b6h, 6 * P0)
    ten = np.nan_to_num(t10, nan=-1.0) >= P0
    return {"MWMB": mw, "LONG": lg, "TEN": ten}


def episodes(fire):
    return int(np.sum(fire[1:] & ~fire[:-1]) + (1 if fire[0] else 0))


def traffic(qps, minutes, p):
    req = RNG.poisson(60 * qps, minutes)
    err = RNG.binomial(req, p)
    return err.astype(float), req.astype(float)


def e1_false_pages(p, months=24):
    print(f"\nE1: pages per 30 days while the service really runs at error rate {p:.4f} "
          f"(burn rate {p / P0:.2f}x), {months} simulated months per row")
    print(f"{'qps':>8} {'req/5min':>9} {'errors/mo':>10} {'MWMB':>8} {'LONG':>8} {'TEN':>8}  {'MWMB firing %':>13}")
    for qps in [0.003, 0.01, 0.03, 0.1, 0.3, 1, 3, 10, 100]:
        err, req = traffic(qps, MONTH * months, p)
        f = rules(err, req)
        row = {k: episodes(v) / months for k, v in f.items()}
        print(f"{qps:>8g} {300 * qps:>9.1f} {err.sum() / months:>10.0f} {row['MWMB']:>8.2f} {row['LONG']:>8.2f} "
              f"{row['TEN']:>8.1f}  {100 * f['MWMB'].mean():>12.2f}%")


def fluid_series(minutes, outage_start, outage_len, e, qps=1000.0, bg=0.0):
    req = np.full(minutes, 60 * qps)
    err = np.full(minutes, 60 * qps * bg)
    err[outage_start:outage_start + outage_len] = 60 * qps * e
    return err, req


def e2_detection():
    print("\nE2: minutes from outage start to first page (steady 1000 qps, no background errors),")
    print("    and the share of the 30-day budget burned by then")
    print(f"{'error rate':>10} {'burn':>7} {'MWMB min':>9} {'budget %':>9} {'TEN min':>8} {'LONG min':>9}")
    for e in [0.001, 0.002, 0.005, 0.0072, 0.01, 0.0144, 0.02, 0.05, 0.1, 0.5, 1.0]:
        err, req = fluid_series(3000, 400, 2000, e)
        f = rules(err, req)
        cells = []
        for k in ("MWMB", "TEN", "LONG"):
            idx = np.nonzero(f[k][400:])[0]
            cells.append(None if len(idx) == 0 else int(idx[0]) + 1)
        burned = None if cells[0] is None else 100 * (e / P0) * cells[0] / MONTH
        fmt = lambda v: "never" if v is None else str(v)
        b = "-" if burned is None else f"{burned:.2f}"
        print(f"{e:>10.4f} {e / P0:>6.1f}x {fmt(cells[0]):>9} {b:>9} {fmt(cells[1]):>8} {fmt(cells[2]):>9}")


def e3_reset():
    print("\nE3: minutes the page stays on after a short full outage ends (steady 1000 qps)")
    print(f"{'outage min':>10} {'MWMB firing':>12} {'LONG firing':>12} {'TEN firing':>11}")
    for d in [1, 2, 5, 10, 30, 60]:
        err, req = fluid_series(3000, 400, d, 1.0)
        f = rules(err, req)
        print(f"{d:>10} " + " ".join(f"{int(f[k].sum()):>{w}}" for k, w in
                                      (("MWMB", 12), ("LONG", 12), ("TEN", 11))))


def e4_low_traffic_detection(trials=300):
    print("\nE4: real 100% outage on a low-traffic service: minutes until MWMB pages (median / p90 / never in 6h)")
    print(f"{'qps':>8} {'median':>8} {'p90':>6} {'never':>6}")
    for qps in [0.003, 0.01, 0.03, 0.1, 1]:
        times = []
        for _ in range(trials):
            req = RNG.poisson(60 * qps, 1200).astype(float)
            err = np.zeros(1200)
            err[600:] = req[600:]
            f = rules(err, req)["MWMB"][600:960]
            idx = np.nonzero(f)[0]
            times.append(idx[0] + 1 if len(idx) else np.inf)
        t = np.array(times)
        med = np.median(t)
        p90 = np.percentile(t, 90)
        print(f"{qps:>8g} {med:>8.0f} {p90:>6.0f} {int((~np.isfinite(t)).sum()):>6}")


def e5_guard(trials=300, months=24):
    print("\nE5: MWMB plus a floor on errors in the trailing hour (page only if hour has >= k errors)")
    print("    left: pages per 30 days at error rate 0.001; right: median minutes to page on a real 100% outage")
    print(f"{'qps':>8} {'k':>3} {'pages/mo':>9} {'median min':>11} {'p90':>6} {'never':>6}")
    for qps in [0.01, 0.03, 0.1]:
        for k in [0, 2, 3, 5]:
            err, req = traffic(qps, MONTH * months, P0)
            pages = episodes(rules(err, req, k)["MWMB"]) / months
            times = []
            for _ in range(trials):
                rq = RNG.poisson(60 * qps, 1200).astype(float)
                er = np.zeros(1200)
                er[600:] = rq[600:]
                idx = np.nonzero(rules(er, rq, k)["MWMB"][600:960])[0]
                times.append(idx[0] + 1 if len(idx) else np.inf)
            t = np.array(times)
            print(f"{qps:>8g} {k:>3} {pages:>9.2f} {np.median(t):>11.0f} {np.percentile(t, 90):>6.0f} "
                  f"{int((~np.isfinite(t)).sum()):>6}")


if __name__ == "__main__":
    print(f"numpy {np.__version__}, python {sys.version.split()[0]}")
    e1_false_pages(0.001)
    e1_false_pages(0.0005)
    e2_detection()
    e3_reset()
    e4_low_traffic_detection()
    e5_guard()
