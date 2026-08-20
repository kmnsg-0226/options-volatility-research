# Local EOD SPY VRP backtest audit

This run is an implementation and accounting smoke test. It does not contain
enough completed trades for a profitability conclusion.

## Outcome

The full signal, delayed execution, short-straddle, hedge, exit, accounting,
and final-liquidation lifecycle completes and reconciles. The primary
configuration produced 1 completed trade(s) from
276 valid z-score observations. The low
count is primarily expected from signal scarcity: only
4 session(s) exceeded the primary 1.0
entry level. The short overlapping option/underlying window also materially
limits the number of opportunities.

## Root causes

- Entry behavior is a level condition: `z_t > entry_z` while flat. It is not
  an upward-crossing-only rule.
- Re-entry state clears after exits; no permanent one-entry lock was found.
- Turnover was reported as zero because performance analytics had no
  transaction-notional fields. The engine now records both option legs on
  entry and exit, plus only changes in hedge shares.
- The raw option file reaches 2022-12-30;
  the backtest ends at 2021-05-06 because the supplied SPY
  minute file ends there. The filename was not the problem.
- HAR training is expanding, purged, and uses a
  22-session embargo. All recorded
  training features and label ends strictly precede their forecast dates.

## Accounting

Premium turnover is 0.00521907, hedge notional
turnover is 0.05524814, and total cash-notional
turnover is 0.06046721. Entry/exit option legs, hedge
transactions, costs, trade P&L, cumulative P&L, and final equity reconcile.

## Diagnostic configuration

The separate diagnostic run produced 18
completed trade(s). It is labelled diagnostic and is not an investment
performance result. If fewer than five trades occurred, the accompanying
funnel identifies whether the binding constraint was valid z-score history,
threshold scarcity, or execution blocking; no further parameters were
changed.

## Interpretation

Raw descriptive values remain available, but Sharpe, Sortino, Calmar, win
rate, higher moments, VaR, expected shortfall, and t-statistics are flagged as
insufficient-sample statistics. The sensitivity grid is sorted by trade count
and must not be used to choose a profitable parameter set on this sample.

The pipeline successfully completes the full trade and hedge lifecycle, but
the sample contains too few completed trades for an inference about
profitability.
