"""Tests for the Heston pricer, the QE simulator and capped-variance valuation."""

from __future__ import annotations

import numpy as np
import pytest

from equity_options_research.pricing.black_scholes import bsm_call_price
from equity_options_research.pricing.capped_variance import (
    capped_payoff,
    hypothetical_capped_payoff,
    price_capped_variance,
    simulate_realised_variance,
    uncapped_payoff,
)
from equity_options_research.pricing.heston import (
    HestonParams,
    call_prices,
    characteristic_function,
    expected_integrated_variance,
    put_prices,
    realised_variance_from_paths,
    simulate_paths,
)

BASE = HestonParams(v0=0.04, kappa=1.5, theta=0.05, xi=0.6, rho=-0.7)
F, R, T = 100.0, 0.03, 0.25
STRIKES = np.array([80.0, 90.0, 95.0, 100.0, 105.0, 110.0, 120.0])


# ------------------------------------------------------------ parameters
def test_parameters_reject_economically_invalid_values() -> None:
    for bad in [
        {"v0": -0.01}, {"v0": 0.0}, {"kappa": 0.0}, {"kappa": -1.0},
        {"theta": 0.0}, {"xi": 0.0}, {"rho": 1.0}, {"rho": -1.0}, {"rho": 1.5},
    ]:
        with pytest.raises(ValueError):
            HestonParams(**{**{"v0": 0.04, "kappa": 1.5, "theta": 0.05, "xi": 0.6, "rho": -0.7}, **bad})


def test_feller_condition_is_reported_not_enforced() -> None:
    satisfied = HestonParams(v0=0.04, kappa=3.0, theta=0.05, xi=0.3, rho=-0.5)
    violated = HestonParams(v0=0.04, kappa=1.0, theta=0.02, xi=1.5, rho=-0.5)
    assert satisfied.feller and satisfied.feller_ratio >= 1.0
    assert not violated.feller and violated.feller_ratio < 1.0


def test_parameter_array_round_trip() -> None:
    assert HestonParams.from_array(BASE.as_array()) == BASE


# --------------------------------------------------- characteristic function
def test_characteristic_function_is_a_martingale_at_u_equals_minus_i() -> None:
    """psi(-i) = E[S_T/F] must be exactly one, at every maturity."""
    for maturity in [0.02, 0.25, 1.0, 5.0, 10.0]:
        value = characteristic_function(np.array([-1j]), maturity, BASE)[0]
        assert value.real == pytest.approx(1.0, abs=1e-10)
        assert value.imag == pytest.approx(0.0, abs=1e-10)


def test_characteristic_function_at_zero_is_one() -> None:
    assert characteristic_function(np.array([0.0]), T, BASE)[0] == pytest.approx(1.0)


def test_characteristic_function_has_conjugate_symmetry() -> None:
    u = np.array([0.5, 1.0, 3.0])
    assert np.allclose(characteristic_function(-u, T, BASE), np.conj(characteristic_function(u, T, BASE)))


def test_characteristic_function_stays_finite_at_long_maturity() -> None:
    """The trap-free branch must not wind the complex logarithm."""
    values = characteristic_function(np.linspace(0.01, 100.0, 500), 10.0, BASE)
    assert np.all(np.isfinite(values)) and np.all(np.abs(values) <= 1.0 + 1e-9)


# ------------------------------------------------------------ vanilla prices
@pytest.mark.parametrize("sigma", [0.15, 0.25, 0.40])
def test_vanilla_prices_collapse_to_black_scholes_as_vol_of_vol_vanishes(sigma: float) -> None:
    flat = HestonParams(v0=sigma**2, kappa=2.0, theta=sigma**2, xi=1e-6, rho=0.0)
    spot = F * np.exp(-R * T)
    heston = call_prices(F, STRIKES, T, R, flat, nodes=384, upper=300.0)
    black = np.array([bsm_call_price(spot, k, T, R, 0.0, sigma) for k in STRIKES])
    assert np.max(np.abs(heston - black)) < 5e-3


def test_put_call_parity_holds_exactly() -> None:
    calls = call_prices(F, STRIKES, T, R, BASE)
    puts = put_prices(F, STRIKES, T, R, BASE)
    assert np.allclose(calls - puts, np.exp(-R * T) * (F - STRIKES), atol=1e-10)


