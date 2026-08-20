"""Tests for the delta-hedged, Greek-managed listed option strategy."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from equity_options_research.pricing.black_scholes import price
from equity_options_research.pricing.greeks import all_greeks
from equity_options_research.research.final_test_guard import FinalTestGuard, FinalTestLockError
from equity_options_research.research.listed_vol_strategy import (
    DAYS_PER_YEAR,
    MULTIPLIER,
    CashAccount,
    StrategyConfig,
    aggregate_greeks,
    greek_efficiency,
    implied_dividend,
    parity_forward,
    run_listed_trade,
    select_structure,
    size_structures,
    solve_leg,
    usable,
)

SPOT, RATE, DIV, YEAR = 400.0, 0.03, 0.015, 30.0 / 365.0
OOS_START = pd.Timestamp("2023-01-01")


def synthetic_chain(spot: float = SPOT, sigma: float = 0.18, dte: float = 30.0,
                    strikes: np.ndarray | None = None, quote_date: str = "2019-06-03") -> pd.DataFrame:
    """A clean arbitrage-free chain priced from Black-Scholes with a small spread."""
    if strikes is None:
        strikes = np.arange(320.0, 481.0, 5.0)
    T = dte / DAYS_PER_YEAR
    rows = []
    for k in strikes:
        c = price("call", spot, k, T, RATE, DIV, sigma)
        p = price("put", spot, k, T, RATE, DIV, sigma)
        rows.append({"quote_date": pd.Timestamp(quote_date), "strike": float(k), "dte": dte,
                     "spot": spot, "call_bid": max(c - 0.05, 0.01), "call_ask": c + 0.05,
                     "put_bid": max(p - 0.05, 0.01), "put_ask": p + 0.05, "rate": RATE})
    return pd.DataFrame(rows)


# ------------------------------------------------------------ forward and dividend
def test_parity_forward_recovers_the_forward_that_priced_the_chain() -> None:
    chain = synthetic_chain()
    expected = SPOT * np.exp((RATE - DIV) * YEAR)
    assert parity_forward(chain, RATE, YEAR) == pytest.approx(expected, rel=1e-4)


def test_implied_dividend_inverts_the_forward() -> None:
    forward = SPOT * np.exp((RATE - DIV) * YEAR)
    assert implied_dividend(forward, SPOT, RATE, YEAR) == pytest.approx(DIV, abs=1e-9)


def test_forward_is_used_rather_than_spot_when_carry_is_material() -> None:
    """A large dividend pushes the forward below spot; the straddle must follow it."""
    T = YEAR
    strikes = np.arange(360.0, 441.0, 1.0)
    rows = []
    for k in strikes:
        c = price("call", SPOT, k, T, RATE, 0.20, 0.18)
        p = price("put", SPOT, k, T, RATE, 0.20, 0.18)
        rows.append({"quote_date": pd.Timestamp("2019-06-03"), "strike": float(k), "dte": 30.0,
                     "spot": SPOT, "call_bid": max(c - 0.05, 0.01), "call_ask": c + 0.05,
                     "put_bid": max(p - 0.05, 0.01), "put_ask": p + 0.05, "rate": RATE})
    chain = pd.DataFrame(rows)
    forward = parity_forward(chain, RATE, T)
    assert forward < SPOT - 1.0
    legs = select_structure(chain, SPOT, forward, T, RATE, implied_dividend(forward, SPOT, RATE, T),
                            StrategyConfig(wing_delta=None))
    assert legs is not None
    assert abs(legs[0]["strike"] - forward) < abs(legs[0]["strike"] - SPOT)


# ------------------------------------------------------------ quote filters
def test_unusable_quotes_are_rejected() -> None:
    c = StrategyConfig()
    assert usable(1.00, 1.10, c)
    assert not usable(0.0, 0.10, c)            # no bid
    assert not usable(1.10, 1.00, c)           # crossed
    assert not usable(0.01, 0.02, c)           # below the minimum mid
    assert not usable(0.10, 1.00, c)           # spread far too wide
    assert not usable(np.nan, 1.0, c)


# ------------------------------------------------------------ leg solving
def test_solve_leg_recovers_the_volatility_that_priced_it() -> None:
    chain = synthetic_chain(sigma=0.22)
    row = chain[chain.strike == 400.0].iloc[0]
    s = solve_leg(row, "call", SPOT, YEAR, RATE, DIV)
    assert s is not None
    assert s["implied_vol"] == pytest.approx(0.22, rel=2e-2)
    assert not s["stale_vol"]


def test_solve_leg_falls_back_to_the_last_known_volatility() -> None:
    """An end-of-day quote below intrinsic must not cost us the leg's delta."""
    row = pd.Series({"strike": 400.0, "call_bid": 0.001, "call_ask": 0.002,
                     "put_bid": 0.001, "put_ask": 0.002, "spot": SPOT})
    assert solve_leg(row, "call", SPOT, YEAR, RATE, DIV) is None
    s = solve_leg(row, "call", SPOT, YEAR, RATE, DIV, fallback_vol=0.20)
    assert s is not None and s["stale_vol"] and s["implied_vol"] == pytest.approx(0.20)
    assert np.isfinite(s["delta"])


