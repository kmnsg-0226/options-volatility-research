"""Tests for the V6 exposure rules and the development/OOS protocol."""

from __future__ import annotations

import hashlib
import json

import numpy as np
import pandas as pd
import pytest

from equity_options_research.research import risk_timing as rt
from equity_options_research.research.final_test_guard import FinalTestGuard, FinalTestLockError

OOS_START = pd.Timestamp("2023-01-01")


def monthly(n: int, start: str = "2013-01-01") -> pd.DatetimeIndex:
    return pd.date_range(start, periods=n, freq="MS")


# --------------------------------------------------------------- OOS protocol
def test_guard_blocks_out_of_sample_until_unlocked() -> None:
    guard = FinalTestGuard(final_test_start=OOS_START, allow_final_test=False)
    frame = pd.DataFrame({"date": monthly(160)})
    with pytest.raises(FinalTestLockError):
        guard.final_test_frame(frame, date_column="date")
    guard.unlock("frozen specification hashed")
    assert len(guard.final_test_frame(frame, date_column="date")) > 0


def test_guard_rejects_a_development_table_containing_oos_rows() -> None:
    guard = FinalTestGuard(final_test_start=OOS_START, allow_final_test=False)
    leaked = pd.DataFrame({"date": [pd.Timestamp("2022-12-01"), pd.Timestamp("2023-02-01")]})
    with pytest.raises(FinalTestLockError):
        guard.check_development_only(leaked, date_column="date")
    clean = pd.DataFrame({"date": [pd.Timestamp("2022-12-01")]})
    guard.check_development_only(clean, date_column="date")


def test_development_split_excludes_the_oos_boundary_date() -> None:
    guard = FinalTestGuard(final_test_start=OOS_START, allow_final_test=False)
    frame = pd.DataFrame({"date": [OOS_START - pd.Timedelta(days=1), OOS_START]})
    assert list(guard.development_frame(frame, date_column="date")["date"]) == [OOS_START - pd.Timedelta(days=1)]


# ----------------------------------------------------------- causal reference
def test_expanding_reference_never_sees_the_current_observation() -> None:
    idx = monthly(40)
    values = pd.Series(np.arange(1.0, 41.0), index=idx)
    ref = rt.expanding_reference(values, minimum_observations=5)
    assert ref.iloc[:5].isna().all()
    # at position 5 the reference is the median of the first five values only
    assert ref.iloc[5] == pytest.approx(np.median(values.iloc[:5]))
    assert ref.iloc[-1] == pytest.approx(np.median(values.iloc[:-1]))


def test_error_scale_admits_a_label_only_once_the_contract_has_expired() -> None:
    idx = monthly(30)
    errors = pd.Series(np.linspace(-0.02, 0.02, 30), index=idx)
    # every contract expires a month after entry, so the previous trade is still
    # open when the next one is entered
    observable = pd.Series(idx + pd.Timedelta(days=31), index=idx)
    scale = rt.expanding_error_scale(errors, observable, minimum_observations=6)
    assert scale.iloc[:6].isna().all()
    at = idx[10]
    expected = errors[observable < at].std(ddof=1)
    assert scale.loc[at] == pytest.approx(expected)


def test_error_scale_would_be_larger_if_open_trades_were_counted() -> None:
    """Guards against keying observability off the entry date instead of expiry."""
    idx = monthly(30)
    errors = pd.Series(np.linspace(-0.02, 0.02, 30), index=idx)
    causal = rt.expanding_error_scale(errors, pd.Series(idx + pd.Timedelta(days=31), index=idx), 6)
    leaky = rt.expanding_error_scale(errors, pd.Series(idx, index=idx), 6)
    assert causal.dropna().index[0] > leaky.dropna().index[0]


# ------------------------------------------------------------------- branch A
def test_inverse_variance_scaler_moves_against_the_variance_level() -> None:
    idx = monthly(60)
    strike = pd.Series(np.r_[np.full(40, 0.04), np.full(20, 0.16)], index=idx)
    scale = rt.inverse_variance_scale(strike)
    assert scale.iloc[-1] < scale.iloc[35]
    assert scale.iloc[-1] == pytest.approx(0.25)          # 0.04 / 0.16 = 0.25, at the floor


def test_inverse_vol_scaler_is_the_square_root_of_the_variance_scaler() -> None:
    idx = monthly(60)
    strike = pd.Series(np.r_[np.full(40, 0.04), np.full(20, 0.09)], index=idx)
    variance, vol = rt.inverse_variance_scale(strike), rt.inverse_vol_scale(strike)
    assert vol.iloc[-1] == pytest.approx(np.sqrt(variance.iloc[-1]))
    assert vol.iloc[-1] > variance.iloc[-1]               # the square root scaler cuts less


