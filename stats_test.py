"""Statistical tests on the first_orders table in olist.db.

Question: do customers whose first order arrived late come back to buy less?

  1. Two-proportion z-test: repeat rate, late vs on-time first orders
     (p-value, difference, 95% confidence interval).
  2. Significance at alpha = 0.05.
  3. Power analysis: how many late-order customers we would need to detect
     a difference of the observed size.
  4. Second check: average review score of the first order, late vs on-time
     (Welch t-test, plus a Mann-Whitney test because scores are 1-5 ratings).
  5. Sensitivity check: test 1 again, counting only non-canceled orders as
     repeats.

Uses only the Python standard library (no scipy needed).
Build first_orders first with analysis.sql, then run:  python stats_test.py
"""
import math
import sqlite3
from pathlib import Path
from statistics import NormalDist

DB_PATH = Path(__file__).resolve().parent / "olist.db"
ALPHA = 0.05
POWER_TARGETS = (0.80, 0.90)
Z = NormalDist()  # standard normal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def two_sided_p_from_z(z):
    return 2 * (1 - Z.cdf(abs(z)))


def _betacf(a, b, x, max_iter=300, eps=3e-14):
    """Continued fraction for the regularized incomplete beta function."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1, a - 1
    c, d = 1.0, 1 - qab * x / qap
    d = 1 / (d if abs(d) > tiny else tiny)
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + aa / c
        c = c if abs(c) > tiny else tiny
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1 + aa * d
        d = 1 / (d if abs(d) > tiny else tiny)
        c = 1 + aa / c
        c = c if abs(c) > tiny else tiny
        delta = d * c
        h *= delta
        if abs(delta - 1) < eps:
            break
    return h


def betainc(a, b, x):
    """Regularized incomplete beta I_x(a, b)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    ln_front = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
                + a * math.log(x) + b * math.log(1 - x))
    front = math.exp(ln_front)
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    return 1 - front * _betacf(b, a, 1 - x) / b


def t_two_sided_p(t, df):
    """Two-sided p-value of Student's t distribution."""
    return betainc(df / 2, 0.5, df / (df + t * t))


def t_critical(df, conf=0.95):
    """Two-sided critical value of the t distribution, by bisection."""
    target = 1 - conf
    lo, hi = 0.0, 50.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if t_two_sided_p(mid, df) > target:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def fmt_p(p):
    if p == 0:
        return "< 1e-300 (too small to represent)"
    return f"{p:.4f}" if p >= 0.0001 else f"{p:.2e}"


def pct(x):
    return f"{100 * x:.2f}%"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def two_proportion_test(x1, n1, x2, n2, conf=0.95):
    """Group 1 = late, group 2 = on time. Difference = p1 - p2."""
    p1, p2 = x1 / n1, x2 / n2
    diff = p1 - p2
    p_pool = (x1 + x2) / (n1 + n2)
    se_pool = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))  # for the test
    z = diff / se_pool
    p_value = two_sided_p_from_z(z)
    se_unpooled = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)  # for the CI
    zc = Z.inv_cdf(1 - (1 - conf) / 2)
    ci = (diff - zc * se_unpooled, diff + zc * se_unpooled)
    return dict(p1=p1, p2=p2, diff=diff, z=z, p_value=p_value, ci=ci,
                rel=p1 / p2 if p2 else float("nan"))


def achieved_power(p1, p2, n1, n2, alpha=ALPHA):
    """Power of the two-sided two-proportion z-test for the given sizes."""
    d = abs(p1 - p2)
    p_bar = (n1 * p1 + n2 * p2) / (n1 + n2)
    se0 = math.sqrt(p_bar * (1 - p_bar) * (1 / n1 + 1 / n2))
    se1 = math.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    za = Z.inv_cdf(1 - alpha / 2)
    return Z.cdf((d - za * se0) / se1) + Z.cdf((-d - za * se0) / se1)