# ------------------------------------------------------------ structure selection
def test_naked_structure_is_two_short_legs_at_the_forward() -> None:
    chain = synthetic_chain()
    fwd = parity_forward(chain, RATE, YEAR)
    legs = select_structure(chain, SPOT, fwd, YEAR, RATE, DIV, StrategyConfig(wing_delta=None))
    assert legs is not None and len(legs) == 2
    assert {x["role"] for x in legs} == {"short_call", "short_put"}
    assert all(x["quantity"] == -1.0 for x in legs)
    assert legs[0]["strike"] == legs[1]["strike"]


@pytest.mark.parametrize("wing", [0.10, 0.15])
def test_wings_are_selected_by_delta_not_by_dollar_distance(wing: float) -> None:
    chain = synthetic_chain(strikes=np.arange(300.0, 501.0, 1.0))
    fwd = parity_forward(chain, RATE, YEAR)
    legs = select_structure(chain, SPOT, fwd, YEAR, RATE, DIV, StrategyConfig(wing_delta=wing))
    assert legs is not None and len(legs) == 4
    call_wing = next(x for x in legs if x["role"] == "long_call_wing")
    put_wing = next(x for x in legs if x["role"] == "long_put_wing")
    assert abs(abs(call_wing["delta"]) - wing) < 0.02
    assert abs(abs(put_wing["delta"]) - wing) < 0.02
    assert call_wing["quantity"] == 1.0 and put_wing["quantity"] == 1.0
    assert call_wing["strike"] > legs[0]["strike"] > put_wing["strike"]


def test_a_wider_wing_delta_sits_closer_to_the_money() -> None:
    chain = synthetic_chain(strikes=np.arange(300.0, 501.0, 1.0))
    fwd = parity_forward(chain, RATE, YEAR)
    ten = select_structure(chain, SPOT, fwd, YEAR, RATE, DIV, StrategyConfig(wing_delta=0.10))
    fifteen = select_structure(chain, SPOT, fwd, YEAR, RATE, DIV, StrategyConfig(wing_delta=0.15))
    assert ten is not None and fifteen is not None
    assert fifteen[2]["strike"] < ten[2]["strike"]     # call wing
    assert fifteen[3]["strike"] > ten[3]["strike"]     # put wing


def test_structure_selection_fails_when_no_strike_lies_outside_the_short_legs() -> None:
    chain = synthetic_chain(strikes=np.array([400.0]))
    fwd = parity_forward(chain, RATE, YEAR)
    assert select_structure(chain, SPOT, fwd, YEAR, RATE, DIV, StrategyConfig(wing_delta=0.10)) is None


def test_sparse_strikes_degrade_the_wing_delta_rather_than_refusing_the_trade() -> None:
    """Documented behaviour: the nearest listed strike is taken even when it is a
    poor match for the delta target. On the real SPY chain the achieved wing
    delta is within 0.05 of target on 149 of 152 entries, with a worst case of
    0.15, so this degradation is measured and reported rather than guarded."""
    chain = synthetic_chain(strikes=np.array([396.0, 398.0, 400.0, 402.0, 404.0]))
    fwd = parity_forward(chain, RATE, YEAR)
    legs = select_structure(chain, SPOT, fwd, YEAR, RATE, DIV, StrategyConfig(wing_delta=0.10))
    assert legs is not None and len(legs) == 4
    call_wing = next(x for x in legs if x["role"] == "long_call_wing")
    assert abs(call_wing["delta"]) > 0.20            # far from the 0.10 target
    assert call_wing["strike"] == 404.0              # the furthest strike available


# ------------------------------------------------------------ portfolio Greeks
def _legs(right_strikes, sigma=0.18):
    return [{**all_greeks(r, SPOT, k, YEAR, RATE, DIV, sigma), "right": r, "strike": k, "quantity": q}
            for r, k, q in right_strikes]


