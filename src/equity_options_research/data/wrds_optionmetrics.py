"""Adapt WRDS OptionMetrics option prices to the project's internal wide schema.

OptionMetrics stores one contract per row and identifies the right through
``cp_flag``.  The research engine consumes a call/put-wide frame keyed by quote
date, expiration, and strike, so this adapter pivots the long format instead of
introducing a second internal representation.

Three vendor conventions are handled explicitly:

* ``strike_price`` is quoted in thousandths of a dollar and is divided by 1000.
* ``contract_size`` is not always 100; adjusted and non-standard deliverables
  are excluded rather than silently mixed into notional arithmetic.
* the file carries no underlying price, so spot is joined from the paired
  security-price series.

Days to expiration are recomputed locally from the parsed dates; no vendor DTE
column is trusted.  ``impl_volatility`` is preserved only as a diagnostic under
the ``vendor_*`` prefix and is never substituted for the project's own solver.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pandas as pd

WRDS_OPTION_SOURCE_COLUMNS = [
    "date",
    "exdate",
    "cp_flag",
    "strike_price",
    "best_bid",
    "best_offer",
    "volume",
    "open_interest",
    "impl_volatility",
    "contract_size",
    "optionid",
]

WRDS_NUMERIC_COLUMNS = [
    "strike_price",
    "best_bid",
    "best_offer",
    "volume",
    "open_interest",
    "impl_volatility",
    "optionid",
]

STRIKE_SCALING_DIVISOR = 1000.0
STANDARD_CONTRACT_SIZE = 100

_LEG_COLUMN_MAP = {
    "best_bid": "bid",
    "best_offer": "ask",
    "impl_volatility": "vendor_iv",
    "volume": "volume",
    "open_interest": "open_interest",
    "optionid": "optionid",
}

QUOTE_KEY = ["quote_date", "expiration", "strike"]


def load_wrds_option_chains(
    path: str | Path,
    spot_prices: pd.Series | None = None,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
    min_dte: int = 21,
    max_dte: int = 45,
    chunksize: int = 250_000,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Return a call/put-wide option frame plus an explicit data-quality report.

    The source file is streamed in compressed chunks; only rows surviving the
    contract-size, date, and DTE filters are retained in memory.
    """

    source = Path(path)
    if min_dte > max_dte:
        raise ValueError("min_dte must not exceed max_dte")
    start_date = pd.Timestamp(start).normalize() if start is not None else None
    end_date = pd.Timestamp(end).normalize() if end is not None else None

    parts: list[pd.DataFrame] = []
    rows_scanned = 0
    quote_date_parse_failures = expiration_parse_failures = 0
    rows_excluded_by_contract_size = 0
    rows_excluded_by_requested_dates = 0
    rows_excluded_by_dte = 0
    rows_excluded_by_contract_validation = 0
    contract_size_counts: Counter[str] = Counter()
    missing_bid = missing_ask = missing_vendor_iv = 0

    reader = pd.read_csv(
        source,
        encoding="utf-8-sig",
        skipinitialspace=True,
        usecols=WRDS_OPTION_SOURCE_COLUMNS,
        chunksize=chunksize,
        compression="infer",
        low_memory=False,
    )
    for chunk in reader:
        rows_scanned += len(chunk)
        chunk.columns = [str(column).strip().lower() for column in chunk.columns]

        contract_size = pd.to_numeric(chunk["contract_size"], errors="coerce")
        contract_size_counts.update(
            contract_size.astype("Int64").astype("string").fillna("missing").tolist()
        )
        standard = contract_size == STANDARD_CONTRACT_SIZE
        rows_excluded_by_contract_size += int((~standard).sum())
        chunk = chunk.loc[standard]
        if chunk.empty:
            continue

        chunk = chunk.copy()
        chunk["quote_date"] = pd.to_datetime(
            chunk["date"].astype("string").str.strip(),
            format="%Y-%m-%d",
            errors="coerce",
        )
        chunk["expiration"] = pd.to_datetime(
            chunk["exdate"].astype("string").str.strip(),
            format="%Y-%m-%d",
            errors="coerce",
        )
        quote_date_parse_failures += int(chunk["quote_date"].isna().sum())
        expiration_parse_failures += int(chunk["expiration"].isna().sum())

        for column in WRDS_NUMERIC_COLUMNS:
            chunk[column] = pd.to_numeric(chunk[column], errors="coerce")

        parse_valid = chunk["quote_date"].notna() & chunk["expiration"].notna()
        mask = parse_valid.copy()
        if start_date is not None:
            mask &= chunk["quote_date"] >= start_date
        if end_date is not None:
            mask &= chunk["quote_date"] <= end_date
        rows_excluded_by_requested_dates += int((parse_valid & ~mask).sum())
        chunk = chunk.loc[mask]
        if chunk.empty:
            continue

        chunk = chunk.copy()
        chunk["strike"] = chunk["strike_price"] / STRIKE_SCALING_DIVISOR
        chunk["dte"] = (chunk["expiration"] - chunk["quote_date"]).dt.days

        dte_valid = chunk["dte"].between(min_dte, max_dte)
        rows_excluded_by_dte += int((~dte_valid).sum())
        chunk = chunk.loc[dte_valid]
        if chunk.empty:
            continue

        chunk = chunk.copy()
        contract_valid = (
            (chunk["strike"] > 0)
            & chunk["cp_flag"].astype("string").str.strip().str.upper().isin({"C", "P"})
        )
        rows_excluded_by_contract_validation += int((~contract_valid).sum())
        chunk = chunk.loc[contract_valid]
        if chunk.empty:
            continue

        chunk = chunk.copy()
        chunk["cp_flag"] = chunk["cp_flag"].astype("string").str.strip().str.upper()
        missing_bid += int(chunk["best_bid"].isna().sum())
        missing_ask += int(chunk["best_offer"].isna().sum())
        missing_vendor_iv += int(chunk["impl_volatility"].isna().sum())
        parts.append(
            chunk[
                [
                    "quote_date",
                    "expiration",
                    "strike",
                    "dte",
                    "cp_flag",
                    *_LEG_COLUMN_MAP,
                ]
            ]
        )

    if not parts:
        raise ValueError(
            "WRDS option file has no rows in the requested date/DTE range"
        )

    long = pd.concat(parts, ignore_index=True)
    long["quote_date"] = long["quote_date"].dt.normalize()
    long["expiration"] = long["expiration"].dt.normalize()

    exact_duplicate_rows = int(long.duplicated().sum())
    long = long.drop_duplicates()
    leg_key = [*QUOTE_KEY, "cp_flag"]
    conflicting_key_rows = int(long.duplicated(leg_key, keep=False).sum())
    if conflicting_key_rows:
        raise ValueError(
            "WRDS option file has conflicting rows for a quote-date, expiration, "
            "strike, and right key; automatic deduplication would be unsafe"
        )

    dte_distribution = {
        int(dte): int(count)
        for dte, count in sorted(long["dte"].value_counts().items())
    }
    long_rows = len(long)

    paired, unmatched_call_legs, unmatched_put_legs = _pivot_legs(long)
    del long

    rows_missing_spot = 0
    if spot_prices is not None:
        spot = pd.Series(spot_prices).rename("spot")
        spot.index = pd.DatetimeIndex(spot.index).normalize()
        paired = paired.merge(
            spot, left_on="quote_date", right_index=True, how="left"
        )
        rows_missing_spot = int(paired["spot"].isna().sum())
        paired = paired.loc[paired["spot"].notna()]
    else:
        paired = paired.assign(spot=float("nan"))

    for column in (
        "call_volume",
        "put_volume",
        "call_open_interest",
        "put_open_interest",
        "call_optionid",
        "put_optionid",
    ):
        paired[column] = paired[column].astype("Int64")

    paired = (
        paired.sort_values(QUOTE_KEY)
        .reset_index(drop=True)
        .loc[
            :,
            [
                "quote_date",
                "expiration",
                "dte",
                "strike",
                "spot",
                "call_bid",
                "call_ask",
                "put_bid",
                "put_ask",
                "vendor_call_iv",
                "vendor_put_iv",
                "call_volume",
                "put_volume",
                "call_open_interest",
                "put_open_interest",
                "call_optionid",
                "put_optionid",
            ],
        ]
    )

    report: dict[str, object] = {
        "source": source.name,
        "file_size_bytes": source.stat().st_size,
        "rows_scanned": rows_scanned,
        "strike_scaling_divisor": STRIKE_SCALING_DIVISOR,
        "required_contract_size": STANDARD_CONTRACT_SIZE,
        "contract_size_distribution": dict(sorted(contract_size_counts.items())),
        "rows_excluded_by_contract_size": rows_excluded_by_contract_size,
        "rows_excluded_by_requested_dates": rows_excluded_by_requested_dates,
        "rows_excluded_by_dte": rows_excluded_by_dte,
        "rows_excluded_by_contract_validation": rows_excluded_by_contract_validation,
        "quote_date_parse_failures": quote_date_parse_failures,
        "expiration_parse_failures": expiration_parse_failures,
        "exact_duplicate_rows_removed": exact_duplicate_rows,
        "conflicting_leg_key_rows": conflicting_key_rows,
        "rows_after_filters_long": long_rows,
        "dte_range_enforced": [min_dte, max_dte],
        "dte_distribution": dte_distribution,
        "missing_best_bid": missing_bid,
        "missing_best_offer": missing_ask,
        "missing_vendor_implied_volatility": missing_vendor_iv,
        "unmatched_call_legs": unmatched_call_legs,
        "unmatched_put_legs": unmatched_put_legs,
        "paired_rows": len(paired),
        "rows_dropped_missing_spot": rows_missing_spot,
        "unique_quote_dates": int(paired["quote_date"].nunique()),
        "first_quote_date": (
            str(paired["quote_date"].min().date()) if len(paired) else None
        ),
        "last_quote_date": (
            str(paired["quote_date"].max().date()) if len(paired) else None
        ),
        "vendor_iv_role": "diagnostic_only_not_used_by_solver",
    }
    return paired, report


