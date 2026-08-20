"""Canonical variance-swap replication: strip + identity hedge + self-financing cash.

This is the first engine in the project that actually implements the object the
research claims to trade. It replaces three defects the methodology audit found in the legacy engine
that preceded it (removed from the tree; the audit is preserved under
`reports/variance_hedge_identity_audit/`):

1. **Hedge.** The legacy engine hedged the strip's Black-Scholes aggregate delta
   to zero, which carried roughly 57% of the position the log-contract identity
   requires. Here the dynamic leg is the identity's own
   ``h_t = N (2/T) (1/F - 1/S_t)`` -- model-free, needing no implied volatility,
   no Greeks and no strike set. The formula lives in ``variance_identity`` and is
   imported rather than restated, so it has one definition in the codebase.
2. **Horizon.** The legacy engine priced the strip on calendar maturity but
   exited at DTE <= 2, measuring realised variance over a shorter window. Here
   the contract runs to expiry and *one* horizon ``T`` annualises the fair
   strike, the strip weights, the hedge and the realised leg.
3. **Financing.** The legacy engine charged no interest on a share position that
   reached tens of millions of dollars. Here every cash movement is tracked and
   the book is self-financing by construction: final cash *is* the P&L.

The dividend yield is no longer assumed. It is implied per trade from the
put-call-parity forward, ``q = r - ln(F/S)/T``, so the hedge and the strip agree
with the market's own carry.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from equity_options_research.execution.costs import option_commission
from equity_options_research.execution.option_fill import option_fill
from equity_options_research.research.model_free_variance import StripSelection
from equity_options_research.research.variance_identity import hedge_shares

DAYS_PER_YEAR = 365.0


@dataclass(frozen=True)
class CanonicalConfig:
    """Execution and accounting conventions for the canonical engine."""

    variance_notional: float = 1_000_000.0
    multiplier: int = 100
    integer_contracts: bool = False
    execution_lambda: float = 0.75
    option_commission_per_contract: float = 0.65
    hedge_slippage_bps: float = 0.5
    equity_commission_per_share: float = 0.0


@dataclass
class CashAccount:
    """Self-financing ledger. Final balance is the trade's P&L."""

    rate: float
    balance: float = 0.0
    interest: float = 0.0
    _flows: list[tuple[str, float]] = field(default_factory=list)

    def flow(self, label: str, amount: float) -> None:
        self.balance += amount
        self._flows.append((label, amount))

    def accrue(self, days: float) -> None:
        earned = self.balance * self.rate * days / DAYS_PER_YEAR
        self.interest += earned
        self.balance += earned

    @property
    def flows(self) -> list[tuple[str, float]]:
        return list(self._flows)


def implied_dividend_yield(forward: float, spot: float, rate: float, year_fraction: float) -> float:
    """Back out q from the parity forward instead of assuming it."""

    if forward <= 0 or spot <= 0 or year_fraction <= 0:
        raise ValueError("forward, spot and year_fraction must be positive")
    return float(rate - np.log(forward / spot) / year_fraction)


def strip_weights(strip: StripSelection, notional: float, multiplier: int) -> np.ndarray:
    """Contracts per strike: N (2/T) dK/K^2 / multiplier."""

    return notional * (2.0 / strip.year_fraction) * strip.delta_k / strip.strikes**2 / multiplier


def realised_variance(spot_path: np.ndarray, year_fraction: float) -> float:
    """Annualised realised variance over the contract, using the contract's own T.

    Total variance is the sum of squared close-to-close log returns over exactly
    the contract life; annualising by the *same* ``T`` that prices the strip is
    what removes the legacy mismatch.
    """

    s = np.asarray(spot_path, dtype=float)
    if s.size < 2 or year_fraction <= 0:
        return float("nan")
    return float(np.sum(np.log(s[1:] / s[:-1]) ** 2) / year_fraction)


def strip_intrinsic(strip: StripSelection, contracts: np.ndarray, terminal_spot: float, multiplier: int) -> float:
    """Settlement value of the strip at expiry."""

    total = 0.0
    for i, strike in enumerate(strip.strikes):
        right = strip.rights[i]
        put = max(float(strike) - terminal_spot, 0.0)
        call = max(terminal_spot - float(strike), 0.0)
        value = put if right == "put" else call if right == "call" else 0.5 * (put + call)
        total += float(contracts[i]) * multiplier * value
    return total