def test_aggregate_greeks_sum_the_legs_and_scale_with_size() -> None:
    legs = _legs([("call", 400.0, -1.0), ("put", 400.0, -1.0)])
    one = aggregate_greeks(legs, SPOT, 1.0)
    ten = aggregate_greeks(legs, SPOT, 10.0)
    for k in ("delta", "gamma", "vega", "theta", "dollar_gamma"):
        assert ten[k] == pytest.approx(10.0 * one[k])
    raw = sum(x["quantity"] * x["gamma"] for x in legs)
    assert one["gamma"] == pytest.approx(raw * MULTIPLIER)


def test_a_short_straddle_has_negative_gamma_and_positive_theta() -> None:
    g = aggregate_greeks(_legs([("call", 400.0, -1.0), ("put", 400.0, -1.0)]), SPOT)
    assert g["gamma"] < 0 and g["dollar_gamma"] < 0
    assert g["vega"] < 0 and g["vega_dollars"] < 0
    assert g["theta"] > 0 and g["theta_per_day"] > 0


def test_wings_reduce_the_magnitude_of_gamma_vega_and_theta() -> None:
    naked = aggregate_greeks(_legs([("call", 400.0, -1.0), ("put", 400.0, -1.0)]), SPOT)
    winged = aggregate_greeks(_legs([("call", 400.0, -1.0), ("put", 400.0, -1.0),
                                     ("call", 440.0, 1.0), ("put", 360.0, 1.0)]), SPOT)
    assert abs(winged["dollar_gamma"]) < abs(naked["dollar_gamma"])
    assert abs(winged["vega_dollars"]) < abs(naked["vega_dollars"])
    assert 0 < winged["theta_per_day"] < naked["theta_per_day"]


def test_dollar_gamma_and_derived_units_are_consistent() -> None:
    g = aggregate_greeks(_legs([("call", 400.0, -1.0), ("put", 400.0, -1.0)]), SPOT)
    assert g["dollar_gamma"] == pytest.approx(g["gamma"] * SPOT**2)
    assert g["vega_dollars"] == pytest.approx(g["vega"] / 100.0)
    assert g["theta_per_day"] == pytest.approx(g["theta"] / DAYS_PER_YEAR)


def test_greek_efficiency_rises_when_theta_rises() -> None:
    g = aggregate_greeks(_legs([("call", 400.0, -1.0), ("put", 400.0, -1.0)]), SPOT)
    richer = {**g, "theta_per_day": g["theta_per_day"] * 2}
    assert greek_efficiency(richer)["theta_per_dollar_gamma"] > greek_efficiency(g)["theta_per_dollar_gamma"]
    assert greek_efficiency(richer)["theta_per_vega"] > greek_efficiency(g)["theta_per_vega"]


# ------------------------------------------------------------ sizing
def test_vega_target_sets_the_size_when_gamma_is_not_binding() -> None:
    unit = {"vega_dollars": -50.0, "dollar_gamma": -1_000.0}
    cfg = StrategyConfig(target_vega_dollars=10_000.0)
    s = size_structures(unit, cfg)
    assert s["desired"] == pytest.approx(200.0)
    assert s["structures"] == 200.0
    assert not s["gamma_capped"]
    assert s["realised_vega"] == pytest.approx(10_000.0)


def test_gamma_cap_reduces_size_and_never_increases_it() -> None:
    cfg = StrategyConfig(target_vega_dollars=10_000.0, gamma_stress_move=0.03,
                         gamma_stress_budget=0.05, reference_capital=1_000_000.0)
    heavy = size_structures({"vega_dollars": -50.0, "dollar_gamma": -5_000_000.0}, cfg)
    assert heavy["gamma_capped"]
    assert heavy["structures"] < 200.0
    assert heavy["sized_stress_loss"] <= cfg.gamma_stress_cap + 1e-6
    light = size_structures({"vega_dollars": -50.0, "dollar_gamma": -1_000.0}, cfg)
    assert not light["gamma_capped"] and light["structures"] == 200.0


def test_size_is_floored_to_whole_structures() -> None:
    s = size_structures({"vega_dollars": -33.0, "dollar_gamma": -1_000.0},
                        StrategyConfig(target_vega_dollars=10_000.0))
    assert s["structures"] == float(int(s["structures"]))
    assert s["structures"] <= s["desired"]
    assert s["rounding_error"] <= 0.0


def test_zero_vega_structure_is_not_traded() -> None:
    s = size_structures({"vega_dollars": 0.0, "dollar_gamma": -1_000.0}, StrategyConfig())
    assert s["structures"] == 0.0


