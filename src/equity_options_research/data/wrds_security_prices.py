"""Load WRDS OptionMetrics daily security prices for SPY.

The security-price file supplies the underlying spot series that the WRDS
option file omits, and the daily OHLC needed by range-based realised-variance
estimators.  Rows whose OHLC bounds are internally inconsistent are flagged
rather than dropped, because ``close`` remains usable as spot even when the
high/low envelope is suspect.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

SECURITY_SOURCE_COLUMNS = [
    "secid",
    "date",
    "ticker",
    "low",
    "high",
    "open",
    "close",
    "volume",
    "return",
    "cfadj",
]

SECURITY_PRICE_COLUMNS = ["open", "high", "low", "close"]


def load_wrds_security_prices(
    path: str | Path,
    ticker: str | None = "SPY",
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Return a date-indexed OHLC frame plus an explicit data-quality report."""

    source = Path(path)
    raw = pd.read_csv(source, encoding="utf-8-sig")
    raw.columns = [str(column).strip().lower() for column in raw.columns]
    required = {"date", *SECURITY_PRICE_COLUMNS}
    missing = required - set(raw.columns)
    if missing:
        raise ValueError(f"WRDS security-price file missing columns: {sorted(missing)}")

    raw_rows = len(raw)
    raw["date"] = pd.to_datetime(raw["date"], format="%Y-%m-%d", errors="coerce")
    invalid_timestamp_rows = int(raw["date"].isna().sum())
    raw = raw.dropna(subset=["date"])

    ticker_rows_removed = 0
    if ticker is not None and "ticker" in raw.columns:
        matches = raw["ticker"].astype("string").str.strip() == ticker
        ticker_rows_removed = int((~matches).sum())
        raw = raw.loc[matches]

    for column in [*SECURITY_PRICE_COLUMNS, "volume", "return", "cfadj"]:
        if column in raw.columns:
            raw[column] = pd.to_numeric(raw[column], errors="coerce")

    exact_duplicate_rows = int(raw.duplicated().sum())
    raw = raw.drop_duplicates()
    conflicting_dates = int(raw["date"].duplicated(keep=False).sum())
    if conflicting_dates:
        raise ValueError(
            "WRDS security-price file has conflicting rows for the same date; "
            "automatic deduplication would be unsafe"
        )

    positive_close = raw["close"] > 0
    rows_without_usable_close = int((~positive_close).sum())
    raw = raw.loc[positive_close]

    frame = raw.set_index(raw["date"].dt.normalize()).drop(columns="date").sort_index()
    frame.index.name = "date"

    consistent = (
        (frame[SECURITY_PRICE_COLUMNS] > 0).all(axis=1)
        & (frame["high"] >= frame[["open", "close", "low"]].max(axis=1))
        & (frame["low"] <= frame[["open", "close", "high"]].min(axis=1))
    )
    frame["ohlc_consistent"] = consistent

    report: dict[str, object] = {
        "source": str(source),
        "file_size_bytes": source.stat().st_size,
        "raw_rows": raw_rows,
        "invalid_timestamp_rows": invalid_timestamp_rows,
        "ticker_rows_removed": ticker_rows_removed,
        "exact_duplicate_rows_removed": exact_duplicate_rows,
        "rows_without_usable_close_removed": rows_without_usable_close,
        "rows_retained": len(frame),
        "ohlc_inconsistent_rows_flagged": int((~consistent).sum()),
        "unique_dates": int(frame.index.nunique()),
        "first_date": str(frame.index.min().date()) if len(frame) else None,
        "last_date": str(frame.index.max().date()) if len(frame) else None,
    }
    return frame, report


def spot_series(prices: pd.DataFrame) -> pd.Series:
    """Return the closing price series used as the option-chain spot."""

    return prices["close"].rename("spot")