def required_n_late(p1, p2, ratio, power, alpha=ALPHA):
    """Late-group size n1 needed, with n_on_time = ratio * n1."""
    d = abs(p1 - p2)
    k = ratio
    p_bar = (p1 + k * p2) / (1 + k)
    za = Z.inv_cdf(1 - alpha / 2)
    zb = Z.inv_cdf(power)
    num = (za * math.sqrt(p_bar * (1 - p_bar) * (1 + 1 / k))
           + zb * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2) / k)) ** 2
    return math.ceil(num / d ** 2)


def welch_t_test(a, b, conf=0.95):
    n1, n2 = len(a), len(b)
    m1, m2 = sum(a) / n1, sum(b) / n2
    v1 = sum((x - m1) ** 2 for x in a) / (n1 - 1)
    v2 = sum((x - m2) ** 2 for x in b) / (n2 - 1)
    se = math.sqrt(v1 / n1 + v2 / n2)
    t = (m1 - m2) / se
    df = (v1 / n1 + v2 / n2) ** 2 / ((v1 / n1) ** 2 / (n1 - 1) + (v2 / n2) ** 2 / (n2 - 1))
    tc = t_critical(df, conf)
    diff = m1 - m2
    pooled_sd = math.sqrt(((n1 - 1) * v1 + (n2 - 1) * v2) / (n1 + n2 - 2))
    return dict(n1=n1, n2=n2, m1=m1, m2=m2, sd1=math.sqrt(v1), sd2=math.sqrt(v2),
                diff=diff, t=t, df=df, p_value=t_two_sided_p(t, df),
                ci=(diff - tc * se, diff + tc * se), cohens_d=diff / pooled_sd)


def mann_whitney(a, b):
    """Mann-Whitney U with tie correction, normal approximation."""
    n1, n2 = len(a), len(b)
    combined = sorted([(x, 0) for x in a] + [(x, 1) for x in b])
    ranks, tie_term, i = [0.0] * len(combined), 0.0, 0
    while i < len(combined):
        j = i
        while j + 1 < len(combined) and combined[j + 1][0] == combined[i][0]:
            j += 1
        avg_rank = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[k] = avg_rank
        t = j - i + 1
        tie_term += t ** 3 - t
        i = j + 1
    r1 = sum(r for r, (_, g) in zip(ranks, combined) if g == 0)
    u1 = r1 - n1 * (n1 + 1) / 2
    n = n1 + n2
    mu = n1 * n2 / 2
    sigma = math.sqrt(n1 * n2 / 12 * ((n + 1) - tie_term / (n * (n - 1))))
    z = (u1 - mu) / sigma
    return dict(u=u1, z=z, p_value=two_sided_p_from_z(z),
                prob_superiority=u1 / (n1 * n2))  # P(late score > on-time score)


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def repeat_counts(conn, column):
    rows = conn.execute(f"""
        SELECT is_late, COUNT(*), SUM({column}) FROM first_orders GROUP BY is_late
    """).fetchall()
    d = {late: (n, x) for late, n, x in rows}
    return d[1], d[0]  # (n_late, x_late), (n_on, x_on)


def report_proportions(title, late, on):
    (n1, x1), (n2, x2) = late, on
    r = two_proportion_test(x1, n1, x2, n2)
    print(f"\n{title}")
    print(f"  Late:    {x1:>5,} / {n1:>6,} came back  = {pct(r['p1'])}")
    print(f"  On time: {x2:>5,} / {n2:>6,} came back  = {pct(r['p2'])}")
    print(f"  Difference (late - on time): {100 * r['diff']:+.2f} percentage points")
    print(f"  95% CI: [{100 * r['ci'][0]:+.2f}, {100 * r['ci'][1]:+.2f}] percentage points")
    print(f"  Relative: late customers repeat at {r['rel']:.2f}x the on-time rate")
    print(f"  z = {r['z']:.3f},  p-value = {fmt_p(r['p_value'])}")
    verdict = "SIGNIFICANT" if r["p_value"] < ALPHA else "NOT significant"
    print(f"  -> {verdict} at alpha = {ALPHA}")
    return r