def test_vanilla_prices_respect_arbitrage_bounds() -> None:
    calls = call_prices(F, STRIKES, T, R, BASE)
    puts = put_prices(F, STRIKES, T, R, BASE)
    assert np.all(calls >= np.maximum(np.exp(-R * T) * (F - STRIKES), 0.0) - 1e-10)
    assert np.all(calls <= np.exp(-R * T) * F + 1e-10)
    assert np.all(puts >= np.maximum(np.exp(-R * T) * (STRIKES - F), 0.0) - 1e-10)


def test_call_prices_decrease_and_are_convex_in_strike() -> None:
    calls = call_prices(F, STRIKES, T, R, BASE)
    assert np.all(np.diff(calls) < 0)
    assert np.all(np.diff(calls, 2) > -1e-8)


def test_call_prices_increase_with_maturity() -> None:
    atm = np.array([100.0])
    values = [call_prices(F, atm, t, 0.0, BASE)[0] for t in [0.05, 0.25, 1.0, 2.0]]
    assert all(b > a for a, b in zip(values[:-1], values[1:], strict=True))


def test_zero_maturity_returns_intrinsic() -> None:
    assert np.allclose(call_prices(F, STRIKES, 0.0, R, BASE), np.maximum(F - STRIKES, 0.0))


def test_integration_has_converged_at_the_default_node_count() -> None:
    reference = call_prices(F, STRIKES, T, R, BASE, nodes=768, upper=500.0)
    assert np.max(np.abs(call_prices(F, STRIKES, T, R, BASE) - reference)) < 1e-6


# ------------------------------------------------------- Monte Carlo engine
def test_simulation_is_reproducible_from_its_seed() -> None:
    a = simulate_paths(BASE, T, 21, 500, seed=7)
    b = simulate_paths(BASE, T, 21, 500, seed=7)
    c = simulate_paths(BASE, T, 21, 500, seed=8)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_variance_process_never_goes_negative() -> None:
    """QE is unconditionally positive; a Feller-violating fit is the hard case."""
    rough = HestonParams(v0=0.01, kappa=1.0, theta=0.02, xi=2.0, rho=-0.8)
    _, variance = simulate_paths(rough, 0.25, 63, 4000, seed=3, return_variance=True)
    assert np.all(variance >= 0.0)
    assert np.all(np.isfinite(variance))


def test_monte_carlo_reprices_vanillas_within_its_standard_error() -> None:
    paths = 200_000
    returns = simulate_paths(BASE, T, 126, paths, seed=11)
    terminal = F * np.exp(np.sum(returns, axis=1))
    for strike in [90.0, 100.0, 110.0]:
        payoff = np.exp(-R * T) * np.maximum(terminal - strike, 0.0)
        stderr = payoff.std(ddof=1) / np.sqrt(paths)
        analytic = call_prices(F, np.array([strike]), T, R, BASE)[0]
        assert abs(payoff.mean() - analytic) < 4.0 * stderr


def test_monte_carlo_preserves_the_forward() -> None:
    returns = simulate_paths(BASE, T, 63, 200_000, seed=5)
    terminal = np.exp(np.sum(returns, axis=1))
    stderr = terminal.std(ddof=1) / np.sqrt(len(terminal))
    assert abs(terminal.mean() - 1.0) < 4.0 * stderr


def test_monte_carlo_recovers_expected_integrated_variance() -> None:
    returns = simulate_paths(BASE, T, 252, 200_000, seed=13)
    realised = realised_variance_from_paths(returns, T)
    stderr = realised.std(ddof=1) / np.sqrt(len(realised))
    analytic = expected_integrated_variance(T, BASE)
    assert abs(realised.mean() - analytic) < 5.0 * stderr


def test_expected_integrated_variance_matches_its_limits() -> None:
    flat = HestonParams(v0=0.04, kappa=1.0, theta=0.04, xi=0.3, rho=0.0)
    assert expected_integrated_variance(1.0, flat) == pytest.approx(0.04)
    rising = HestonParams(v0=0.01, kappa=2.0, theta=0.09, xi=0.3, rho=0.0)
    assert 0.01 < expected_integrated_variance(1.0, rising) < 0.09
    assert expected_integrated_variance(1e-8, rising) == pytest.approx(0.01, abs=1e-6)


# --------------------------------------------------- realised variance convention
def test_realised_variance_matches_the_canonical_engine_definition() -> None:
    from equity_options_research.research.canonical_variance_engine import realised_variance

    path = np.array([100.0, 101.0, 99.5, 102.0, 101.5])
    year_fraction = 30.0 / 365.0
    log_returns = np.log(path[1:] / path[:-1])[None, :]
    assert realised_variance_from_paths(log_returns, year_fraction)[0] == pytest.approx(
        realised_variance(path, year_fraction)
    )


