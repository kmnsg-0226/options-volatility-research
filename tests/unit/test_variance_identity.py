"""The log-contract identity, tested against the implementation the engine uses.

These assertions carry the project's central mathematical claim: that realised
variance decomposes into a static log contract plus a dynamic share position,
and that the dynamic position is ``N (2/T)(1/F - 1/S)`` — model-free, with no
volatility or dividend input. ``canonical_variance_engine`` imports
``hedge_shares`` from the module under test, so what is verified here is the
formula the backtest actually runs.
"""

from __future__ import annotations

import numpy as np
import pytest

from equity_options_research.research.canonical_variance_engine import realised_variance
from equity_options_research.research.variance_identity import (
    discretisation_residual,
    dynamic_leg_gain,
    hedge_pnl_from_path,
    hedge_shares,
    log_contract_gain,
    reconstructed_variance,
    theoretical_hedge_path,
)

YEAR = 30.0 / 365.0
NOTIONAL, FORWARD = 1_000_000.0, 100.0


def gbm(steps: int, sigma: float, seed: int, spot: float = 100.0, years: float = YEAR) -> np.ndarray:
    rng = np.random.default_rng(seed)
    dt = years / steps
    shocks = rng.normal(-0.5 * sigma**2 * dt, sigma * np.sqrt(dt), steps)
    return spot * np.exp(np.concatenate(([0.0], np.cumsum(shocks))))


# ------------------------------------------------------- log-contract reconstruction
def test_identity_is_exact_up_to_the_cubic_remainder() -> None:
    """dynamic leg + log contract - sum(x^2) is exactly the residual, by construction."""
    path = gbm(60, 0.25, seed=1)
    total = dynamic_leg_gain(path) + log_contract_gain(path)
    squared = float(np.sum(np.log(path[1:] / path[:-1]) ** 2))
    assert total - squared == pytest.approx(discretisation_residual(path), abs=1e-12)


def test_a_flat_path_carries_no_variance_and_no_hedge_gain() -> None:
    flat = np.full(25, 100.0)
    assert dynamic_leg_gain(flat) == pytest.approx(0.0)
    assert log_contract_gain(flat) == pytest.approx(0.0)
    assert reconstructed_variance(flat, YEAR) == pytest.approx(0.0)
    shares, pnl, _ = theoretical_hedge_path(flat, NOTIONAL, YEAR, FORWARD)
    assert pnl == pytest.approx(0.0)


def test_monotonic_paths_reconstruct_their_realised_variance() -> None:
    for direction in (1.0, -1.0):
        path = 100.0 * np.exp(np.cumsum(np.r_[0.0, np.full(40, direction * 0.002)]))
        assert reconstructed_variance(path, YEAR) == pytest.approx(
            realised_variance(path, YEAR), rel=2e-3)


def test_a_whipsaw_returns_to_its_start_but_still_carries_variance() -> None:
    """The static leg alone cannot see this path; only the dynamic leg does."""
    path = np.array([100.0, 108.0, 100.0, 108.0, 100.0])
    assert log_contract_gain(path) == pytest.approx(0.0, abs=1e-12)
    assert reconstructed_variance(path, YEAR) > 0.0
    assert realised_variance(path, YEAR) > 0.0


def test_reconstruction_matches_the_engine_convention_on_a_diffusive_path() -> None:
    path = gbm(252, 0.20, seed=7, years=1.0)
    assert reconstructed_variance(path, 1.0) == pytest.approx(realised_variance(path, 1.0), rel=5e-3)


# ------------------------------------------------------------- cubic remainder
def test_down_moves_under_deliver_and_up_moves_over_deliver() -> None:
    down = 100.0 * np.exp(np.cumsum(np.r_[0.0, np.full(20, -0.01)]))
    up = 100.0 * np.exp(np.cumsum(np.r_[0.0, np.full(20, +0.01)]))
    assert discretisation_residual(down) < 0.0
    assert discretisation_residual(up) > 0.0


def test_the_residual_is_third_order_in_the_step_size() -> None:
    """Halving the move should cut the residual by roughly eight."""
    coarse = discretisation_residual(100.0 * np.exp(np.cumsum(np.r_[0.0, np.full(8, -0.04)])))
    fine = discretisation_residual(100.0 * np.exp(np.cumsum(np.r_[0.0, np.full(8, -0.02)])))
    assert abs(fine) < abs(coarse)
    assert abs(coarse / fine) == pytest.approx(8.0, rel=0.15)