def test_gamma_stress_sizing_mode_targets_the_budget_directly() -> None:
    cfg = StrategyConfig(sizing_mode="gamma_stress", gamma_stress_budget=0.05)
    s = size_structures({"vega_dollars": -50.0, "dollar_gamma": -1_000_000.0}, cfg)
    assert s["sized_stress_loss"] <= cfg.gamma_stress_cap + 1e-6
    assert s["structures"] > 0


# ------------------------------------------------------------ cash account
def test_cash_account_is_self_financing() -> None:
    cash = CashAccount(rate=0.05)
    cash.flow("premium", 1_000.0)
    cash.accrue(365.0)
    assert cash.interest == pytest.approx(50.0)
    assert cash.balance == pytest.approx(1_050.0)
    cash.flow("close", -1_050.0)
    assert cash.balance == pytest.approx(0.0)


def test_cash_account_charges_interest_on_a_negative_balance() -> None:
    cash = CashAccount(rate=0.05)
    cash.flow("buy", -10_000.0)
    cash.accrue(365.0)
    assert cash.interest == pytest.approx(-500.0)


# ------------------------------------------------------------ the trade runner
def _panel(spots: list[float], dtes: list[float], strikes: np.ndarray, sigma: float = 0.18) -> pd.DataFrame:
    rows = []
    base = pd.Timestamp("2019-06-03")
    for i, (s, dte) in enumerate(zip(spots, dtes, strict=True)):
        T = max(dte, 1e-6) / DAYS_PER_YEAR
        for k in strikes:
            c = price("call", s, float(k), T, RATE, DIV, sigma)
            p = price("put", s, float(k), T, RATE, DIV, sigma)
            rows.append({"quote_date": base + pd.Timedelta(days=i), "strike": float(k), "dte": dte,
                         "spot": s, "call_bid": max(c - 0.05, 0.01), "call_ask": c + 0.05,
                         "put_bid": max(p - 0.05, 0.01), "put_ask": p + 0.05, "rate": RATE})
    return pd.DataFrame(rows)


def _run(spots, dtes, cfg=None, structures=10.0):
    strikes = np.arange(360.0, 441.0, 5.0)
    cfg = cfg or StrategyConfig(wing_delta=None)
    chain = _panel([spots[0]], [dtes[0]], strikes)
    fwd = parity_forward(chain, RATE, dtes[0] / DAYS_PER_YEAR)
    legs = select_structure(chain, spots[0], fwd, dtes[0] / DAYS_PER_YEAR, RATE, DIV, cfg)
    assert legs is not None
    return legs, run_listed_trade(legs, structures, _panel(spots, dtes, strikes), cfg, RATE)


def test_trade_reconciles_exactly() -> None:
    _, res = _run([400.0, 402.0, 398.0, 401.0, 400.0], [30.0, 25.0, 18.0, 12.0, 6.0])
    assert abs(res["reconciliation_error"]) < 1e-8
    assert res["net_pnl"] == pytest.approx(
        res["gross_pnl"] + res["financing"] - res["total_costs"], abs=1e-8)


def test_exit_rule_closes_at_the_configured_dte() -> None:
    _, res = _run([400.0] * 6, [30.0, 24.0, 18.0, 12.0, 7.0, 3.0])
    assert res["days_held"] == 5                      # stops on the DTE = 7 observation
    assert res["daily"].iloc[-1]["dte"] == 7.0
    assert bool(res["daily"].iloc[-1]["closing"])


def test_hedge_removes_the_option_delta_on_every_open_day() -> None:
    _, res = _run([400.0, 410.0, 392.0, 405.0, 400.0], [30.0, 25.0, 18.0, 12.0, 6.0])
    daily = res["daily"]
    open_days = daily[~daily.closing.astype(bool)]
    assert np.allclose(open_days.residual_delta.to_numpy(float), 0.0, atol=1e-9)
    assert np.allclose((open_days.delta + open_days.hedge_shares).to_numpy(float), 0.0, atol=1e-9)


def test_hedge_is_flat_after_the_closing_day() -> None:
    _, res = _run([400.0, 405.0, 398.0], [30.0, 20.0, 6.0])
    assert res["daily"].iloc[-1]["hedge_shares"] == pytest.approx(0.0)


def test_a_flat_market_earns_theta_net_of_costs() -> None:
    """No spot movement and no volatility change: the seller keeps decay."""
    _, res = _run([400.0] * 5, [30.0, 24.0, 18.0, 12.0, 6.0])
    assert res["gross_pnl"] > 0
    assert res["hedge_pnl"] == pytest.approx(0.0, abs=1e-6)   # delta never moves