def test_realised_variance_sampling_uses_the_contract_observation_count() -> None:
    coarse = simulate_realised_variance(BASE, 0.0833, steps=21, paths=20_000, seed=2)
    fine = simulate_realised_variance(BASE, 0.0833, steps=210, paths=20_000, seed=2)
    # both estimate the same integrated variance, so their means agree closely
    assert coarse.mean() == pytest.approx(fine.mean(), rel=0.05)
    # but coarse daily monitoring is a noisier estimator of the same quantity
    assert coarse.std() > fine.std()


# ------------------------------------------------------------- capped payoff
def test_capped_payoff_truncates_only_the_loss_side() -> None:
    assert capped_payoff(0.50, 0.03, 0.10, 1e6) == pytest.approx(1e6 * (0.03 - 0.10))
    assert capped_payoff(0.02, 0.03, 0.10, 1e6) == pytest.approx(1e6 * (0.03 - 0.02))


def test_capped_payoff_never_loses_more_than_the_cap_allows() -> None:
    worst = capped_payoff(1e9, 0.03, 0.10, 1e6)
    assert worst == pytest.approx(1e6 * (0.03 - 0.10))
    assert capped_payoff(0.5, 0.03, 0.10, 1e6) == worst


def test_hypothetical_payoff_is_strictly_more_generous_than_the_fair_contract() -> None:
    """The naive arithmetic keeps the uncapped strike and pays nothing for it."""
    fair = capped_payoff(0.50, 0.028, 0.10, 1e6)
    naive = hypothetical_capped_payoff(0.50, 0.03, 0.10, 1e6)
    assert naive > fair
    assert naive - fair == pytest.approx(1e6 * (0.03 - 0.028))


def test_uncapped_payoff_is_linear_in_realised_variance() -> None:
    a = uncapped_payoff(0.02, 0.03, 1e6)
    b = uncapped_payoff(0.04, 0.03, 1e6)
    assert a == pytest.approx(10_000.0)
    assert b == pytest.approx(-10_000.0)


# ------------------------------------------------------- fair capped strike
def _quote(multiplier: float, seed: int = 21, paths: int = 60_000):
    realised = simulate_realised_variance(BASE, 0.0833, 21, paths, seed)
    return price_capped_variance(realised, 0.045, multiplier, BASE, 0.0833, paths, 21, seed)


def test_fair_capped_strike_sits_below_the_uncapped_strike() -> None:
    q = _quote(2.5)
    assert q.fair_strike_capped < q.fair_strike_uncapped_market
    assert q.concession > 0.0


def test_cap_decomposition_identity_holds_exactly() -> None:
    """min(x, C) + (x - C)+ = x pathwise, so the strike decomposition is exact."""
    realised = simulate_realised_variance(BASE, 0.0833, 21, 40_000, seed=31)
    for multiplier in [2.0, 2.5, 3.0]:
        cap = multiplier * 0.045
        assert np.allclose(np.minimum(realised, cap) + np.maximum(realised - cap, 0.0), realised)
    q = _quote(2.5)
    assert q.fair_strike_capped + q.tail_value == pytest.approx(q.fair_strike_uncapped_market)


def test_a_higher_cap_concedes_less_strike_and_binds_less_often() -> None:
    low, mid, high = _quote(2.0), _quote(2.5), _quote(3.0)
    assert low.concession > mid.concession > high.concession
    assert low.probability_cap_binds > mid.probability_cap_binds > high.probability_cap_binds


def test_an_unreachable_cap_costs_nothing() -> None:
    q = _quote(500.0)
    assert q.tail_value == pytest.approx(0.0, abs=1e-9)
    assert q.fair_strike_capped == pytest.approx(q.fair_strike_uncapped_market)
    assert q.probability_cap_binds == 0.0


def test_monte_carlo_standard_error_is_reported_and_shrinks_with_paths() -> None:
    small, large = _quote(2.5, paths=10_000), _quote(2.5, paths=160_000)
    assert small.tail_value_stderr > large.tail_value_stderr
    lo, hi = large.confidence_interval
    assert lo < large.fair_strike_capped < hi


def test_quote_row_carries_the_reproducibility_metadata() -> None:
    row = _quote(2.5).as_row()
    for key in ["paths", "steps", "seed", "tail_value_stderr", "k_cap_ci_low", "k_cap_ci_high"]:
        assert key in row
