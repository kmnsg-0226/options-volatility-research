import numpy as np
import pytest

from equity_options_research.pricing.black_scholes import bsm_call_price, bsm_put_price
from equity_options_research.research.model_free_variance import (
    interpolate_total_variance,
    model_free_variance,
    strike_intervals,
)


def bs_chain(spot=100.0, sigma=0.20, r=0.02, q=0.0, T=30 / 365, lo=40.0, hi=200.0, step=1.0):
    """A dense, arbitrage-free chain generated from Black-Scholes."""
    strikes = np.arange(lo, hi + step, step)
    calls = np.array([bsm_call_price(spot, k, T, r, q, sigma) for k in strikes])
    puts = np.array([bsm_put_price(spot, k, T, r, q, sigma) for k in strikes])
    tick = 1e-4
    return strikes, calls - tick, calls + tick, puts - tick, puts + tick


# ---------------- building blocks ----------------

def test_strike_intervals_are_central_with_one_sided_ends() -> None:
    out = strike_intervals(np.array([90.0, 95.0, 100.0, 110.0]))
    assert out[0] == pytest.approx(5.0)
    assert out[1] == pytest.approx((100 - 90) / 2)
    assert out[2] == pytest.approx((110 - 95) / 2)
    assert out[-1] == pytest.approx(10.0)


def test_uniform_grid_gives_uniform_intervals() -> None:
    out = strike_intervals(np.arange(90.0, 111.0, 5.0))
    assert np.allclose(out, 5.0)


# ---------------- the CBOE identity ----------------

def test_recovers_black_scholes_variance_from_a_dense_chain() -> None:
    sigma, T = 0.20, 30 / 365
    strikes, cb, ca, pb, pa = bs_chain(sigma=sigma, T=T)
    result = model_free_variance(strikes, cb, ca, pb, pa, rate=0.02, year_fraction=T)
    assert result.success
    # discretisation and truncation leave a small negative bias; 5% is ample
    assert result.variance == pytest.approx(sigma**2, rel=0.05)


def test_recovers_a_different_volatility_level() -> None:
    sigma, T = 0.35, 45 / 365
    strikes, cb, ca, pb, pa = bs_chain(sigma=sigma, T=T, lo=20.0, hi=300.0)
    result = model_free_variance(strikes, cb, ca, pb, pa, rate=0.03, year_fraction=T)
    assert result.success
    assert result.variance == pytest.approx(sigma**2, rel=0.05)


def test_forward_is_recovered_by_put_call_parity() -> None:
    spot, r, q, T = 100.0, 0.02, 0.0, 30 / 365
    strikes, cb, ca, pb, pa = bs_chain(spot=spot, r=r, q=q, T=T)
    result = model_free_variance(strikes, cb, ca, pb, pa, rate=r, year_fraction=T)
    assert result.forward == pytest.approx(spot * np.exp((r - q) * T), rel=1e-3)


def test_k0_is_the_first_strike_at_or_below_the_forward() -> None:
    strikes, cb, ca, pb, pa = bs_chain(step=5.0)
    result = model_free_variance(strikes, cb, ca, pb, pa, rate=0.02, year_fraction=30 / 365)
    assert result.k0 <= result.forward
    assert result.k0 + 5.0 > result.forward


def test_manual_summation_reconstructs_the_reported_variance() -> None:
    """Recompute the CBOE sum by hand and compare with the module."""
    T, r = 30 / 365, 0.02
    strikes, cb, ca, pb, pa = bs_chain(T=T, r=r, step=5.0)
    result = model_free_variance(strikes, cb, ca, pb, pa, rate=r, year_fraction=T)
    assert result.success

    call_mid, put_mid = (cb + ca) / 2, (pb + pa) / 2
    k0 = result.k0
    used = strikes[(strikes >= result.lowest_strike) & (strikes <= result.highest_strike)]
    q = np.where(used < k0, put_mid[np.isin(strikes, used)],
                 np.where(used > k0, call_mid[np.isin(strikes, used)],
                          (call_mid[np.isin(strikes, used)] + put_mid[np.isin(strikes, used)]) / 2))
    dk = strike_intervals(used)
    manual = 2 / T * np.sum(dk / used**2 * np.exp(r * T) * q) - (result.forward / k0 - 1) ** 2 / T
    assert manual == pytest.approx(result.variance, rel=1e-9)


# ---------------- data-quality rules ----------------

