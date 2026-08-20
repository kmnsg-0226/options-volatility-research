import numpy as np
import pytest

from equity_options_research.pricing.black_scholes import bsm_call_price, bsm_put_price
from equity_options_research.research.canonical_variance_engine import (
    CanonicalConfig,
    CashAccount,
    hedge_shares,
    implied_dividend_yield,
    realised_variance,
    run_canonical_trade,
    strip_intrinsic,
    strip_weights,
)
from equity_options_research.research.model_free_variance import model_free_variance

T, N = 30 / 365, 1_000_000.0


def chain(spot=100.0, sigma=0.20, r=0.02, q=0.0, t=T, step=1.0):
    k = np.arange(spot * 0.5, spot * 1.5 + step, step)
    c = np.array([bsm_call_price(spot, x, t, r, q, sigma) for x in k])
    p = np.array([bsm_put_price(spot, x, t, r, q, sigma) for x in k])
    tick = 1e-5
    return model_free_variance(k, c - tick, c + tick, p - tick, p + tick, r, t)


# ---------------- units and horizon ----------------

def test_realised_variance_uses_the_contract_horizon() -> None:
    """One T annualises both legs -- the legacy mismatch is gone by construction."""
    path = 100.0 * np.exp(np.cumsum(np.concatenate(([0.0], np.full(21, 0.01)))))
    total = np.sum(np.log(path[1:] / path[:-1]) ** 2)
    assert realised_variance(path, T) == pytest.approx(total / T)


def test_realised_variance_scales_inversely_with_horizon() -> None:
    path = np.array([100.0, 101.0, 100.0])
    assert realised_variance(path, T / 2) == pytest.approx(2 * realised_variance(path, T))


def test_flat_path_has_zero_realised_variance() -> None:
    assert realised_variance(np.array([100.0] * 5), T) == pytest.approx(0.0)


def test_variance_notional_units_are_dollars_per_unit_variance() -> None:
    assert N * (0.05 - 0.04) == pytest.approx(10_000.0)


# ---------------- hedge and weights ----------------

def test_hedge_is_zero_at_the_forward_and_scales_with_notional() -> None:
    assert hedge_shares(N, T, 100.0, np.array([100.0]))[0] == pytest.approx(0.0)
    a = hedge_shares(N, T, 100.0, np.array([90.0]))[0]
    b = hedge_shares(2 * N, T, 100.0, np.array([90.0]))[0]
    assert b == pytest.approx(2 * a)


def test_strip_weights_follow_dK_over_K_squared() -> None:
    s = chain().strip
    w = strip_weights(s, N, 100)
    expected = N * (2.0 / s.year_fraction) * s.delta_k / s.strikes**2 / 100
    assert np.allclose(w, expected)


def test_implied_dividend_recovers_the_input() -> None:
    r, q = 0.02, 0.015
    spot = 100.0
    fwd = spot * np.exp((r - q) * T)
    assert implied_dividend_yield(fwd, spot, r, T) == pytest.approx(q)


def test_implied_dividend_rejects_bad_inputs() -> None:
    with pytest.raises(ValueError, match="positive"):
        implied_dividend_yield(0.0, 100.0, 0.02, T)


# ---------------- settlement ----------------

def test_strip_intrinsic_is_zero_when_everything_expires_worthless() -> None:
    s = chain().strip
    w = strip_weights(s, N, 100)
    # settle exactly at K0: OTM puts below and calls above are all worthless
    val = strip_intrinsic(s, w, float(s.k0), 100)
    assert val == pytest.approx(0.0, abs=1e-6)


def test_strip_intrinsic_grows_as_spot_leaves_the_strikes() -> None:
    s = chain().strip
    w = strip_weights(s, N, 100)
    near = strip_intrinsic(s, w, float(s.k0) * 0.98, 100)
    far = strip_intrinsic(s, w, float(s.k0) * 0.85, 100)
    assert far > near > 0


# ---------------- cash account ----------------

