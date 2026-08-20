"""Assemble and run the backtest from WRDS OptionMetrics inputs.

This path reuses the existing engine unchanged.  Its only job is to build the
two frames the engine already consumes -- a call/put-wide option chain and a
HAR-ready realised-variance frame -- from the WRDS files, and to attach a
per-row risk-free rate interpolated from the OptionMetrics zero curve.

Realised variance comes from daily Garman--Klass estimates because intraday
minute history does not cover the option sample.  The strategy specification is
untouched: the default configuration is the research specification, and this
module never overrides a threshold.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from equity_options_research.backtest.ingestion_config import IngestionConfig
from equity_options_research.data.wrds_optionmetrics import load_wrds_option_chains
from equity_options_research.data.wrds_security_prices import (
    load_wrds_security_prices,
    spot_series,
)
from equity_options_research.data.zero_curve import load_zero_curve
from equity_options_research.volatility.range_based import daily_range_realised_variance


@dataclass(frozen=True)
class WrdsBacktestInputs:
    """Engine-ready frames plus the data-quality reports that produced them."""

    options: pd.DataFrame
    realised: pd.DataFrame
    prices: pd.DataFrame
    reports: dict[str, object] = field(default_factory=dict)


def prepare_wrds_inputs(
    option_path: str | Path,
    security_price_path: str | Path,
    zero_curve_path: str | Path | None = None,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
    config: IngestionConfig | None = None,
    allow_previous_curve_date: bool = False,
    load_min_dte: int = 0,
    load_max_dte: int = 60,
) -> WrdsBacktestInputs:
    """Build the option and realised-variance frames the engine expects.

    The chain is loaded over a wider maturity band than the strategy trades.
    Entry selection is restricted to ``config.min_dte``--``config.max_dte`` by
    the engine itself; the extra maturities exist so an open position stays
    markable and closable as its own expiration approaches, which a load-time
    21--45 filter would silently prevent.
    """

    cfg = config or IngestionConfig()
    prices, price_report = load_wrds_security_prices(security_price_path)
    realised = daily_range_realised_variance(prices)

    options, option_report = load_wrds_option_chains(
        option_path,
        spot_prices=spot_series(prices),
        start=start,
        end=end,
        min_dte=load_min_dte,
        max_dte=max(load_max_dte, int(cfg.max_dte)),
    )

    reports: dict[str, object] = {
        "security_prices": price_report,
        "option_chains": option_report,
        "maturity_bands": {
            "loaded_dte_minimum": load_min_dte,
            "loaded_dte_maximum": max(load_max_dte, int(cfg.max_dte)),
            "selection_dte_minimum": cfg.min_dte,
            "selection_dte_maximum": cfg.max_dte,
            "exit_dte": cfg.exit_dte,
            "observed_dte_minimum": int(options["dte"].min()),
            "observed_dte_maximum": int(options["dte"].max()),
        },
        "realised_variance": {
            "estimator": "garman_klass_plus_overnight",
            "sessions": int(len(realised)),
            "sessions_with_valid_rv_total": int(realised["rv_total"].notna().sum()),
            "sessions_excluded_for_inconsistent_ohlc": int(
                (~realised["ohlc_consistent"]).sum()
            ),
            "sessions_with_valid_monthly_feature": int(
                realised["rv_monthly"].notna().sum()
            ),
            "first_session": str(realised.index.min().date()),
            "last_session": str(realised.index.max().date()),
        },
    }

    if zero_curve_path is not None:
        curve, curve_report = load_zero_curve(zero_curve_path)
        rates = curve.rate_series(
            options["quote_date"],
            options["dte"],
            allow_previous_date=allow_previous_curve_date,
        )
        options = options.assign(risk_free_rate=rates.to_numpy())
        unresolved = int(options["risk_free_rate"].isna().sum())
        curve_report = dict(curve_report)
        curve_report.update(
            {
                "option_rows_priced_from_curve": int(len(options) - unresolved),
                "option_rows_falling_back_to_scalar": unresolved,
                "scalar_fallback_rate": cfg.risk_free_rate,
                "allow_previous_curve_date": allow_previous_curve_date,
                "interpolated_rate_minimum": (
                    float(options["risk_free_rate"].min())
                    if unresolved < len(options)
                    else None
                ),
                "interpolated_rate_maximum": (
                    float(options["risk_free_rate"].max())
                    if unresolved < len(options)
                    else None
                ),
            }
        )
        reports["zero_curve"] = curve_report
    else:
        reports["zero_curve"] = {
            "status": "not_supplied",
            "scalar_fallback_rate": cfg.risk_free_rate,
        }

    return WrdsBacktestInputs(
        options=options, realised=realised, prices=prices, reports=reports
    )