def main():
    conn = sqlite3.connect(DB_PATH)

    print("=" * 72)
    print("1-2. Repeat rate within 180 days: late vs on-time first order")
    print("     Two-proportion z-test (pooled SE for the test, unpooled SE for the CI)")
    print("=" * 72)
    late, on = repeat_counts(conn, "is_repeat")
    r = report_proportions("Repeat = any later order (any status)", late, on)

    print("\n" + "=" * 72)
    print("3. Power analysis (two-sided, alpha = 0.05)")
    print("=" * 72)
    (n1, _), (n2, _) = late, on
    p1, p2 = r["p1"], r["p2"]
    ratio = n2 / n1
    print(f"  Effect size assumed: {pct(p1)} vs {pct(p2)} "
          f"(difference {100 * (p1 - p2):+.2f} points)")
    print(f"  Power we actually had with {n1:,} late / {n2:,} on-time: "
          f"{pct(achieved_power(p1, p2, n1, n2))}")
    for target in POWER_TARGETS:
        need_cur = required_n_late(p1, p2, ratio, target)
        need_eq = required_n_late(p1, p2, 1.0, target)
        print(f"\n  For {target:.0%} power:")
        print(f"    Keeping today's mix ({ratio:.1f} on-time per late customer): "
              f"{need_cur:,} late customers "
              f"(~{need_cur * (1 + ratio):,.0f} customers in total, "
              f"{need_cur / n1:.1f}x the late customers we have)")
        print(f"    With equal groups: {need_eq:,} late + {need_eq:,} on-time customers")

    print("\n" + "=" * 72)
    print("4. Review score of the first order: late vs on-time")
    print("   (customers whose first order has no review are excluded)")
    print("=" * 72)
    late_s = [s for (s,) in conn.execute(
        "SELECT review_score FROM first_orders WHERE is_late = 1 AND review_score IS NOT NULL")]
    on_s = [s for (s,) in conn.execute(
        "SELECT review_score FROM first_orders WHERE is_late = 0 AND review_score IS NOT NULL")]
    w = welch_t_test(late_s, on_s)
    print(f"  Late:    n = {w['n1']:>6,}  mean = {w['m1']:.3f}  (sd {w['sd1']:.2f})")
    print(f"  On time: n = {w['n2']:>6,}  mean = {w['m2']:.3f}  (sd {w['sd2']:.2f})")
    print(f"  Difference (late - on time): {w['diff']:+.3f} stars")
    print(f"  95% CI: [{w['ci'][0]:+.3f}, {w['ci'][1]:+.3f}] stars")
    print(f"  Welch t = {w['t']:.2f}, df = {w['df']:.0f}, p-value = {fmt_p(w['p_value'])}")
    print(f"  Cohen's d = {w['cohens_d']:.2f}")
    mw = mann_whitney(late_s, on_s)
    print(f"  Mann-Whitney: z = {mw['z']:.2f}, p-value = {fmt_p(mw['p_value'])}, "
          f"P(late score > on-time score) = {mw['prob_superiority']:.2f}")
    print("\n  Score distribution (rounded down for averaged scores):")
    print("    stars   late    on time")
    for star in range(1, 6):
        fl = sum(1 for s in late_s if int(s) == star) / len(late_s)
        fo = sum(1 for s in on_s if int(s) == star) / len(on_s)
        print(f"      {star}   {pct(fl):>7}   {pct(fo):>7}")

    print("\n" + "=" * 72)
    print("5. Sensitivity: repeat = later order that was NOT canceled")
    print("=" * 72)
    late_nc, on_nc = repeat_counts(conn, "is_repeat_noncanceled")
    r_nc = report_proportions("Repeat = any later non-canceled order", late_nc, on_nc)
    same = (r["p_value"] < ALPHA) == (r_nc["p_value"] < ALPHA)
    print(f"\n  Conclusion {'UNCHANGED' if same else 'CHANGES'} versus test 1.")

    conn.close()


if __name__ == "__main__":
    main()