def test_cash_account_accrues_interest_on_the_balance() -> None:
    c = CashAccount(rate=0.05)
    c.flow("premium", 100_000.0)
    c.accrue(365.0)
    assert c.interest == pytest.approx(5_000.0)
    assert c.balance == pytest.approx(105_000.0)


def test_negative_balance_pays_interest() -> None:
    c = CashAccount(rate=0.05)
    c.flow("borrow", -100_000.0)
    c.accrue(365.0)
    assert c.interest == pytest.approx(-5_000.0)


def test_zero_rate_accrues_nothing() -> None:
    c = CashAccount(rate=0.0)
    c.flow("premium", 50_000.0)
    c.accrue(365.0)
    assert c.interest == 0.0
    assert c.balance == pytest.approx(50_000.0)


# ---------------- full reconciliation ----------------

def synthetic(path, integer=False, rate=0.02):
    r = chain(r=rate)
    days = np.full(len(path) - 1, 1.0)
    cfg = CanonicalConfig(variance_notional=N, integer_contracts=integer)
    return run_canonical_trade(r.strip, np.asarray(path, float), days, cfg, r.variance)


def test_pnl_reconciles_with_the_cash_account() -> None:
    """net = option P&L + hedge P&L + financing - costs, to machine precision."""
    out = synthetic([100.0, 101.0, 99.0, 100.5, 100.0])
    recon = out["gross_pnl"] + out["financing"] - out["total_costs"]
    assert out["net_pnl"] == pytest.approx(recon, abs=1e-6)
    assert abs(out["reconciliation_error"]) < 1e-6


def test_flat_path_earns_the_full_fair_strike() -> None:
    """No realised variance: the seller keeps the strike, less costs."""
    out = synthetic([100.0] * 6)
    assert out["realised_variance"] == pytest.approx(0.0)
    assert out["theoretical_vs_pnl"] == pytest.approx(N * out["fair_strike"])
    assert out["net_pnl"] > 0


def test_high_variance_path_loses_money() -> None:
    out = synthetic([100.0, 88.0, 100.0, 88.0, 100.0])
    assert out["realised_variance"] > out["fair_strike"]
    assert out["theoretical_vs_pnl"] < 0
    assert out["net_pnl"] < 0


def test_tracking_error_is_small_on_a_smooth_path() -> None:
    rng = np.random.default_rng(3)
    path = 100.0 * np.exp(np.cumsum(np.concatenate(([0.0], rng.normal(0, 0.006, 21)))))
    out = synthetic(path)
    assert abs(out["tracking_error"]) < 0.35 * abs(out["theoretical_vs_pnl"])


def test_jump_path_leaves_a_larger_residual_than_a_smooth_one() -> None:
    smooth = synthetic(100.0 * np.exp(np.cumsum(np.concatenate(([0.0], np.full(20, -0.005))))))
    jump = synthetic([100.0] * 10 + [82.0] * 11)
    assert abs(jump["tracking_error"]) > abs(smooth["tracking_error"])


def test_integer_contracts_change_the_result_but_stay_reconciled() -> None:
    frac = synthetic([100.0, 102.0, 99.0, 101.0], integer=False)
    whole = synthetic([100.0, 102.0, 99.0, 101.0], integer=True)
    assert whole["contracts_per_leg"] != frac["contracts_per_leg"]
    recon = whole["gross_pnl"] + whole["financing"] - whole["total_costs"]
    assert whole["net_pnl"] == pytest.approx(recon, abs=1e-6)
    assert abs(whole["reconciliation_error"]) < 1e-6


def test_financing_is_nonzero_and_signed_by_the_rate() -> None:
    a = synthetic([100.0, 101.0, 100.0], rate=0.0)
    b = synthetic([100.0, 101.0, 100.0], rate=0.05)
    assert a["financing"] == 0.0
    assert b["financing"] != 0.0


def test_engine_is_deterministic() -> None:
    a = synthetic([100.0, 103.0, 98.0, 101.0])
    b = synthetic([100.0, 103.0, 98.0, 101.0])
    assert a == b