@pytest.mark.parametrize("scaler", [rt.inverse_variance_scale, rt.inverse_vol_scale])
def test_scalers_respect_their_bounds(scaler) -> None:
    idx = monthly(80)
    rng = np.random.default_rng(0)
    strike = pd.Series(np.exp(rng.normal(-3.5, 1.4, 80)), index=idx)
    scale = scaler(strike, 0.25, 1.50).dropna()
    assert scale.min() >= 0.25 and scale.max() <= 1.50
    tight = scaler(strike, 0.5, 1.0).dropna()
    assert tight.min() >= 0.5 and tight.max() <= 1.0


# ------------------------------------------------------------------- branch C
def test_expected_vrp_is_the_strike_less_the_forecast() -> None:
    idx = monthly(4)
    k = pd.Series([0.05, 0.04, 0.03, 0.02], index=idx)
    f = pd.Series([0.03, 0.04, 0.05, 0.06], index=idx)
    assert list(rt.expected_vrp(k, f).round(10)) == [0.02, 0.0, -0.02, -0.04]


def test_expected_vrp_against_implied_variance_is_identically_zero() -> None:
    """Why raw implied variance cannot serve as the expected-RV input."""
    k = pd.Series([0.05, 0.04, 0.03], index=monthly(3))
    assert (rt.expected_vrp(k, k) == 0).all()


def test_abstention_rule_takes_only_positive_premium_months() -> None:
    evrp = pd.Series([0.01, -0.01, 0.0, 0.02], index=monthly(4))
    assert list(rt.participate_if_positive(evrp)) == [1.0, 0.0, 0.0, 1.0]


def test_uncertainty_buffer_is_stricter_than_the_bare_sign_rule() -> None:
    idx = monthly(4)
    evrp = pd.Series([0.01, 0.05, 0.001, 0.02], index=idx)
    err = pd.Series([0.04, 0.04, 0.04, 0.04], index=idx)
    buffered = rt.participate_with_buffer(evrp, err, 0.5)     # threshold 0.02
    assert list(buffered) == [0.0, 1.0, 0.0, 0.0]
    assert buffered.sum() <= rt.participate_if_positive(evrp).sum()


def test_buffer_abstains_when_the_error_scale_is_unknown() -> None:
    idx = monthly(3)
    evrp = pd.Series([0.05, 0.05, 0.05], index=idx)
    err = pd.Series([np.nan, np.nan, 0.01], index=idx)
    assert list(rt.participate_with_buffer(evrp, err, 0.5)) == [0.0, 0.0, 1.0]


def test_continuous_premium_scale_rises_with_premium_and_stops_at_the_cap() -> None:
    idx = monthly(4)
    evrp = pd.Series([-0.01, 0.01, 0.02, 0.10], index=idx)
    err = pd.Series(0.02, index=idx)
    scale = rt.continuous_premium_scale(evrp, err)
    assert list(scale) == [0.0, 0.5, 1.0, 1.5]
    assert scale.is_monotonic_increasing


# ------------------------------------------------------------- branches D / E
def test_term_structure_scaler_cuts_exposure_when_the_state_is_elevated() -> None:
    idx = monthly(60)
    ratio = pd.Series(np.r_[np.full(40, 0.9), np.full(20, 1.4)], index=idx)
    scale = rt.term_structure_scale(ratio, minimum_observations=12)
    assert scale.iloc[-1] < 1.0
    assert scale.iloc[30] == pytest.approx(1.0)           # flat history, z = 0
    assert scale.min() >= 0.25 and scale.max() <= 1.0


def test_term_structure_scaler_never_levers_above_one() -> None:
    idx = monthly(60)
    rng = np.random.default_rng(3)
    ratio = pd.Series(np.r_[rng.normal(1.0, 0.1, 40), np.full(20, 0.2)], index=idx)
    assert rt.term_structure_scale(ratio, minimum_observations=12).max() <= 1.0


def test_surface_state_splits_variance_across_the_wings() -> None:
    strikes = np.array([70.0, 80.0, 90.0, 100.0, 110.0, 120.0])
    quotes = np.array([0.5, 1.0, 3.0, 6.0, 2.0, 0.5])
    delta_k = np.full(6, 10.0)
    state = rt.surface_state(strikes, quotes, delta_k, forward=100.0, k0=100.0)
    assert 0.0 < state["put_share"] < 1.0
    assert 0.0 < state["deep_down_share"] < state["put_share"]
    assert state["strip_low_moneyness"] == pytest.approx(0.70)
    assert state["strip_high_moneyness"] == pytest.approx(1.20)


def test_surface_state_skew_wedge_is_signed_by_which_wing_is_richer() -> None:
    strikes = np.array([85.0, 90.0, 95.0, 100.0, 105.0, 110.0, 115.0])
    delta_k = np.full(7, 5.0)
    rich_puts = rt.surface_state(strikes, np.array([4.0, 4.0, 4.0, 5.0, 1.0, 1.0, 1.0]),
                                 delta_k, 100.0, 100.0)
    rich_calls = rt.surface_state(strikes, np.array([1.0, 1.0, 1.0, 5.0, 4.0, 4.0, 4.0]),
                                  delta_k, 100.0, 100.0)
    assert rich_puts["skew_wedge"] > 0 > rich_calls["skew_wedge"]
    assert rich_puts["down_up_ratio"] > rich_calls["down_up_ratio"]


