"""Range-based daily realised variance from open/high/low/close bars.

Intraday five-minute realised variance is only available where minute history
exists.  These estimators reconstruct a comparable daily series from the daily
OHLC record alone, which is what the WRDS OptionMetrics security-price file
provides for the full option sample.

Each variance component is computed independently so callers can inspect them
separately:

``close_to_close_variance``
    squared close-to-close log return; the noisiest estimator and the only one
    that needs no intraday information.
``garman_klass_variance``
    open-to-close variance using the high/low range, roughly five times more
    efficient than close-to-close.
``overnight_variance``
    squared log return from the previous close to the current open, which the
    range estimators cannot observe.

Bars whose high/low envelope does not contain the open and close are excluded
from the range estimator rather than repaired; the offending sessions are
reported through ``ohlc_consistent`` so the exclusion stays visible.
"""

from __future__ import annotations

from math import log

import numpy as np
import pandas as pd

TRADING_DAYS = 252
GARMAN_KLASS_CLOSE_COEFFICIENT = 2.0 * log(2.0) - 1.0

OHLC_COLUMNS = ["open", "high", "low", "close"]


def ohlc_is_consistent(prices: pd.DataFrame) -> pd.Series:
    """Flag bars whose high/low envelope contains the open and close."""

    positive = (prices[OHLC_COLUMNS] > 0).all(axis=1)
    return (
        positive
        & (prices["high"] >= prices[["open", "close", "low"]].max(axis=1))
        & (prices["low"] <= prices[["open", "close", "high"]].min(axis=1))
    ).rename("ohlc_consistent")


def close_to_close_variance(close: pd.Series) -> pd.Series:
    """Squared close-to-close log return, unannualised."""

    close = close.astype(float)
    return np.log(close / close.shift(1)).pow(2).rename("close_to_close_variance")


def garman_klass_variance(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
) -> pd.Series:
    """Garman--Klass open-to-close variance, unannualised.

    ``0.5 * ln(H/L)^2 - (2 ln 2 - 1) * ln(C/O)^2``
    """

    open_, high, low, close = (series.astype(float) for series in (open_, high, low, close))
    range_term = 0.5 * np.log(high / low) ** 2
    drift_term = GARMAN_KLASS_CLOSE_COEFFICIENT * np.log(close / open_) ** 2
    return (range_term - drift_term).rename("garman_klass_variance")


def overnight_variance(open_: pd.Series, close: pd.Series) -> pd.Series:
    """Squared log return from the previous close to the current open."""

    open_, close = open_.astype(float), close.astype(float)
    return np.log(open_ / close.shift(1)).pow(2).rename("overnight_variance")


def daily_range_realised_variance(
    prices: pd.DataFrame,
    include_overnight: bool = True,
    annualization: int = TRADING_DAYS,
) -> pd.DataFrame:
    """Return the HAR-ready realised-variance frame built from daily OHLC.

    The output mirrors :func:`daily_realised_variance` so the existing HAR
    pipeline consumes it unchanged: ``rv_total`` is a daily unannualised
    variance, ``rv_annualised`` scales it by the trading-day count, and the
    weekly/monthly features are trailing means of the annualised series.
    """

    if not isinstance(prices.index, pd.DatetimeIndex):
        raise ValueError("prices must have a DatetimeIndex")
    missing = set(OHLC_COLUMNS) - set(prices.columns)
    if missing:
        raise ValueError(f"price frame missing columns: {sorted(missing)}")
    frame = prices.sort_index()
    if frame.index.has_duplicates:
        raise ValueError("price index must be unique")

    consistent = (
        frame["ohlc_consistent"].astype(bool)
        if "ohlc_consistent" in frame.columns
        else ohlc_is_consistent(frame)
    )

    intraday = garman_klass_variance(
        frame["open"], frame["high"], frame["low"], frame["close"]
    ).where(consistent)
    overnight = (
        overnight_variance(frame["open"], frame["close"])
        if include_overnight
        else pd.Series(0.0, index=frame.index, name="overnight_variance")
    )
    close_to_close = close_to_close_variance(frame["close"])

    total = intraday + overnight if include_overnight else intraday
    result = pd.DataFrame(
        {
            "rv_intraday": intraday,
            "overnight_variance": overnight,
            "close_to_close_variance": close_to_close,
            "rv_total": total,
            "ohlc_consistent": consistent,
        }
    )
    result.index = pd.to_datetime(result.index)
    result.index.name = "date"
    result["rv_annualised"] = annualization * result["rv_total"]
    result["realised_volatility"] = np.sqrt(result["rv_annualised"].clip(lower=0))
    result["rv_weekly"] = result["rv_annualised"].rolling(5, min_periods=5).mean()
    result["rv_monthly"] = result["rv_annualised"].rolling(22, min_periods=22).mean()
    return result


def compare_realised_variance(
    reference: pd.Series,
    candidate: pd.Series,
    aggregation_window: int = 22,
) -> dict[str, object]:
    """Score a candidate realised-variance series against a reference series.

    The comparison is deliberately confined to estimation quality: correlation,
    bias and error.  No trading outcome enters the calculation.
    """

    pair = (
        pd.concat(
            [reference.rename("reference"), candidate.rename("candidate")], axis=1
        )
        .replace([np.inf, -np.inf], np.nan)
        .dropna()
    )
    if pair.empty:
        raise ValueError("no overlapping observations to compare")

    error = pair["candidate"] - pair["reference"]
    positive = pair.loc[(pair > 0).all(axis=1)]
    logged = np.log(positive)
    ratio = (positive["candidate"] / positive["reference"]).replace(
        [np.inf, -np.inf], np.nan
    ).dropna()
    aggregated = pair.rolling(aggregation_window, min_periods=aggregation_window).mean().dropna()

    return {
        "overlapping_sessions": int(len(pair)),
        "first_session": str(pair.index.min().date()),
        "last_session": str(pair.index.max().date()),
        "daily_correlation": float(pair["reference"].corr(pair["candidate"])),
        "daily_rank_correlation": float(
            pair["reference"].corr(pair["candidate"], method="spearman")
        ),
        "log_space_correlation": float(logged["reference"].corr(logged["candidate"])),
        "log_space_sessions": int(len(logged)),
        "mean_bias": float(error.mean()),
        "median_ratio": float(ratio.median()),
        "mean_ratio": float(ratio.mean()),
        "rmse": float(np.sqrt((error**2).mean())),
        "reference_mean": float(pair["reference"].mean()),
        "candidate_mean": float(pair["candidate"].mean()),
        "aggregation_window": aggregation_window,
        "aggregated_sessions": int(len(aggregated)),
        "aggregated_correlation": float(
            aggregated["reference"].corr(aggregated["candidate"])
        ),
        "aggregated_mean_bias": float(
            (aggregated["candidate"] - aggregated["reference"]).mean()
        ),
        "aggregated_median_ratio": float(
            (aggregated["candidate"] / aggregated["reference"]).median()
        ),
    }
