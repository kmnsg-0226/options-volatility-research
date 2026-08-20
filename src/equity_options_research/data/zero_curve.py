"""OptionMetrics zero-curve loading and maturity interpolation.

The vendor publishes a continuously compounded zero curve per date, quoted in
percent, on an irregular grid of maturities measured in calendar days.  Black--
Scholes--Merton consumes a continuously compounded decimal rate, so the only
transformations applied here are a division by 100 and a linear interpolation
across maturity, which is the interpolation OptionMetrics itself documents.

Lookups never fall forward onto a later date.  A quote date absent from the
curve file raises unless the caller explicitly opts into using the most recent
earlier curve, so a missing date can never be filled with information that was
not available at the time.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

PERCENT_TO_DECIMAL = 100.0

ZERO_CURVE_SOURCE_COLUMNS = ["date", "days", "rate"]


@dataclass(frozen=True)
class ZeroCurve:
    """Date-indexed zero curves with linear interpolation across maturity."""

    tenors: dict[pd.Timestamp, np.ndarray]
    rates: dict[pd.Timestamp, np.ndarray]

    @property
    def dates(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(sorted(self.tenors)).sort_values()

    def _resolve_date(
        self,
        date: pd.Timestamp,
        allow_previous_date: bool,
    ) -> pd.Timestamp | None:
        stamp = pd.Timestamp(date).normalize()
        if stamp in self.tenors:
            return stamp
        if not allow_previous_date:
            return None
        available = self.dates
        position = available.searchsorted(stamp, side="right") - 1
        if position < 0:
            return None
        return available[position]

    def rate(
        self,
        date: pd.Timestamp | str,
        days: float,
        allow_previous_date: bool = False,
    ) -> float:
        """Return the continuously compounded decimal rate for a maturity.

        Maturities inside the quoted grid are linearly interpolated between the
        two nearest tenors; maturities outside it are held flat at the nearest
        quoted tenor rather than extrapolated.
        """

        if days <= 0:
            raise ValueError("days must be positive")
        resolved = self._resolve_date(pd.Timestamp(date), allow_previous_date)
        if resolved is None:
            raise KeyError(f"zero curve has no observation on or before {date}")
        return float(np.interp(float(days), self.tenors[resolved], self.rates[resolved]))

    def rate_series(
        self,
        dates: pd.Series,
        days: pd.Series,
        allow_previous_date: bool = False,
    ) -> pd.Series:
        """Vectorised lookup returning NaN where no usable curve date exists."""

        frame = pd.DataFrame(
            {
                "date": pd.to_datetime(pd.Series(dates).reset_index(drop=True)).dt.normalize(),
                "days": pd.to_numeric(pd.Series(days).reset_index(drop=True), errors="coerce"),
            }
        )
        result = pd.Series(np.nan, index=frame.index, name="risk_free_rate")
        for date, group in frame.groupby("date", sort=False):
            resolved = self._resolve_date(date, allow_previous_date)
            if resolved is None:
                continue
            valid = group["days"] > 0
            if not valid.any():
                continue
            result.loc[group.index[valid]] = np.interp(
                group.loc[valid, "days"].to_numpy(dtype=float),
                self.tenors[resolved],
                self.rates[resolved],
            )
        result.index = pd.Series(dates).index
        return result


def load_zero_curve(path: str | Path) -> tuple[ZeroCurve, dict[str, object]]:
    """Load the OptionMetrics zero curve and convert percent to decimal."""

    source = Path(path)
    raw = pd.read_csv(source, encoding="utf-8-sig")
    raw.columns = [str(column).strip().lower() for column in raw.columns]
    missing = set(ZERO_CURVE_SOURCE_COLUMNS) - set(raw.columns)
    if missing:
        raise ValueError(f"zero-curve file missing columns: {sorted(missing)}")

    raw_rows = len(raw)
    raw["date"] = pd.to_datetime(raw["date"], format="%Y-%m-%d", errors="coerce")
    raw["days"] = pd.to_numeric(raw["days"], errors="coerce")
    raw["rate"] = pd.to_numeric(raw["rate"], errors="coerce")

    invalid = raw["date"].isna() | raw["days"].isna() | raw["rate"].isna()
    invalid_rows = int(invalid.sum())
    raw = raw.loc[~invalid]

    non_positive_tenor_rows = int((raw["days"] <= 0).sum())
    raw = raw.loc[raw["days"] > 0]

    exact_duplicate_rows = int(raw.duplicated().sum())
    raw = raw.drop_duplicates()
    conflicting = int(raw.duplicated(["date", "days"], keep=False).sum())
    if conflicting:
        raise ValueError(
            "zero-curve file has conflicting rates for the same date and tenor"
        )

    raw["date"] = raw["date"].dt.normalize()
    raw["rate_decimal"] = raw["rate"] / PERCENT_TO_DECIMAL
    raw = raw.sort_values(["date", "days"])

    tenors: dict[pd.Timestamp, np.ndarray] = {}
    rates: dict[pd.Timestamp, np.ndarray] = {}
    for date, group in raw.groupby("date", sort=True):
        tenors[date] = group["days"].to_numpy(dtype=float)
        rates[date] = group["rate_decimal"].to_numpy(dtype=float)

    curve = ZeroCurve(tenors=tenors, rates=rates)
    shortest = {date: float(values.min()) for date, values in tenors.items()}
    longest = {date: float(values.max()) for date, values in tenors.items()}
    report: dict[str, object] = {
        "source": source.name,
        "file_size_bytes": source.stat().st_size,
        "raw_rows": raw_rows,
        "invalid_rows_removed": invalid_rows,
        "non_positive_tenor_rows_removed": non_positive_tenor_rows,
        "exact_duplicate_rows_removed": exact_duplicate_rows,
        "rows_retained": len(raw),
        "unique_dates": len(tenors),
        "first_date": str(min(tenors).date()) if tenors else None,
        "last_date": str(max(tenors).date()) if tenors else None,
        "compounding": "continuous",
        "source_units": "percent",
        "converted_units": "decimal",
        "percent_to_decimal_divisor": PERCENT_TO_DECIMAL,
        "interpolation": "linear_in_days_between_two_nearest_tenors",
        "boundary_policy": "flat_at_nearest_quoted_tenor",
        "minimum_tenor_days": min(shortest.values()) if shortest else None,
        "maximum_tenor_days": max(longest.values()) if longest else None,
        "worst_shortest_tenor_days": max(shortest.values()) if shortest else None,
        "decimal_rate_minimum": float(raw["rate_decimal"].min()) if len(raw) else None,
        "decimal_rate_maximum": float(raw["rate_decimal"].max()) if len(raw) else None,
    }
    return curve, report
