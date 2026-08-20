from pathlib import Path

import pandas as pd
import pytest

from equity_options_research.data.zero_curve import PERCENT_TO_DECIMAL, load_zero_curve

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "wrds" / "zero_curve_sample.csv"


@pytest.fixture()
def curve():
    loaded, _ = load_zero_curve(FIXTURE)
    return loaded


def test_percent_rates_are_converted_to_decimals(curve) -> None:
    _, report = load_zero_curve(FIXTURE)
    assert report["source_units"] == "percent"
    assert report["converted_units"] == "decimal"
    assert report["percent_to_decimal_divisor"] == PERCENT_TO_DECIMAL
    assert curve.rate("2020-01-02", 7) == pytest.approx(0.015)
    assert report["decimal_rate_minimum"] == pytest.approx(0.010)
    assert report["decimal_rate_maximum"] == pytest.approx(0.030)


def test_exact_tenor_lookup_returns_the_quoted_rate(curve) -> None:
    assert curve.rate("2020-01-02", 30) == pytest.approx(0.020)
    assert curve.rate("2020-01-02", 60) == pytest.approx(0.025)
    assert curve.rate("2020-01-03", 40) == pytest.approx(0.030)


def test_between_tenor_interpolation_is_linear_in_days(curve) -> None:
    # midpoint of the 30d/60d segment
    assert curve.rate("2020-01-02", 45) == pytest.approx(0.0225)
    # one third along the 7d/30d segment
    expected = 0.015 + (0.020 - 0.015) * (7 + (30 - 7) / 3 - 7) / (30 - 7)
    assert curve.rate("2020-01-02", 7 + (30 - 7) / 3) == pytest.approx(expected)
    # linearity: the midpoint equals the average of the endpoints
    lower, upper = curve.rate("2020-01-03", 10), curve.rate("2020-01-03", 40)
    assert curve.rate("2020-01-03", 25) == pytest.approx((lower + upper) / 2)


def test_maturities_outside_the_grid_are_held_flat(curve) -> None:
    assert curve.rate("2020-01-02", 1) == pytest.approx(0.015)
    assert curve.rate("2020-01-02", 365) == pytest.approx(0.025)
    _, report = load_zero_curve(FIXTURE)
    assert report["boundary_policy"] == "flat_at_nearest_quoted_tenor"


def test_non_positive_maturity_is_rejected(curve) -> None:
    with pytest.raises(ValueError, match="days must be positive"):
        curve.rate("2020-01-02", 0)


def test_missing_date_raises_by_default(curve) -> None:
    with pytest.raises(KeyError):
        curve.rate("2020-01-06", 30)


def test_previous_date_is_used_only_when_explicitly_configured(curve) -> None:
    with pytest.raises(KeyError):
        curve.rate("2020-01-04", 30)
    # 2020-01-04 falls back to the 2020-01-03 curve, whose 30d point interpolates
    expected = 0.010 + (0.030 - 0.010) * (30 - 10) / (40 - 10)
    assert curve.rate("2020-01-04", 30, allow_previous_date=True) == pytest.approx(expected)


def test_lookup_never_falls_forward_to_a_later_date(curve) -> None:
    # 2020-01-01 precedes every quoted curve; the later 2020-01-02 curve must not be used
    with pytest.raises(KeyError):
        curve.rate("2020-01-01", 30, allow_previous_date=True)


def test_rate_series_is_vectorised_and_marks_unavailable_dates(curve) -> None:
    dates = pd.Series(["2020-01-02", "2020-01-02", "2020-01-06"])
    days = pd.Series([30.0, 45.0, 30.0])
    rates = curve.rate_series(dates, days)
    assert rates.iloc[0] == pytest.approx(0.020)
    assert rates.iloc[1] == pytest.approx(0.0225)
    assert pd.isna(rates.iloc[2])


def test_rate_series_matches_scalar_lookup(curve) -> None:
    dates = pd.Series(["2020-01-02"] * 3 + ["2020-01-03"] * 2)
    days = pd.Series([8.0, 30.0, 55.0, 12.0, 39.0])
    series = curve.rate_series(dates, days)
    for index, (date, day) in enumerate(zip(dates, days, strict=True)):
        assert series.iloc[index] == pytest.approx(curve.rate(date, day))


def test_loader_report_describes_the_grid() -> None:
    _, report = load_zero_curve(FIXTURE)
    assert report["unique_dates"] == 2
    assert report["rows_retained"] == 5
    assert report["compounding"] == "continuous"
    assert report["interpolation"] == "linear_in_days_between_two_nearest_tenors"
    assert report["minimum_tenor_days"] == 7
    assert report["maximum_tenor_days"] == 60
