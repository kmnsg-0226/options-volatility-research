from math import exp

import pytest

from equity_options_research.pricing.black_scholes import bsm_call_price, bsm_put_price
from equity_options_research.pricing.bounds import european_bounds, put_call_parity
from equity_options_research.pricing.greeks import call_delta, call_theta, gamma, vega
from equity_options_research.pricing.implied_vol import (
    implied_volatility,
    implied_volatility_newton,
)


def test_known_prices_and_parity() -> None:
    call = bsm_call_price(100, 100, 1, 0.05, 0, 0.2)
    put = bsm_put_price(100, 100, 1, 0.05, 0, 0.2)
    assert call == pytest.approx(10.4506, abs=1e-4)
    assert put == pytest.approx(5.5735, abs=1e-4)
    assert call - put == pytest.approx(100 - 100 * exp(-0.05), abs=1e-9)
    assert put_call_parity(call, put, 100, 100, 1, 0.05, 0).within_tolerance


def test_bounds_monotonicity_and_limits() -> None:
    lo, hi = european_bounds("call", 100, 100, 1, 0.05, 0.01)
    assert lo <= bsm_call_price(100, 100, 1, 0.05, 0.01, 0.2) <= hi
    assert bsm_call_price(100, 100, 1, 0.05, 0.01, 0.4) > bsm_call_price(100, 100, 1, 0.05, 0.01, 0.2)
    assert bsm_call_price(101, 100, 0, 0.05, 0, 0.2) == 1
    assert bsm_call_price(100, 100, 1, 0, 0, 0) == 0


def test_greeks_against_finite_difference() -> None:
    args = (102.0, 100.0, 0.7, 0.03, 0.01, 0.25)
    S, K, T, r, q, sigma = args
    eps, vol_eps, time_eps = 1e-3, 1e-5, 1e-6
    fd_delta = (bsm_call_price(S + eps, K, T, r, q, sigma) - bsm_call_price(S - eps, K, T, r, q, sigma)) / (2 * eps)
    fd_gamma = (bsm_call_price(S + eps, K, T, r, q, sigma) - 2 * bsm_call_price(S, K, T, r, q, sigma) + bsm_call_price(S - eps, K, T, r, q, sigma)) / eps**2
    fd_vega = (bsm_call_price(S, K, T, r, q, sigma + vol_eps) - bsm_call_price(S, K, T, r, q, sigma - vol_eps)) / (2 * vol_eps)
    # Calendar theta is -dV/dT.
    fd_theta = -(bsm_call_price(S, K, T + time_eps, r, q, sigma) - bsm_call_price(S, K, T - time_eps, r, q, sigma)) / (2 * time_eps)
    assert call_delta(*args) == pytest.approx(fd_delta, rel=1e-5)
    assert gamma(*args) == pytest.approx(fd_gamma, rel=2e-4)
    assert vega(*args) == pytest.approx(fd_vega, rel=1e-5)
    assert call_theta(*args) == pytest.approx(fd_theta, rel=1e-5)


def test_iv_recovery_and_failures() -> None:
    market = bsm_call_price(100, 105, 0.5, 0.03, 0.01, 0.37)
    result = implied_volatility("call", market, 100, 105, 0.5, 0.03, 0.01)
    assert result.success and result.volatility == pytest.approx(0.37, abs=1e-8)
    assert result.absolute_error is not None and result.absolute_error < 1e-8
    assert implied_volatility("call", 200, 100, 100, 1, 0, 0).reason == "above_no_arbitrage_upper_bound"
    assert implied_volatility("call", market, 100, 105, 0.5, 0.03, 0.01, 0.01, 0.02).reason == "root_not_bracketed"
    assert implied_volatility_newton("call", 0, 1, 1000, 0.01, 0, 0, initial=1e-9).reason == "zero_vega"