def test_surface_state_rejects_an_empty_strip() -> None:
    with pytest.raises(ValueError):
        rt.surface_state(np.array([100.0]), np.array([0.0]), np.array([1.0]), 100.0, 100.0)


# ------------------------------------------------------------------- branch F
def test_carry_to_risk_scaler_rewards_premium_per_unit_of_risk() -> None:
    idx = monthly(60)
    evrp = pd.Series(0.02, index=idx)
    risk = pd.Series(np.r_[np.full(40, 0.2), np.full(20, 0.4)], index=idx)
    scale = rt.carry_to_risk_scale(evrp, risk, minimum_observations=12)
    assert scale.iloc[-1] < scale.iloc[35]                # same carry, twice the risk
    assert scale.min() >= 0.0 and scale.max() <= 1.5


def test_carry_to_risk_scaler_abstains_on_negative_carry() -> None:
    idx = monthly(60)
    evrp = pd.Series(np.r_[np.full(40, 0.02), np.full(20, -0.02)], index=idx)
    scale = rt.carry_to_risk_scale(evrp, pd.Series(0.2, index=idx), minimum_observations=12)
    assert scale.iloc[-1] == pytest.approx(0.0)


# ------------------------------------------------------- controls and exposure
def test_average_exposure_normalisation_hits_its_target() -> None:
    scale = pd.Series([0.2, 0.6, 1.0, 1.4], index=monthly(4))
    assert rt.normalise_average_exposure(scale).mean() == pytest.approx(1.0)
    assert rt.normalise_average_exposure(scale, 0.8).mean() == pytest.approx(0.8)


def test_average_exposure_normalisation_leaves_a_degenerate_series_alone() -> None:
    zero = pd.Series(0.0, index=monthly(4))
    pd.testing.assert_series_equal(rt.normalise_average_exposure(zero), zero)


def test_flat_control_matches_the_rule_average_but_never_varies() -> None:
    scale = pd.Series([0.25, 0.75, 1.5, 0.5], index=monthly(4))
    flat = rt.flat_control(scale)
    assert flat.mean() == pytest.approx(scale.mean())
    assert flat.nunique() == 1


def test_apply_scale_is_linear_in_the_named_columns_only() -> None:
    idx = monthly(3)
    ledger = pd.DataFrame({"net_pnl": [100.0, -50.0, 20.0], "fair_strike": [0.04, 0.05, 0.06]}, index=idx)
    scaled = rt.apply_scale(ledger, pd.Series([0.5, 1.0, 0.0], index=idx), ["net_pnl"])
    assert list(scaled.net_pnl) == [50.0, -50.0, 0.0]
    assert list(scaled.fair_strike) == [0.04, 0.05, 0.06]
    assert list(scaled.exposure_scale) == [0.5, 1.0, 0.0]


def test_apply_scale_treats_a_missing_date_as_no_position() -> None:
    idx = monthly(3)
    ledger = pd.DataFrame({"net_pnl": [100.0, -50.0, 20.0]}, index=idx)
    scaled = rt.apply_scale(ledger, pd.Series([0.5], index=idx[:1]), ["net_pnl"])
    assert list(scaled.net_pnl) == [50.0, 0.0, 0.0]


# ---------------------------------------------- parameter state and freezing
def test_scalers_are_pure_functions_of_their_history() -> None:
    """The scale at a date must not change when later observations are appended."""
    idx = monthly(60)
    rng = np.random.default_rng(11)
    strike = pd.Series(np.exp(rng.normal(-3.5, 0.8, 60)), index=idx)
    short = rt.inverse_variance_scale(strike.iloc[:45])
    long = rt.inverse_variance_scale(strike)
    pd.testing.assert_series_equal(short, long.iloc[:45])


def test_term_structure_state_is_also_frozen_by_history() -> None:
    idx = monthly(60)
    rng = np.random.default_rng(12)
    ratio = pd.Series(rng.normal(1.0, 0.15, 60), index=idx)
    pd.testing.assert_series_equal(
        rt.term_structure_scale(ratio.iloc[:40], minimum_observations=12),
        rt.term_structure_scale(ratio, minimum_observations=12).iloc[:40],
    )


def test_frozen_specification_round_trips_and_rehashes() -> None:
    spec = {"exposure_rule": {"type": "constant", "scale": 1.0}, "variance_notional": 1_000_000.0,
            "schedule": "monthly, first trading day"}
    payload = json.dumps(spec, indent=2, sort_keys=True)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    assert hashlib.sha256(json.dumps(json.loads(payload), indent=2, sort_keys=True).encode()).hexdigest() == digest
    tampered = {**spec, "variance_notional": 1_000_001.0}
    assert hashlib.sha256(json.dumps(tampered, indent=2, sort_keys=True).encode()).hexdigest() != digest
