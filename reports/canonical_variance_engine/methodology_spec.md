# V5 canonical variance-replication engine — specification

## What changed from the legacy engine

| | Legacy (`variance_replication.py`) | **Canonical (`canonical_variance_engine.py`)** |
|---|---|---|
| Dynamic leg | BSM aggregate strip delta → 0 | **`h_t = N(2/T)(1/F − 1/S_t)`** from the log-contract identity |
| Depends on | IV surface, q, r, strike set | **spot, forward, T, N only** |
| Horizon | priced on `dte/365`, exited at DTE ≤ 2 | **runs to expiry; one `T` throughout** |
| Realised leg | `252/n × Σx²` (different window) | **`Σx² / T_contract`** (same window, same `T`) |
| Financing | zero | **explicit self-financing cash account** |
| Dividend | hard-coded `q = 1.3%` | **implied per trade from the parity forward** |
| Settlement | market close at DTE ≤ 2 | **intrinsic value at expiry** |

The legacy engine is retained unchanged and remains reproducible.

## Contract definition

- **Entry** `t0`: first trading day of the month.
- **Expiry**: listed expiry nearest 30 calendar days, constrained to 21–45 DTE.
- **Horizon** `T = (expiry − t0)/365`, one value used for the fair strike, the
  strip weights `N(2/T)ΔK/K²/mult`, the hedge `N(2/T)(1/F − 1/S)` and the
  realised leg.
- **Settlement**: strip intrinsic against the expiry close; hedge unwound the
  same session. SPY options are American, so early exercise is possible and
  ignored — an approximation, documented, not modelled.
- **Non-trading days**: the spot path uses trading closes only, while interest
  accrues on **calendar** days between consecutive observations, so weekends and
  holidays are financed.

## Dividends

`q` is no longer assumed. Per trade it is implied from the put-call-parity
forward, `q = r − ln(F/S)/T`. Realised mean **1.72%**, median **0.70%** — both
away from the legacy 1.3%, with wide dispersion.

**One residual inconsistency is disclosed rather than patched.** The realised leg
uses SPY *price* returns, so ex-dividend drops enter as variance even though they
are not volatility. Removing them needs an actual ex-date/amount series, which
this project does not have. The effect is roughly 0.5–0.6% of typical realised
variance and biases it upward, i.e. against the short-variance seller. I have not
fabricated a dividend series.

## Verification

The accounting identity `net = gross + financing − costs` holds to
**1.16e-09** across all 152 trades, and final cash *is* the P&L by construction.
