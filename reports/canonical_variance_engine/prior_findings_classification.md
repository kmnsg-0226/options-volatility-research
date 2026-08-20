# Which prior findings survive

## VALID — measurement findings, independent of the hedge

These were computed from option chains and quotes, never from replicated P&L:

- **Model-free implied variance construction** and the CBOE strike integration
  (validated against Black–Scholes to within 5% on synthetic chains).
- **ATM IV² vs model-free variance**: ATM premium −0.00232 (NW t −0.70) versus
  model-free +0.00658 (NW t +2.03). The finding that ATM IV measures no premium
  while the strike-integrated measure does **stands**.
- **The skew wedge**, +0.0089 to +0.0091, reproduced independently twice.
- **Where variance lives across strikes**: puts 68.6%, calls 27.4%, the 90–100%
  put band alone 53.8%.
- **Option-chain quality diagnostics**: 95.8% chain success, contract-size and
  strike-scaling conventions, expiration-day exclusion.
- **Zero-curve handling**: percent→decimal, linear-in-days interpolation, no
  forward-date fallback.
- **HAR vs implied variance as forecasters** — a forecasting comparison, not a
  P&L result.
- **The variance premium itself is positive**: +$564,513 theoretical pre-2023 and
  +$74,632 OOS under the canonical engine.

## INVALIDATED for strategy selection — computed on the legacy engine

Every one of these ranked candidates using a portfolio that tracked the variance
swap payoff at correlation 0.712, no better than holding no hedge (0.721):

- variance-strip Sharpe at any coverage
- **strike-coverage selection** (c80/c90/c95) — now *reversed*: the full strip
  dominates
- corridor selection (80–120, 85–115, 90–110)
- risk-target sizing conclusions
- hedge-policy selection, including the daily-hedge default
- tail-control and protective-put conclusions
- replication-scaling (V4) strategy conclusions
- the pre-2023 frozen strategy and its OOS test

Nothing is deleted. All prior directories remain, and should be read as results
from the **legacy delta-hedged short-option-strip engine**, not from a variance
swap replication.
