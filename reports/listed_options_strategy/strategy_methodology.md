# V8 methodology — a Greek-managed listed SPY option strategy

## What this is, and what it is not

A listed SPY option book, managed the way a listed option book actually is.
Black–Scholes is not a diagnostic here: implied volatility selects the strikes,
Greeks size the position and cap its risk, and a daily Black–Scholes delta hedge
keeps the book directionally flat.

It is **not** a variance swap, a capped variance swap, a static replication of the
log contract, or an OTC derivative. Every instrument is an exchange-listed SPY
option present in OptionMetrics.

**The hedge is deliberately different from V5's.** The canonical variance engine
hedges with the model-free log-contract identity `h_t = N(2/T)(1/F − 1/S_t)`,
because that is what replicates a variance payoff. Using that hedge here would be
wrong — it hedges a different payoff. This book holds four listed contracts whose
delta is a Black–Scholes quantity, so it is hedged with Black–Scholes delta. Each
hedge is correct for its own product; neither is correct for the other.

## Structure

Per unit ("structure"):

    short 1 call at the listed strike nearest the parity forward
    short 1 put  at the listed strike nearest the parity forward
    long  1 call at |delta| ≈ w        (10 or 15 delta)
    long  1 put  at |delta| ≈ w

Short legs sit nearest the **forward**, not spot, so a material carry basis does
not silently skew the straddle. Wings are chosen by Black–Scholes delta, never by
dollar distance from the strike.

## Conventions

- **Entry**: first trading day of each calendar month, 2013 onward.
- **Maturity**: expiry nearest 30 DTE within a fixed 25–40 band. Not optimised.
- **Exit**: first trading day with DTE ≤ 7. Not optimised. SPY options are
  American; early assignment is **not modelled**, and closing a week early keeps
  that exposure smaller than holding to expiry would.
- **Forward and dividend**: forward from put–call parity at the strike where call
  and put mids are closest; `q = r − ln(F/S)/T`. Nothing is hard-coded.
- **Greeks**: point-in-time Black–Scholes on same-date spot, rate, remaining
  maturity and that implied dividend. Validated against finite differences.
- **Quote filters**: positive bid, mid ≥ $0.05, relative spread ≤ 60%.

## Sizing: vega budget, then a gamma brake

1. **Vega budget**: structures = $10,000 target absolute vega (per volatility
   point) ÷ |vega per structure|.
2. **Dollar-gamma stress cap**: `0.5 × |Γ·S²| × 0.03² ≤ 5% of $1,000,000`
   reference capital. If the vega-sized position breaches it, size is cut.

The cap **can only reduce size, never increase it**, and it is floored to whole
structures.

The 5% budget comes from development risk accounting, not from returns: sized
purely to the vega target, a 3% one-day move costs a median 4.2% of reference
capital across the 120 development entries, with a 95th percentile of 7.5%. A 5%
cap is a round number near the 70th–75th percentile, so it binds only in the
upper quartile of gamma states. That was the intent; in practice it binds on
95–97% of entries, which means **the gamma cap, not the vega target, is the
operative sizing rule** — realised vega averages $5,400 against a $10,000 target.

## Hedging and accounting

Each observation: revalue every leg, invert its implied volatility, aggregate
portfolio delta, and trade SPY so total delta is zero. Residual delta after
hedging is exactly 0 shares on every non-closing day.

If a leg's implied volatility cannot be inverted — an end-of-day quote below
intrinsic on a violent day — the leg's **last solved volatility is repriced at
today's spot**. If no leg solves at all, the existing hedge is **held**, never
liquidated. This matters: an earlier version zeroed the hedge on such days,
which closed and reopened the entire share position at gap prices and fabricated
P&L (it turned the COVID trade from −$302,734 into +$191,791). Eight of 2,085
option-days needed the carried-forward volatility.

Accounting reuses the V5 pattern: a self-financing cash account tracks option
premiums, execution cost, commissions, share trades, slippage and interest
accrued on calendar days. Final cash **is** the P&L, and reconciliation is exact
to 10⁻¹¹.

## Costs

Actual OptionMetrics bid/ask with a 0.75 half-spread fill, $0.65 per contract
per leg, 0.5bp SPY hedge slippage, and financing at the entry-date zero rate.
Wing costs are never netted away: a four-leg structure matched to the same dollar
gamma needs 3.6× the contracts of a two-leg one, and the cost tables report that
in full.

## Known limitations

- **Early assignment is not modelled.** Short in-the-money legs carry real
  assignment risk that end-of-day quotes cannot capture.
- **The gamma cap is applied at entry only.** Dollar gamma grows as expiry
  approaches: entry gamma averages −$44M but the largest intra-trade reading is
  −$126M. The DTE ≤ 7 exit is the only control on that drift.
- **Wing delta degrades when strikes are sparse.** The nearest listed strike is
  taken even when it is a poor match: the achieved wing delta is within 0.05 of
  target on 149 of 152 entries, worst case 0.15.
- **Capacity is not established.** End-of-day OptionMetrics quotes carry no
  depth, no intraday liquidity and no market impact. Contract counts describe
  what the backtest traded, not what the market would absorb.