def _pivot_legs(long: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    """Pivot one-row-per-contract data into the call/put-wide schema.

    Legs are matched with an inner join so the paired frame never materialises
    half-populated rows; the unmatched counts are derived from the key sets so
    the report still records legs the vendor left without a counterparty.
    """

    legs: dict[str, pd.DataFrame] = {}
    for flag, prefix in (("C", "call"), ("P", "put")):
        side = long.loc[long["cp_flag"] == flag].drop(columns=["cp_flag", "dte"])
        renames = {
            source: (
                f"vendor_{prefix}_iv"
                if target == "vendor_iv"
                else f"{prefix}_{target}"
            )
            for source, target in _LEG_COLUMN_MAP.items()
        }
        legs[prefix] = side.rename(columns=renames)

    call_keys = pd.MultiIndex.from_frame(legs["call"][QUOTE_KEY])
    put_keys = pd.MultiIndex.from_frame(legs["put"][QUOTE_KEY])
    unmatched_call_legs = len(call_keys.difference(put_keys))
    unmatched_put_legs = len(put_keys.difference(call_keys))

    paired = legs["call"].merge(legs["put"], on=QUOTE_KEY, how="inner")
    paired["dte"] = (paired["expiration"] - paired["quote_date"]).dt.days
    return paired, unmatched_call_legs, unmatched_put_legs
