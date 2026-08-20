"""Tests for Black-Scholes Greek P&L attribution."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from equity_options_research.pricing.black_scholes import price
from equity_options_research.pricing.greeks import all_greeks
from equity_options_research.research.greek_attribution import (
    DAYS_PER_YEAR,
    Leg,
    attribution_quality,
    leg_state,
    second_order_pnl,
    vanna,
    volga,
)

S, K, T, R, Q, SIGMA = 100.0, 100.0, 0.25, 0.03, 0.01, 0.20


# ------------------------------------------------ analytic vs finite difference
@pytest.mark.parametrize("right", ["call", "put"])
@pytest.mark.parametrize("strike", [85.0, 100.0, 115.0])
def test_delta_and_gamma_match_finite_differences(right: str, strike: float) -> None:
    h = 1e-4 * S
    g = all_greeks(right, S, strike, T, R, Q, SIGMA)
    up = price(right, S + h, strike, T, R, Q, SIGMA)
    down = price(right, S - h, strike, T, R, Q, SIGMA)
    mid = price(right, S, strike, T, R, Q, SIGMA)
    assert g["delta"] == pytest.approx((up - down) / (2 * h), rel=1e-5)
    assert g["gamma"] == pytest.approx((up - 2 * mid + down) / h**2, rel=1e-3)


@pytest.mark.parametrize("right", ["call", "put"])
def test_vega_and_theta_match_finite_differences(right: str) -> None:
    hv = 1e-5
    g = all_greeks(right, S, K, T, R, Q, SIGMA)
    fd_vega = (price(right, S, K, T, R, Q, SIGMA + hv) - price(right, S, K, T, R, Q, SIGMA - hv)) / (2 * hv)
    assert g["vega"] == pytest.approx(fd_vega, rel=1e-5)
    ht = 1e-6
    fd_theta = -(price(right, S, K, T + ht, R, Q, SIGMA) - price(right, S, K, T - ht, R, Q, SIGMA)) / (2 * ht)
    assert g["theta"] == pytest.approx(fd_theta, rel=1e-3)


@pytest.mark.parametrize("right", ["call", "put"])
@pytest.mark.parametrize("strike", [88.0, 112.0])
def test_vanna_and_volga_match_finite_differences(right: str, strike: float) -> None:
    """Away from the money: both vanish identically at d2 = 0, which these
    parameters hit exactly at the money, making a relative check meaningless."""
    hv = 1e-5
    fd_vanna = (all_greeks(right, S, strike, T, R, Q, SIGMA + hv)["delta"]
                - all_greeks(right, S, strike, T, R, Q, SIGMA - hv)["delta"]) / (2 * hv)
    assert vanna(S, strike, T, R, Q, SIGMA) == pytest.approx(fd_vanna, rel=1e-3)
    fd_volga = (all_greeks(right, S, strike, T, R, Q, SIGMA + hv)["vega"]
                - all_greeks(right, S, strike, T, R, Q, SIGMA - hv)["vega"]) / (2 * hv)
    assert volga(S, strike, T, R, Q, SIGMA) == pytest.approx(fd_volga, rel=1e-3)


def test_vanna_and_volga_vanish_where_d2_is_zero() -> None:
    assert vanna(S, K, T, R, Q, SIGMA) == pytest.approx(0.0, abs=1e-12)
    assert volga(S, K, T, R, Q, SIGMA) == pytest.approx(0.0, abs=1e-12)


def test_greeks_vanish_at_expiry() -> None:
    for right in ["call", "put"]:
        g = all_greeks(right, S, K, 0.0, R, Q, SIGMA)
        assert g["gamma"] == 0.0 and g["vega"] == 0.0 and g["theta"] == 0.0


# ------------------------------------------------------------ leg state
def test_leg_state_recovers_the_volatility_it_was_priced_with() -> None:
    market = price("put", S, 95.0, T, R, Q, 0.23)
    state = leg_state(Leg("put", 95.0, -1.0), S, T, R, Q, market)
    assert state["implied_vol"] == pytest.approx(0.23, rel=1e-6)
    assert state["model_price"] == pytest.approx(market, rel=1e-8)
    assert state["quantity"] == -1.0


def test_leg_state_degrades_gracefully_on_an_uninvertible_quote() -> None:
    """A root finder will return an arbitrary sigma for an economically zero
    price, because Black-Scholes is flat in sigma there. That must not become a
    Greek."""
    state = leg_state(Leg("call", 200.0, -1.0), S, T, R, Q, 1e-12)
    assert np.isnan(state["implied_vol"]) and np.isnan(state["delta"])
    assert np.isnan(leg_state(Leg("call", 200.0, -1.0), S, T, R, Q, 0.0)["implied_vol"])


def test_leg_state_uses_no_information_beyond_the_current_quote() -> None:
    """Same inputs must give the same state regardless of call order."""
    a = leg_state(Leg("call", 105.0, -3.0), S, T, R, Q, 2.5)
    leg_state(Leg("put", 90.0, -7.0), S * 1.5, T, R, Q, 9.0)
    b = leg_state(Leg("call", 105.0, -3.0), S, T, R, Q, 2.5)
    assert a == b


# --------------------------------------------------------- P&L signs
def _short_state(right: str, strike: float, quantity: float) -> pd.DataFrame:
    g = all_greeks(right, S, strike, T, R, Q, SIGMA)
    return pd.DataFrame([{**g, "quantity": quantity, "multiplier": 100,
                          "vanna": vanna(S, strike, T, R, Q, SIGMA),
                          "volga": volga(S, strike, T, R, Q, SIGMA)}])


def test_a_short_option_earns_theta_and_pays_gamma() -> None:
    state = _short_state("call", 100.0, -1.0)
    out = second_order_pnl(state, spot_change=0.0, vol_change=np.array([0.0]), time_change_days=1.0)
    assert out.theta_pnl.iloc[0] > 0          # time passing helps the seller
    out_move = second_order_pnl(state, spot_change=5.0, vol_change=np.array([0.0]), time_change_days=0.0)
    assert out_move.gamma_pnl.iloc[0] < 0     # any move hurts the seller
    down = second_order_pnl(state, spot_change=-5.0, vol_change=np.array([0.0]), time_change_days=0.0)
    assert down.gamma_pnl.iloc[0] == pytest.approx(out_move.gamma_pnl.iloc[0])


def test_a_short_option_loses_when_implied_volatility_rises() -> None:
    state = _short_state("put", 95.0, -1.0)
    out = second_order_pnl(state, spot_change=0.0, vol_change=np.array([0.02]), time_change_days=0.0)
    assert out.vega_pnl.iloc[0] < 0


def test_a_long_option_has_the_mirrored_signs() -> None:
    short = second_order_pnl(_short_state("call", 100.0, -1.0), 3.0, np.array([0.01]), 1.0)
    long = second_order_pnl(_short_state("call", 100.0, +1.0), 3.0, np.array([0.01]), 1.0)
    assert np.allclose(short[["delta_pnl", "gamma_pnl", "vega_pnl", "theta_pnl"]].to_numpy(),
                       -long[["delta_pnl", "gamma_pnl", "vega_pnl", "theta_pnl"]].to_numpy())


def test_attribution_components_sum_to_the_reported_approximation() -> None:
    out = second_order_pnl(_short_state("put", 95.0, -4.0), 2.0, np.array([0.01]), 1.0, include_cross_terms=True)
    parts = out[["delta_pnl", "gamma_pnl", "vega_pnl", "theta_pnl", "vanna_pnl", "volga_pnl"]].sum(axis=1)
    assert out.approx_pnl.iloc[0] == pytest.approx(parts.iloc[0])


def test_theta_scales_with_elapsed_time_and_uses_a_365_day_year() -> None:
    state = _short_state("call", 100.0, -1.0)
    one = second_order_pnl(state, 0.0, np.array([0.0]), 1.0).theta_pnl.iloc[0]
    three = second_order_pnl(state, 0.0, np.array([0.0]), 3.0).theta_pnl.iloc[0]
    assert three == pytest.approx(3.0 * one)
    expected = -1.0 * 100 * state.theta.iloc[0] * (1.0 / DAYS_PER_YEAR)
    assert one == pytest.approx(expected)


# ------------------------------------------------------- portfolio aggregation
def test_portfolio_attribution_is_the_sum_of_its_legs() -> None:
    legs = pd.concat([_short_state("put", 90.0, -5.0), _short_state("put", 95.0, -3.0),
                      _short_state("call", 105.0, -2.0)], ignore_index=True)
    combined = second_order_pnl(legs, 1.5, np.array([0.005, 0.004, 0.006]), 1.0)
    separate = sum(
        second_order_pnl(legs.iloc[[i]], 1.5, np.array([v]), 1.0).approx_pnl.iloc[0]
        for i, v in enumerate([0.005, 0.004, 0.006])
    )
    assert combined.approx_pnl.sum() == pytest.approx(separate)


def test_a_strip_of_shorts_has_negative_net_gamma_whatever_the_strikes() -> None:
    legs = pd.concat([_short_state("put", k, -1.0) for k in [85.0, 90.0, 95.0]]
                     + [_short_state("call", k, -1.0) for k in [105.0, 110.0]], ignore_index=True)
    out = second_order_pnl(legs, 4.0, np.zeros(5), 0.0)
    assert out.gamma_pnl.sum() < 0


# --------------------------------------------------- attribution reconciliation
def test_attribution_reconciles_for_a_pure_time_step() -> None:
    """With no spot or vol move, a one-day revaluation is theta to second order.
    The half-percent tolerance is the genuine truncation error of a linear time
    term over a whole day, not slack."""
    strike, sigma = 100.0, 0.20
    q, mult = -2.0, 100
    dt = 1.0 / DAYS_PER_YEAR
    before = price("call", S, strike, T, R, Q, sigma)
    after = price("call", S, strike, T - dt, R, Q, sigma)
    actual = q * mult * (after - before)
    approx = second_order_pnl(_short_state("call", strike, q), 0.0, np.array([0.0]), 1.0).approx_pnl.iloc[0]
    assert approx == pytest.approx(actual, rel=5e-3)


def test_attribution_quality_reports_a_perfect_fit_as_perfect() -> None:
    actual = pd.Series([100.0, -50.0, 25.0, 10.0, -5.0])
    q = attribution_quality(actual, actual)
    assert q["correlation"] == pytest.approx(1.0)
    assert q["rmse"] == pytest.approx(0.0)
    assert q["explained_variance"] == pytest.approx(1.0)


def test_attribution_quality_penalises_a_biased_approximation() -> None:
    actual = pd.Series([100.0, -50.0, 25.0, 10.0, -5.0])
    q = attribution_quality(actual, actual * 0.5)
    assert q["explained_variance"] < 1.0
    assert q["mean_residual"] == pytest.approx(actual.mean() * 0.5)


def test_attribution_quality_ignores_unusable_rows() -> None:
    actual = pd.Series([1.0, np.nan, 3.0, 4.0, 5.0])
    approx = pd.Series([1.0, 2.0, np.nan, 4.0, 5.0])
    assert attribution_quality(actual, approx)["n"] == 3.0
