from pathlib import Path

from equity_options_research.backtest.ingestion_config import IngestionConfig
from equity_options_research.backtest.wrds_eod import prepare_wrds_inputs

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "wrds"
OPTIONS = FIXTURES / "option_prices_sample.csv"
SECURITIES = FIXTURES / "security_prices_sample.csv"
ZERO_CURVE = FIXTURES / "zero_curve_sample.csv"


def build(**kwargs):
    return prepare_wrds_inputs(OPTIONS, SECURITIES, **kwargs)


def test_chain_is_loaded_wider_than_the_selection_band() -> None:
    """A held position must stay markable after its DTE falls below min_dte.

    Filtering the chain to the 21--45 selection band at load time strands open
    positions, so the loaded band is deliberately wider than the traded band.
    """

    cfg = IngestionConfig()
    inputs = build(config=cfg)
    bands = inputs.reports["maturity_bands"]

    assert bands["loaded_dte_minimum"] < bands["selection_dte_minimum"]
    assert bands["loaded_dte_minimum"] <= bands["exit_dte"]
    assert bands["selection_dte_minimum"] == cfg.min_dte
    assert bands["selection_dte_maximum"] == cfg.max_dte

    # the fixture's 8-DTE pair sits below the selection band but must be loaded
    assert (inputs.options["dte"] < cfg.min_dte).any()
    assert 324.0 in set(inputs.options["strike"])


def test_selection_band_is_left_to_the_engine() -> None:
    cfg = IngestionConfig()
    inputs = build(config=cfg)
    # loading must not pre-apply the strategy's entry window
    assert inputs.options["dte"].min() < cfg.min_dte


def test_realised_frame_exposes_the_har_contract() -> None:
    inputs = build()
    assert {"rv_total", "rv_annualised", "rv_weekly", "rv_monthly"} <= set(
        inputs.realised.columns
    )
    assert inputs.reports["realised_variance"]["estimator"] == (
        "garman_klass_plus_overnight"
    )


def test_zero_curve_rates_are_attached_per_row() -> None:
    inputs = build(zero_curve_path=ZERO_CURVE)
    assert "risk_free_rate" in inputs.options.columns
    report = inputs.reports["zero_curve"]
    assert report["option_rows_falling_back_to_scalar"] == 0
    assert report["option_rows_priced_from_curve"] == len(inputs.options)
    # 2020-01-02 curve: 30d=2.0%, 60d=2.5% -> a 35-DTE contract interpolates
    row = inputs.options.loc[
        (inputs.options["quote_date"] == "2020-01-02") & (inputs.options["dte"] == 35)
    ].iloc[0]
    assert abs(row["risk_free_rate"] - (0.020 + (0.025 - 0.020) * 5 / 30)) < 1e-12


def test_missing_zero_curve_leaves_the_scalar_fallback() -> None:
    cfg = IngestionConfig()
    inputs = build(config=cfg)
    assert "risk_free_rate" not in inputs.options.columns
    assert inputs.reports["zero_curve"]["status"] == "not_supplied"
    assert inputs.reports["zero_curve"]["scalar_fallback_rate"] == cfg.risk_free_rate
