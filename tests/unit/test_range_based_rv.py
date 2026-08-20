from math import log

import numpy as np
import pandas as pd
import pytest

from equity_options_research.volatility.range_based import (
    GARMAN_KLASS_CLOSE_COEFFICIENT,
    TRADING_DAYS,
    close_to_close_variance,
    compare_realised_variance,
    daily_range_realised_variance,
    garman_klass_variance,
    ohlc_is_consistent,
    overnight_variance,
)


def make_prices(days: int = 40, seed: int = 42) -> pd.DataFrame:
    """Deterministic OHLC bars with a valid high/low envelope."""

    rng = np.random.default_rng(seed)
    index = pd.bdate_range("2020-01-01", periods=days)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, days)))
    open_ = close * (1 + rng.normal(0, 0.002, days))
    high = np.maximum(open_, close) * (1 + np.abs(rng.normal(0, 0.004, days)))
    low = np.minimum(open_, close) * (1 - np.abs(rng.normal(0, 0.004, days)))
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close}, index=index
    )


def test_garman_klass_matches_the_longhand_formula() -> None:
    frame = pd.DataFrame(
        {"open": [100.0], "high": [110.0], "low": [90.0], "close": [105.0]},
        index=pd.DatetimeIndex(["2020-01-02"]),
    )
    expected = 0.5 * log(110 / 90) ** 2 - (2 * log(2) - 1) * log(105 / 100) ** 2
    value = garman_klass_variance(
        frame["open"], frame["high"], frame["low"], frame["close"]
    ).iloc[0]
    assert value == pytest.approx(expected)
    assert value == pytest.approx(0.019214798, abs=1e-9)
    assert GARMAN_KLASS_CLOSE_COEFFICIENT == pytest.approx(2 * log(2) - 1)


def test_garman_klass_is_zero_for_a_flat_bar() -> None:
    frame = pd.DataFrame(
        {"open": [100.0], "high": [100.0], "low": [100.0], "close": [100.0]},
        index=pd.DatetimeIndex(["2020-01-02"]),
    )
    value = garman_klass_variance(
        frame["open"], frame["high"], frame["low"], frame["close"]
    ).iloc[0]
    assert value == pytest.approx(0.0)


def test_overnight_variance_uses_the_previous_close() -> None:
    close = pd.Series([100.0, 101.0, 102.0])
    open_ = pd.Series([100.0, 102.0, 103.0])
    result = overnight_variance(open_, close)
    assert pd.isna(result.iloc[0])
    assert result.iloc[1] == pytest.approx(log(102 / 100) ** 2)
    assert result.iloc[2] == pytest.approx(log(103 / 101) ** 2)


def test_close_to_close_variance_is_the_squared_log_return() -> None:
    close = pd.Series([100.0, 105.0, 99.0])
    result = close_to_close_variance(close)
    assert pd.isna(result.iloc[0])
    assert result.iloc[1] == pytest.approx(log(105 / 100) ** 2)
    assert result.iloc[2] == pytest.approx(log(99 / 105) ** 2)


def test_components_sum_to_total_and_are_kept_separate() -> None:
    frame = daily_range_realised_variance(make_prices())
    assert {"rv_intraday", "overnight_variance", "close_to_close_variance"} <= set(
        frame.columns
    )
    reconstructed = frame["rv_intraday"] + frame["overnight_variance"]
    pd.testing.assert_series_equal(
        frame["rv_total"], reconstructed, check_names=False
    )
    # the close-to-close component is reported but is not part of rv_total
    assert not frame["close_to_close_variance"].equals(frame["rv_total"])


def test_annualisation_scales_daily_variance_by_trading_days() -> None:
    frame = daily_range_realised_variance(make_prices())
    pd.testing.assert_series_equal(
        frame["rv_annualised"],
        TRADING_DAYS * frame["rv_total"],
        check_names=False,
    )
    valid = frame["rv_annualised"].dropna()
    assert np.allclose(
        frame["realised_volatility"].dropna().to_numpy(),
        np.sqrt(valid.clip(lower=0).to_numpy()),
    )


