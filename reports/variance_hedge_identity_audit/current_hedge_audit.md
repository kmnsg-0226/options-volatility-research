# Audit of the existing hedge implementation

## The rule as coded

Source: `variance_replication.strip_delta` + the hedge loop in the runner.

| Aspect | Implementation |
|---|---|
| Source of delta | `Σ_i contracts_i × multiplier × δ_i` |
| δ_i | **Black–Scholes delta**, from an IV solved on that option's *own* midpoint |
| Dividend | constant `q = 0.013`, all strikes, all dates |
| Rate | zero-curve rate **fixed at entry**, reused for the whole trade life |
| Maturity in δ | *remaining* life, `max(dte_t/365, 1e-8)` |
| When measured | each session's close, on that session's quotes |
| When traded | same session's close |
| Hedge target | **exact zero net delta** |
| Rounding | `int(round(...))` shares |
| Multiple legs | summed; the K₀ straddle counted 0.5/0.5 |
| Hedge P&L | `shares_{t-1} × (S_t − S_{t-1})` — prior position, no look-ahead ✓ |
| Execution | `S ± 0.5bps`, commission `0` per share |
| Settlement | closed to zero at exit ✓ |
| Financing | **zero** — no interest on the cash implied by the share position |

The accounting mechanics are sound: P&L uses the prior share count, the position
is closed at exit, and no future information enters.

## Is this the hedge the identity requires?

**NOT EQUIVALENT.**

The identity (theory_derivation.md §6) requires

    h_t = N·(2/T)·(1/F − 1/S_t)

which is **model-free**. The implementation instead uses

    h_t = Σ_i n_i·mult·δ_i(BSM, IV_i, q, r, remaining T)

which depends on the implied-volatility surface, the dividend and rate
assumptions, the remaining maturity, and — decisively — **on which strikes
survive truncation**.

### Empirical size of the gap

Across all 3,015 held sessions:

- correlation(strip delta, theory delta) = **0.888**
- regression `strip_delta = 0.5666 × theory_delta`, R² = **0.789**
- mean |difference| = **1,289 shares**, p95 = 3,560

**The strip carries about 57% of the delta the log contract requires.** The
direction is right; the magnitude is not.

### Why: truncation

The frozen strategy trades the *central 80% of variance weight*, which spans a
mean moneyness range of only **[0.865, 1.021]** — barely 16 percentage points
wide and asymmetric. The log contract's delta `−2/(TS)` is generated across the
full strike continuum; cutting the wings removes exactly the options whose delta
grows as spot moves away. A synthetic test (`test_truncating_the_wings_biases_
the_strip_delta_toward_zero`) confirms the mechanism in isolation.

So the under-hedging is not a coding error — it is the arithmetic consequence of
delta-hedging a *truncated* strip while claiming to replicate an *untruncated*
log contract.

## Two further issues found

**1. Annualisation mismatch (unit audit).** The strip is sized and priced on
calendar maturity `T = dte/365` (mean 0.0823), but the position is closed at
DTE ≤ 2, so realised variance is measured over a shorter window — mean trading
maturity `n/252 = 0.0770`. The ratio is **1.076**. Reconstructing variance with
calendar `T` rather than trading `T` biases the result by **−5.9%**. The realised
leg is 252-based, so the identity must use trading-day `T`; all identity checks
in this audit do.

**2. No financing account.** `financing_cost` is zero throughout. The theoretical
hedge holds up to several thousand shares — tens of millions of dollars of
notional at times — with no interest charged or earned. Over ~30-day horizons at
2–5% this is a real omission, though small relative to the hedge P&L itself.

## What the previous backtests actually were

Given a 0.57 delta ratio and tracking correlation of 0.712 against the variance
swap payoff — barely better than **holding no hedge at all** (0.721) — the honest
description is:

> a **delta-hedged short option strip**, systematically under-hedged, not a
> variance-swap replication.