def run_canonical_trade(
    strip: StripSelection,
    spot_path: np.ndarray,
    day_counts: np.ndarray,
    config: CanonicalConfig,
    fair_strike: float,
) -> dict[str, float]:
    """Replicate one short variance-swap trade from entry to expiry.

    ``spot_path`` runs from the entry close to the settlement close inclusive;
    ``day_counts`` holds the calendar days between consecutive observations, so
    interest accrues over holidays and weekends rather than trading days.
    """

    n = config.variance_notional
    t = strip.year_fraction
    fractional = strip_weights(strip, n, config.multiplier)
    contracts = np.rint(fractional) if config.integer_contracts else fractional

    cash = CashAccount(rate=strip.rate)

    # --- sell the strip ---
    proceeds = 0.0
    option_exec = 0.0
    commissions = 0.0
    for i in range(len(strip.strikes)):
        q = float(contracts[i])
        if q == 0:
            continue
        bid, ask = float(strip.bids[i]), float(strip.asks[i])
        if not (np.isfinite(bid) and np.isfinite(ask) and ask > bid and bid >= 0):
            continue
        fill = option_fill(bid, ask, "sell", config.execution_lambda)
        notional_i = q * config.multiplier
        proceeds += fill.price * notional_i
        option_exec += notional_i * fill.execution_cost_per_share
        commissions += option_commission(
            max(int(round(abs(q))), 1), legs=1, per_contract=config.option_commission_per_contract
        )
    cash.flow("option_premium", proceeds)
    cash.flow("option_commissions", -commissions)

    # --- dynamic hedge, financed ---
    s = np.asarray(spot_path, dtype=float)
    target = hedge_shares(n, t, strip.forward, s)
    if config.integer_contracts:
        target = np.rint(target)
    held = 0.0
    hedge_slippage = 0.0
    shares_traded = 0.0
    for i in range(len(s) - 1):
        trade = target[i] - held
        if trade != 0:
            slip = abs(trade) * s[i] * config.hedge_slippage_bps / 10_000.0
            cash.flow("hedge_trade", -trade * s[i])
            cash.flow("hedge_slippage", -slip)
            hedge_slippage += slip
            shares_traded += abs(trade)
            held = target[i]
        cash.accrue(float(day_counts[i]))

    # --- settlement ---
    settlement = strip_intrinsic(strip, contracts, float(s[-1]), config.multiplier)
    cash.flow("option_settlement", -settlement)
    if held != 0:
        slip = abs(held) * s[-1] * config.hedge_slippage_bps / 10_000.0
        cash.flow("hedge_unwind", held * s[-1])
        cash.flow("hedge_unwind_slippage", -slip)
        hedge_slippage += slip
        shares_traded += abs(held)

    rv = realised_variance(s, t)
    theoretical = n * (fair_strike - rv)
    hedge_pnl = float(np.sum(target[:-1] * np.diff(s)))
    # `proceeds` is already net of the crossed spread, so add it back to state a
    # mid-based gross figure; that keeps `net = gross + financing - costs` exact.
    option_pnl = (proceeds + option_exec) - settlement
    costs = option_exec + commissions + hedge_slippage
    gross = option_pnl + hedge_pnl
    reconciliation = cash.balance - (gross + cash.interest - costs)

    return {
        "fair_strike": fair_strike,
        "realised_variance": rv,
        "theoretical_vs_pnl": theoretical,
        "option_premium": proceeds,
        "option_settlement": settlement,
        "option_pnl": option_pnl,
        "hedge_pnl": hedge_pnl,
        "financing": cash.interest,
        "option_execution_cost": option_exec,
        "option_commissions": commissions,
        "hedge_slippage": hedge_slippage,
        "total_costs": costs,
        "gross_pnl": gross,
        "reconciliation_error": reconciliation,
        "net_pnl": cash.balance,
        "cash_balance": cash.balance,
        "tracking_error": cash.balance - theoretical,
        "shares_traded": shares_traded,
        "contracts_total": float(np.abs(contracts).sum()),
        "legs": float(len(strip.strikes)),
        "contracts_per_leg": float(np.abs(contracts).sum() / max(len(strip.strikes), 1)),
        "zero_legs": float((np.rint(fractional) == 0).mean()),
        "implied_dividend": implied_dividend_yield(strip.forward, float(s[0]), strip.rate, t),
    }
