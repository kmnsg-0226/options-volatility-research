import gzip
from pathlib import Path

import pandas as pd
import pytest

from equity_options_research.data.wrds_optionmetrics import (
    STANDARD_CONTRACT_SIZE,
    STRIKE_SCALING_DIVISOR,
    load_wrds_option_chains,
)
from equity_options_research.data.wrds_security_prices import (
    load_wrds_security_prices,
    spot_series,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "wrds"
OPTIONS = FIXTURES / "option_prices_sample.csv"
CONFLICTING = FIXTURES / "option_prices_conflicting.csv"
SECURITIES = FIXTURES / "security_prices_sample.csv"

ENGINE_REQUIRED_COLUMNS = {
    "quote_date",
    "expiration",
    "dte",
    "spot",
    "strike",
    "call_bid",
    "call_ask",
    "put_bid",
    "put_ask",
}


def load(**kwargs):
    return load_wrds_option_chains(OPTIONS, **kwargs)


def test_strike_price_is_scaled_by_one_thousand() -> None:
    frame, report = load()
    assert report["strike_scaling_divisor"] == STRIKE_SCALING_DIVISOR
    assert sorted(frame["strike"].unique()) == [320.0, 326.0, 327.0, 330.0]


def test_dte_is_recomputed_locally_and_window_is_enforced() -> None:
    frame, report = load()
    expected = (frame["expiration"] - frame["quote_date"]).dt.days
    pd.testing.assert_series_equal(
        frame["dte"].astype("int64"), expected.astype("int64"), check_names=False
    )
    assert frame["dte"].between(21, 45).all()
    assert report["dte_range_enforced"] == [21, 45]
    assert report["rows_excluded_by_dte"] == 4
    assert report["dte_distribution"] == {34: 2, 35: 8}


def test_narrower_dte_window_is_respected() -> None:
    frame, _ = load(min_dte=35, max_dte=45)
    assert set(frame["dte"].unique()) == {35}


def test_call_and_put_legs_are_paired_on_date_expiry_strike() -> None:
    frame, report = load()
    assert len(frame) == 4
    assert report["paired_rows"] == 4
    assert report["unmatched_call_legs"] == 1
    assert report["unmatched_put_legs"] == 1
    assert 321.0 not in set(frame["strike"])
    assert 322.0 not in set(frame["strike"])
    pair = frame.loc[frame["strike"] == 320.0].iloc[0]
    assert pair["call_bid"] == 5.0
    assert pair["call_ask"] == 5.2
    assert pair["put_bid"] == 4.0
    assert pair["put_ask"] == 4.2


def test_exact_duplicate_rows_are_removed() -> None:
    _, report = load()
    assert report["exact_duplicate_rows_removed"] == 1
    assert report["conflicting_leg_key_rows"] == 0


def test_conflicting_duplicate_legs_raise() -> None:
    with pytest.raises(ValueError, match="conflicting rows"):
        load_wrds_option_chains(CONFLICTING)


def test_non_standard_contract_sizes_are_filtered() -> None:
    frame, report = load()
    assert report["required_contract_size"] == STANDARD_CONTRACT_SIZE
    assert report["contract_size_distribution"] == {"10": 2, "100": 15}
    assert report["rows_excluded_by_contract_size"] == 2
    assert 323.0 not in set(frame["strike"])


def test_missing_quotes_are_preserved_as_nan_and_counted() -> None:
    frame, report = load()
    assert report["missing_best_bid"] == 1
    assert report["missing_best_offer"] == 1
    incomplete = frame.loc[frame["strike"] == 326.0].iloc[0]
    assert pd.isna(incomplete["call_bid"])
    assert pd.isna(incomplete["call_ask"])
    assert incomplete["put_bid"] == 6.0


def test_vendor_implied_volatility_is_preserved_as_diagnostic_only() -> None:
    frame, report = load()
    assert report["missing_vendor_implied_volatility"] == 2
    assert report["vendor_iv_role"] == "diagnostic_only_not_used_by_solver"
    assert {"vendor_call_iv", "vendor_put_iv"} <= set(frame.columns)
    assert frame.loc[frame["strike"] == 320.0, "vendor_call_iv"].iloc[0] == 0.18
    assert pd.isna(frame.loc[frame["strike"] == 327.0, "vendor_call_iv"].iloc[0])


def test_pairing_survives_chunk_boundaries() -> None:
    single, _ = load(chunksize=1)
    batched, _ = load(chunksize=1_000)
    pd.testing.assert_frame_equal(single, batched)


def test_gzip_source_is_streamed_identically(tmp_path) -> None:
    archive = tmp_path / "option_prices_sample.csv.gz"
    archive.write_bytes(gzip.compress(OPTIONS.read_bytes()))
    plain, _ = load()
    compressed, report = load_wrds_option_chains(archive)
    pd.testing.assert_frame_equal(plain, compressed)
    assert report["source"].endswith(".gz")


def test_date_range_filter_limits_quote_dates() -> None:
    frame, report = load(start="2020-01-03")
    assert set(frame["quote_date"]) == {pd.Timestamp("2020-01-03")}
    assert report["rows_excluded_by_requested_dates"] == 13


def test_spot_is_joined_from_security_prices() -> None:
    prices, _ = load_wrds_security_prices(SECURITIES)
    frame, report = load(spot_prices=spot_series(prices))
    assert report["rows_dropped_missing_spot"] == 0
    assert frame.loc[frame["quote_date"] == "2020-01-02", "spot"].eq(323.0).all()
    assert frame.loc[frame["quote_date"] == "2020-01-03", "spot"].eq(324.0).all()


def test_rows_without_spot_are_dropped_and_reported() -> None:
    partial = pd.Series({pd.Timestamp("2020-01-02"): 323.0})
    frame, report = load(spot_prices=partial)
    assert report["rows_dropped_missing_spot"] == 1
    assert set(frame["quote_date"]) == {pd.Timestamp("2020-01-02")}


def test_report_counts_rows_and_dates() -> None:
    _, report = load()
    assert report["rows_scanned"] == 17
    assert report["rows_after_filters_long"] == 10
    assert report["unique_quote_dates"] == 2
    assert report["first_quote_date"] == "2020-01-02"
    assert report["last_quote_date"] == "2020-01-03"


def test_security_prices_flag_inconsistent_ohlc_without_dropping_spot() -> None:
    frame, report = load_wrds_security_prices(SECURITIES)
    assert len(frame) == 3
    assert report["ohlc_inconsistent_rows_flagged"] == 1
    assert not frame.loc[pd.Timestamp("2020-01-06"), "ohlc_consistent"]
    assert frame.loc[pd.Timestamp("2020-01-06"), "close"] == 320.0
    assert report["unique_dates"] == 3
    assert spot_series(frame).name == "spot"


def test_paired_legs_have_symmetric_dtypes() -> None:
    prices, _ = load_wrds_security_prices(SECURITIES)
    frame, _ = load(spot_prices=spot_series(prices))
    for suffix in ("volume", "open_interest", "optionid"):
        assert frame[f"call_{suffix}"].dtype == frame[f"put_{suffix}"].dtype
        assert str(frame[f"call_{suffix}"].dtype) == "Int64"
    for suffix in ("bid", "ask"):
        assert frame[f"call_{suffix}"].dtype == frame[f"put_{suffix}"].dtype
    assert frame["dte"].dtype == "int64"