def test_wings_bound_the_option_loss_on_a_large_move() -> None:
    naked_legs, naked = _run([400.0, 340.0, 340.0], [30.0, 20.0, 6.0])
    winged_legs, winged = _run([400.0, 340.0, 340.0], [30.0, 20.0, 6.0],
                               cfg=StrategyConfig(wing_delta=0.15))
    assert len(winged_legs) == 4
    assert winged["option_pnl"] > naked["option_pnl"]


def test_costs_scale_with_the_number_of_legs() -> None:
    _, naked = _run([400.0, 401.0, 400.0], [30.0, 20.0, 6.0])
    _, winged = _run([400.0, 401.0, 400.0], [30.0, 20.0, 6.0], cfg=StrategyConfig(wing_delta=0.15))
    assert winged["option_commissions"] > naked["option_commissions"]
    assert winged["option_spread_cost"] > naked["option_spread_cost"]


def test_financing_is_not_zero_when_cash_is_held() -> None:
    _, res = _run([400.0, 401.0, 400.0], [30.0, 20.0, 6.0])
    assert res["financing"] != 0.0


# ------------------------------------------------------------ attribution
def test_daily_attribution_is_reported_and_tracks_the_option_mark() -> None:
    """One-day intervals, where a second-order expansion is meant to hold."""
    rng = np.random.default_rng(4)
    spots = [400.0 * float(x) for x in np.cumprod(1 + rng.normal(0, 0.008, 24))]
    dtes = list(np.arange(30.0, 6.0, -1.0))
    _, res = _run(spots, dtes)
    daily = res["daily"].dropna(subset=["option_mark_pnl"])
    four = daily[["delta_pnl", "gamma_pnl", "vega_pnl", "theta_pnl"]].sum(axis=1)
    assert len(daily) >= 15
    assert daily.option_mark_pnl.corr(four) > 0.99
    residual = (daily.option_mark_pnl - four).abs().sum()
    assert residual < 0.05 * daily.option_mark_pnl.abs().sum()


def test_hedge_pnl_offsets_the_attributed_delta_term() -> None:
    """A perfect daily delta hedge holds exactly minus the option delta."""
    _, res = _run([400.0, 406.0, 394.0, 401.0, 400.0], [30.0, 25.0, 18.0, 12.0, 6.0])
    daily = res["daily"]
    assert res["hedge_pnl"] == pytest.approx(-daily.delta_pnl.sum(), rel=1e-6)


# ------------------------------------------------------------ protocol
def test_oos_guard_blocks_the_final_window_until_unlocked() -> None:
    guard = FinalTestGuard(final_test_start=OOS_START, allow_final_test=False)
    frame = pd.DataFrame({"date": pd.date_range("2022-11-01", periods=6, freq="MS")})
    with pytest.raises(FinalTestLockError):
        guard.final_test_frame(frame, date_column="date")
    with pytest.raises(FinalTestLockError):
        guard.check_development_only(frame, date_column="date")
    guard.unlock("frozen specification hashed")
    assert len(guard.final_test_frame(frame, date_column="date")) == 4


def test_development_slice_contains_no_out_of_sample_dates() -> None:
    guard = FinalTestGuard(final_test_start=OOS_START, allow_final_test=False)
    frame = pd.DataFrame({"date": pd.date_range("2022-11-01", periods=6, freq="MS")})
    dev = guard.development_frame(frame, date_column="date")
    assert dev["date"].max() < OOS_START
    guard.check_development_only(dev, date_column="date")


def test_frozen_specification_hash_detects_any_change() -> None:
    spec = {"structure": "short ATM straddle", "target_vega_dollars": 10_000.0,
            "gamma_stress_budget": 0.05, "exit_dte": 7}
    digest = hashlib.sha256(json.dumps(spec, indent=2, sort_keys=True).encode()).hexdigest()
    reloaded = json.loads(json.dumps(spec, indent=2, sort_keys=True))
    assert hashlib.sha256(json.dumps(reloaded, indent=2, sort_keys=True).encode()).hexdigest() == digest
    for change in [{"exit_dte": 5}, {"gamma_stress_budget": 0.06}, {"target_vega_dollars": 10_001.0}]:
        tampered = {**spec, **change}
        assert hashlib.sha256(json.dumps(tampered, indent=2, sort_keys=True).encode()).hexdigest() != digest


def test_configuration_gamma_cap_is_a_fraction_of_reference_capital() -> None:
    cfg = StrategyConfig(reference_capital=2_000_000.0, gamma_stress_budget=0.05)
    assert cfg.gamma_stress_cap == pytest.approx(100_000.0)