def test_refining_a_fixed_move_drives_the_residual_to_zero() -> None:
    prev = None
    for steps in (10, 40, 160, 640):
        path = 100.0 * np.exp(np.linspace(0.0, -0.20, steps + 1))
        r = abs(discretisation_residual(path))
        if prev is not None:
            assert r < prev
        prev = r
    assert prev < 1e-4


# --------------------------------------------------------- GBM / synthetic convergence
@pytest.mark.parametrize("sigma", [0.12, 0.25, 0.45])
def test_gbm_paths_reconstruct_their_variance_closely(sigma: float) -> None:
    path = gbm(2000, sigma, seed=int(sigma * 1000), years=1.0)
    assert reconstructed_variance(path, 1.0) == pytest.approx(realised_variance(path, 1.0), rel=1e-2)


def test_finer_sampling_shrinks_the_gap_to_realised_variance() -> None:
    gaps = []
    for steps in (25, 100, 400, 1600):
        path = gbm(steps, 0.30, seed=3, years=1.0)
        gaps.append(abs(reconstructed_variance(path, 1.0) - realised_variance(path, 1.0)))
    assert gaps[-1] < gaps[0]


# ------------------------------------------------------- theoretical hedge identity
def test_the_hedge_is_flat_exactly_at_the_forward() -> None:
    assert float(hedge_shares(NOTIONAL, YEAR, FORWARD, FORWARD)) == pytest.approx(0.0)


def test_the_hedge_is_short_below_the_forward_and_long_above() -> None:
    assert float(hedge_shares(NOTIONAL, YEAR, FORWARD, 90.0)) < 0.0
    assert float(hedge_shares(NOTIONAL, YEAR, FORWARD, 110.0)) > 0.0


def test_the_hedge_scales_linearly_with_notional() -> None:
    one = float(hedge_shares(NOTIONAL, YEAR, FORWARD, 95.0))
    three = float(hedge_shares(3 * NOTIONAL, YEAR, FORWARD, 95.0))
    assert three == pytest.approx(3.0 * one)


def test_the_hedge_scales_inversely_with_maturity() -> None:
    short = float(hedge_shares(NOTIONAL, YEAR, FORWARD, 95.0))
    long = float(hedge_shares(NOTIONAL, 2 * YEAR, FORWARD, 95.0))
    assert long == pytest.approx(0.5 * short)


def test_the_hedge_needs_no_volatility_or_dividend_input() -> None:
    """Its entire argument list is notional, maturity, forward and spot."""
    import inspect

    assert set(inspect.signature(hedge_shares).parameters) == {
        "notional", "year_fraction", "forward", "spot"}


def test_the_hedge_rejects_degenerate_inputs() -> None:
    for bad in ({"year_fraction": 0.0}, {"year_fraction": -0.1}, {"forward": 0.0}, {"forward": -5.0}):
        kwargs = {"notional": NOTIONAL, "year_fraction": YEAR, "forward": FORWARD, "spot": 100.0, **bad}
        with pytest.raises(ValueError):
            hedge_shares(**kwargs)


def test_hedge_pnl_uses_the_share_count_held_into_each_step() -> None:
    shares = np.array([10.0, -4.0, 7.0])
    spot = np.array([100.0, 102.0, 99.0])
    assert hedge_pnl_from_path(shares, spot) == pytest.approx(10.0 * 2.0 + (-4.0) * (-3.0))


def test_a_change_after_the_final_step_cannot_earn_anything() -> None:
    spot = np.array([100.0, 103.0, 101.0])
    a = hedge_pnl_from_path(np.array([5.0, 2.0, 0.0]), spot)
    b = hedge_pnl_from_path(np.array([5.0, 2.0, 999.0]), spot)
    assert a == pytest.approx(b)


def test_the_short_variance_hedge_loses_through_a_whipsaw() -> None:
    """Selling variance and hedging it is short gamma; a round trip costs money."""
    path = np.array([100.0, 112.0, 100.0, 112.0, 100.0])
    _, pnl, turnover = theoretical_hedge_path(path, NOTIONAL, YEAR, FORWARD)
    assert pnl < 0.0
    assert turnover > 0.0


def test_the_hedge_path_matches_the_formula_at_every_observation() -> None:
    path = gbm(30, 0.22, seed=11)
    shares, pnl, _ = theoretical_hedge_path(path, NOTIONAL, YEAR, FORWARD)
    assert np.allclose(shares, hedge_shares(NOTIONAL, YEAR, FORWARD, path))
    assert pnl == pytest.approx(hedge_pnl_from_path(shares, path))


def test_the_engine_hedges_with_this_exact_function() -> None:
    """Guards against the formula being restated anywhere else."""
    from equity_options_research.research import canonical_variance_engine as engine

    assert engine.hedge_shares is hedge_shares
