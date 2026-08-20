# Technical reference

Conventions and reproduction notes for the current research stack. The narrative
and headline results are in the top-level [README](../README.md).

## Black-Scholes and model-free variance: two tools, two jobs

This project uses both, and they are not interchangeable. Confusing them is the
single most expensive mistake available here, and an earlier version of this
research made it.

**Model-free replication values and hedges the contract.** A variance swap's
payoff is spanned by vanilla options through the Carr-Madan identity

    [log S]_T = 2 integral(dS_t / S_t) - 2 log(S_T / S_0)

so the fair variance strike is a portfolio price: a static `dK/K^2`-weighted
strip plus a dynamic holding of `(2/T)(1/F - 1/S_t)` shares. No volatility model
appears anywhere in it, which is precisely why it is trustworthy - it is correct
whether or not any parametric model fits the surface.

**Black-Scholes Greeks measure and explain it.** Delta, gamma, vega and theta
give a common language for asking which risk factor moved the book today. Here
Black-Scholes is a *measurement* device, not a pricing belief.

**The canonical variance hedge is not aggregate Black-Scholes delta hedging.**
Over the full sample the strip's cumulative BSM delta P&L is +$777,002 while the
canonical identity hedge contributed -$609,783: it offsets 78.5% of the strip's
directional exposure, not 100%, and the gap is deliberate. A delta hedge tries to
make the option portfolio directionally neutral; the identity hedge is sized to
convert the static log contract into realised variance, and depends on
`1/F - 1/S_t` alone. The V5 methodology audit reached the same conclusion from
the other direction: an aggregate BSM delta hedge carried only ~57% of the
position the variance payoff requires, and tracked that payoff no better than no
hedge at all. Replacing the identity hedge with a Greek hedge reintroduces that
defect.

**Where a real model becomes unavoidable.** Static replication works because the
payoff is spanned. A *capped* realised-variance payoff, `min(RV, C)`, is
path-dependent and is spanned by nothing, so V7 calibrates a Heston model
point-in-time to price it. Note what that model is and is not asked to do: the
uncapped strike still comes model-free from the listed strip, and the model
prices only the incremental tail term `E^Q[(RV - C)+]`.

See `reports/capped_variance_greeks_v7/greeks_methodology.md` and
`heston_methodology.md` for the full treatment.

## Reproducing the research inputs

Every phase runs off two cached frames built once from the raw WRDS files:

```python
from equity_options_research.backtest.ingestion_config import IngestionConfig
from equity_options_research.backtest.wrds_eod import prepare_wrds_inputs

inputs = prepare_wrds_inputs(
    "data/raw/wrds/<option_prices>.csv.gz",
    "data/raw/wrds/<security_prices>.csv",
    "data/raw/wrds/<zero_curve>.csv",
    config=IngestionConfig(),
)
inputs.options.to_parquet("cache/options.parquet", index=False)
inputs.prices.to_parquet("cache/prices.parquet")
```

`inputs.options` carries paired call/put legs with a per-row `risk_free_rate`
interpolated from the zero curve; `inputs.prices` carries OHLC spot.
`inputs.realised` holds Garman–Klass realised variance and is used for the
data-quality report returned in `inputs.reports` — it is not an input to any
current strategy, so it is not persisted.

Raw WRDS data is not committed. The loaders enforce the vendor conventions
(strike scaled by 1000, standard contract size only, locally recomputed DTE) and
report what they dropped.

## Pricing and execution conventions

- **Forward**: put-call parity at the strike where call and put mids are
  closest. The dividend yield is implied from it, never assumed.
- **Realised variance**: sum of squared close-to-close log returns divided by the
  contract's own year fraction — the same `T` that prices the strip.
- **Execution**: OptionMetrics bid/ask with a 0.75 half-spread fill, $0.65 per
  contract per leg, 0.5bp SPY hedge slippage.
- **Financing**: self-financing cash account accrued on calendar days at the
  entry-date zero rate. Final cash *is* the P&L; reconciliation is exact to
  10⁻⁹.
- **Out-of-sample lock**: `research.final_test_guard` raises if a development
  table contains a date on or after 2023-01-01. Each phase hashes its frozen
  specification and writes a pre-OOS memo before unlocking.

## Known limitations and reproducibility

- Black-Scholes does not capture early exercise; American assignment on short
  in-the-money legs is not modelled.
- A drawdown-based capital proxy is not a broker margin engine.
- Daily hedging leaves gap and intraday delta risk.
- End-of-day quotes carry no depth or market impact, so capacity is not
  established.

Record the Git commit, the Python environment and the data snapshot when
reproducing. Bootstrap routines use a fixed seed.