def test_zero_bid_wing_truncation_stops_at_two_consecutive_zeros() -> None:
    strikes, cb, ca, pb, pa = bs_chain(step=5.0)
    pb = pb.copy()
    low = strikes < 70
    pb[low] = 0.0                     # deep put wing quotes a zero bid
    result = model_free_variance(strikes, cb, ca, pb, pa, rate=0.02, year_fraction=30 / 365)
    assert result.success
    assert result.lowest_strike >= 65.0


def test_duplicate_strikes_are_rejected() -> None:
    strikes = np.array([95.0, 100.0, 100.0, 105.0])
    ones = np.ones(4)
    out = model_free_variance(strikes, ones, ones * 1.1, ones, ones * 1.1, 0.02, 30 / 365)
    assert not out.success and out.reason == "duplicate_strikes"


def test_insufficient_strike_coverage_is_reported_not_silently_dropped() -> None:
    strikes = np.array([95.0, 100.0, 105.0])
    out = model_free_variance(
        strikes, np.array([6.0, 2.0, 0.5]), np.array([6.2, 2.2, 0.6]),
        np.array([0.5, 2.0, 6.0]), np.array([0.6, 2.2, 6.2]), 0.02, 30 / 365,
    )
    assert not out.success and out.reason == "insufficient_strike_coverage"
    assert out.strikes_used == 3


def test_crossed_quotes_are_excluded() -> None:
    strikes, cb, ca, pb, pa = bs_chain(step=5.0)
    ca = ca.copy()
    ca[:5] = cb[:5] - 0.5      # crossed on the low wing
    result = model_free_variance(strikes, cb, ca, pb, pa, rate=0.02, year_fraction=30 / 365)
    assert result.success


def test_nonpositive_maturity_is_rejected() -> None:
    strikes, cb, ca, pb, pa = bs_chain()
    out = model_free_variance(strikes, cb, ca, pb, pa, rate=0.02, year_fraction=0.0)
    assert not out.success and out.reason == "nonpositive_maturity"


def test_variance_is_positive_and_finite_on_a_valid_chain() -> None:
    strikes, cb, ca, pb, pa = bs_chain()
    out = model_free_variance(strikes, cb, ca, pb, pa, 0.02, 30 / 365)
    assert out.success and out.variance > 0 and np.isfinite(out.variance)


# ---------------- total-variance interpolation ----------------

def test_interpolation_is_linear_in_total_variance_not_in_rate() -> None:
    near_v, near_T = 0.04, 20 / 365
    next_v, next_T = 0.09, 50 / 365
    target_T = 35 / 365
    out = interpolate_total_variance(near_v, near_T, next_v, next_T, target_T)
    expected_total = 0.5 * (near_v * near_T) + 0.5 * (next_v * next_T)
    assert out == pytest.approx(expected_total / target_T)
    # a naive average of the rates would give 0.065; total-variance weighting does not
    assert out != pytest.approx(0.065)


def test_interpolation_at_an_endpoint_returns_that_endpoint_rate() -> None:
    assert interpolate_total_variance(0.04, 20 / 365, 0.09, 50 / 365, 20 / 365) == pytest.approx(0.04)
    assert interpolate_total_variance(0.04, 20 / 365, 0.09, 50 / 365, 50 / 365) == pytest.approx(0.09)


def test_interpolation_rejects_inverted_maturities() -> None:
    with pytest.raises(ValueError, match="near maturity"):
        interpolate_total_variance(0.04, 50 / 365, 0.09, 20 / 365, 30 / 365)


def test_expiration_day_chains_are_excluded_not_integrated() -> None:
    """At T -> 0 the 2/T factor diverges, so expiry-day chains must be rejected."""
    import pandas as pd

    from equity_options_research.research.model_free_variance import chain_variance_frame

    strikes, cb, ca, pb, pa = bs_chain(step=5.0)
    rows = []
    for dte in (0, 30):
        for k, c_b, c_a, p_b, p_a in zip(strikes, cb, ca, pb, pa, strict=True):
            rows.append({
                "quote_date": pd.Timestamp("2020-01-02"),
                "expiration": pd.Timestamp("2020-01-02") + pd.Timedelta(days=int(dte)),
                "dte": float(dte), "strike": float(k),
                "call_bid": c_b, "call_ask": c_a, "put_bid": p_b, "put_ask": p_a,
                "risk_free_rate": 0.02,
            })
    out = chain_variance_frame(pd.DataFrame(rows))
    expiry_day = out[out["dte"] == 0].iloc[0]
    assert not expiry_day["success"] and expiry_day["reason"] == "expiration_day"
    assert out[out["dte"] == 30].iloc[0]["success"]