def test_excluding_overnight_leaves_only_the_range_component() -> None:
    prices = make_prices()
    frame = daily_range_realised_variance(prices, include_overnight=False)
    assert (frame["overnight_variance"] == 0).all()
    pd.testing.assert_series_equal(
        frame["rv_total"], frame["rv_intraday"], check_names=False
    )


def test_weekly_and_monthly_features_are_trailing_means() -> None:
    frame = daily_range_realised_variance(make_prices())
    annualised = frame["rv_annualised"]
    assert frame["rv_weekly"].iloc[:4].isna().all()
    assert frame["rv_monthly"].iloc[:21].isna().all()
    assert frame["rv_weekly"].iloc[6] == pytest.approx(annualised.iloc[2:7].mean())
    assert frame["rv_monthly"].iloc[25] == pytest.approx(annualised.iloc[4:26].mean())


def test_rolling_features_contain_no_future_information() -> None:
    prices = make_prices()
    baseline = daily_range_realised_variance(prices)

    perturbed_prices = prices.copy()
    perturbed_prices.iloc[30] *= 1.5
    perturbed = daily_range_realised_variance(perturbed_prices)

    # every feature strictly before the perturbed session must be untouched
    for column in ("rv_total", "rv_annualised", "rv_weekly", "rv_monthly"):
        pd.testing.assert_series_equal(
            baseline[column].iloc[:30], perturbed[column].iloc[:30]
        )
    assert not np.allclose(
        baseline["rv_weekly"].iloc[30:34].to_numpy(),
        perturbed["rv_weekly"].iloc[30:34].to_numpy(),
        equal_nan=True,
    )


def test_inconsistent_ohlc_is_flagged_and_excluded_not_repaired() -> None:
    prices = make_prices()
    broken = prices.index[10]
    prices.loc[broken, "high"] = prices.loc[broken, "low"] - 1.0

    consistent = ohlc_is_consistent(prices)
    assert not consistent.loc[broken]
    assert consistent.drop(broken).all()

    frame = daily_range_realised_variance(prices)
    assert not frame.loc[broken, "ohlc_consistent"]
    assert pd.isna(frame.loc[broken, "rv_intraday"])
    assert pd.isna(frame.loc[broken, "rv_total"])
    # the close-only component does not depend on the broken range and survives
    assert not pd.isna(frame.loc[broken, "close_to_close_variance"])
    # the exclusion propagates into the trailing features rather than being patched
    assert frame["rv_weekly"].loc[broken:].iloc[:5].isna().all()


def test_supplied_consistency_flag_is_respected() -> None:
    prices = make_prices()
    prices["ohlc_consistent"] = True
    prices.loc[prices.index[5], "ohlc_consistent"] = False
    frame = daily_range_realised_variance(prices)
    assert pd.isna(frame["rv_intraday"].iloc[5])
    assert frame["rv_intraday"].iloc[4] == pytest.approx(
        garman_klass_variance(
            prices["open"], prices["high"], prices["low"], prices["close"]
        ).iloc[4]
    )


def test_duplicate_or_unsorted_index_is_rejected() -> None:
    prices = make_prices(days=5)
    duplicated = pd.concat([prices, prices.iloc[[0]]]).sort_index()
    with pytest.raises(ValueError, match="unique"):
        daily_range_realised_variance(duplicated)


def test_comparison_scores_a_candidate_against_a_reference() -> None:
    reference = pd.Series(
        [0.0001, 0.0002, 0.00015, 0.0003, 0.00025] * 10,
        index=pd.bdate_range("2020-01-01", periods=50),
    )
    result = compare_realised_variance(reference, reference * 1.1)
    assert result["overlapping_sessions"] == 50
    assert result["daily_correlation"] == pytest.approx(1.0)
    assert result["median_ratio"] == pytest.approx(1.1)
    assert result["log_space_correlation"] == pytest.approx(1.0)
    assert result["aggregated_correlation"] == pytest.approx(1.0)
    assert result["mean_bias"] == pytest.approx((reference * 0.1).mean())
