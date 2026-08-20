"""A delta-hedged, Greek-managed listed SPY option volatility strategy.

This is deliberately *not* a variance swap. Where the canonical V5 engine
replicates a payoff spanned by a continuum of strikes and hedges it with the
model-free log-contract identity, this book holds four listed contracts and is
managed the way a listed options book actually is: Black-Scholes implied
volatility selects the strikes, Black-Scholes Greeks size the position and cap
its risk, and a daily Black-Scholes delta hedge keeps it directionally flat.
Using the identity hedge here would be wrong -- it hedges a different payoff.

Structure, per unit:

    short 1 call  at K ~ F        (the theta engine)
    short 1 put   at K ~ F
    long  1 call  at |delta| ~ w  (the convexity brake)
    long  1 put   at |delta| ~ w

Sizing runs in two stages. A vega budget sets the nominal size, then a
dollar-gamma stress cap can only ever reduce it: the book is never levered up to
reach a risk target, only cut back to respect one.

Known limitation: SPY options are American. Early assignment is not modelled.
The fixed close-before-expiry rule exists partly to keep that exposure small,
but short in-the-money legs carry real assignment risk that end-of-day
OptionMetrics quotes cannot capture.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from equity_options_research.execution.costs import option_commission
from equity_options_research.execution.option_fill import option_fill
from equity_options_research.pricing.greeks import all_greeks
from equity_options_research.pricing.implied_vol import implied_volatility

DAYS_PER_YEAR = 365.0
MULTIPLIER = 100


@dataclass(frozen=True)
class StrategyConfig:
    """Every convention the strategy needs, fixed before results are examined."""

    wing_delta: float | None = 0.10          # None means a naked straddle
    target_vega_dollars: float = 10_000.0    # per one volatility point, absolute
    reference_capital: float = 1_000_000.0
    gamma_stress_move: float = 0.03          # one-day SPY move used for the cap
    gamma_stress_budget: float = 0.02        # as a fraction of reference capital
    target_dte: int = 30
    min_dte: int = 25
    max_dte: int = 40
    exit_dte: int = 7
    min_option_price: float = 0.05
    max_relative_spread: float = 0.60
    execution_lambda: float = 0.75
    option_commission_per_contract: float = 0.65
    hedge_slippage_bps: float = 0.5
    sizing_mode: str = "vega"                # "vega" or "gamma_stress"

    @property
    def gamma_stress_cap(self) -> float:
        return self.gamma_stress_budget * self.reference_capital


@dataclass
class CashAccount:
    """Self-financing ledger; the closing balance is the trade's P&L."""

    rate: float
    balance: float = 0.0
    interest: float = 0.0
    flows: list[tuple[str, float]] = field(default_factory=list)

    def flow(self, label: str, amount: float) -> None:
        self.balance += amount
        self.flows.append((label, amount))

    def accrue(self, days: float) -> None:
        earned = self.balance * self.rate * days / DAYS_PER_YEAR
        self.interest += earned
        self.balance += earned


@dataclass(frozen=True)
class Leg:
    """One listed contract. ``quantity`` is signed per structure: negative is short."""

    right: str
    strike: float
    quantity: float


def parity_forward(frame: pd.DataFrame, rate: float, year_fraction: float) -> float:
    """Forward implied by put-call parity where call and put mids are closest.

    Same convention as the canonical engine, so the dividend yield is implied
    from the market rather than assumed.
    """

    both = frame[(frame.call_bid > 0) & (frame.put_bid > 0)]
    if both.empty:
        return float(frame.spot.iloc[0] * np.exp(rate * year_fraction))
    call_mid = 0.5 * (both.call_bid + both.call_ask)
    put_mid = 0.5 * (both.put_bid + both.put_ask)
    i = int((call_mid - put_mid).abs().to_numpy().argmin())
    return float(both.strike.iloc[i] + np.exp(rate * year_fraction) * (call_mid.iloc[i] - put_mid.iloc[i]))


def implied_dividend(forward: float, spot: float, rate: float, year_fraction: float) -> float:
    return float(rate - np.log(forward / spot) / year_fraction)


def usable(bid: float, ask: float, config: StrategyConfig) -> bool:
    """Reject quotes that cannot be traded against."""

    if not (np.isfinite(bid) and np.isfinite(ask)) or bid <= 0 or ask <= bid:
        return False
    mid = 0.5 * (bid + ask)
    return mid >= config.min_option_price and (ask - bid) / mid <= config.max_relative_spread


def leg_quote(row: pd.Series, right: str) -> tuple[float, float]:
    return (float(row.call_bid), float(row.call_ask)) if right == "call" else (float(row.put_bid), float(row.put_ask))


def solve_leg(
    row: pd.Series, right: str, spot: float, year_fraction: float, rate: float, dividend: float,
    fallback_vol: float | None = None,
) -> dict[str, float] | None:
    """Implied volatility and Greeks for one contract, from same-date data only.

    On violent days an end-of-day quote can sit below intrinsic and the
    inversion fails. Rather than lose the leg, ``fallback_vol`` — the leg's own
    last solved volatility — is repriced at today's spot and maturity. Refusing
    to produce a delta at all is the worse option: it would leave the book
    unhedged on exactly the days that matter.
    """

    bid, ask = leg_quote(row, right)
    mid = 0.5 * (bid + ask)
    iv = implied_volatility(right, mid, spot, float(row.strike), year_fraction, rate, dividend)
    if iv.success and iv.volatility is not None:
        sigma, stale = float(iv.volatility), False
    elif fallback_vol is not None and np.isfinite(fallback_vol):
        sigma, stale = float(fallback_vol), True
    else:
        return None
    g = all_greeks(right, spot, float(row.strike), year_fraction, rate, dividend, sigma)
    return {"strike": float(row.strike), "bid": bid, "ask": ask, "mid": mid,
            "implied_vol": sigma, "stale_vol": stale, **g}


def select_structure(
    chain: pd.DataFrame, spot: float, forward: float, year_fraction: float,
    rate: float, dividend: float, config: StrategyConfig,
) -> list[dict[str, Any]] | None:
    """Pick the four contracts by Black-Scholes delta, not by dollar distance.

    The short legs sit nearest the forward rather than nearest spot, so that a
    material carry basis does not silently skew the straddle.
    """

    solved: list[dict[str, Any]] = []
    for _, row in chain.iterrows():
        for right in ("call", "put"):
            bid, ask = leg_quote(row, right)
            if not usable(bid, ask, config):
                continue
            s = solve_leg(row, right, spot, year_fraction, rate, dividend)
            if s is not None:
                solved.append({**s, "right": right})
    if not solved:
        return None
    frame = pd.DataFrame(solved)

    calls, puts = frame[frame.right == "call"], frame[frame.right == "put"]
    if calls.empty or puts.empty:
        return None

    short_call = calls.iloc[(calls.strike - forward).abs().to_numpy().argmin()].to_dict()
    short_put = puts.iloc[(puts.strike - forward).abs().to_numpy().argmin()].to_dict()
    legs = [{**short_call, "quantity": -1.0, "role": "short_call"},
            {**short_put, "quantity": -1.0, "role": "short_put"}]

    if config.wing_delta is not None:
        otm_calls = calls[calls.strike > short_call["strike"]]
        otm_puts = puts[puts.strike < short_put["strike"]]
        if otm_calls.empty or otm_puts.empty:
            return None
        wing_call = otm_calls.iloc[(otm_calls.delta.abs() - config.wing_delta).abs().to_numpy().argmin()].to_dict()
        wing_put = otm_puts.iloc[(otm_puts.delta.abs() - config.wing_delta).abs().to_numpy().argmin()].to_dict()
        if wing_call["strike"] == short_call["strike"] or wing_put["strike"] == short_put["strike"]:
            return None
        legs += [{**wing_call, "quantity": 1.0, "role": "long_call_wing"},
                 {**wing_put, "quantity": 1.0, "role": "long_put_wing"}]
    return legs


def aggregate_greeks(legs: list[dict[str, Any]], spot: float, structures: float = 1.0) -> dict[str, float]:
    """Portfolio Greeks for ``structures`` units, in per-contract dollar terms."""

    scale = structures * MULTIPLIER
    out = {g: float(sum(float(x["quantity"]) * float(x[g]) for x in legs)) * scale
           for g in ("delta", "gamma", "vega", "theta")}
    out["dollar_gamma"] = out["gamma"] * spot**2
    out["vega_dollars"] = out["vega"] / 100.0          # per one volatility point
    out["theta_per_day"] = out["theta"] / DAYS_PER_YEAR
    out["delta_shares"] = out["delta"]
    return out


def greek_efficiency(greeks: dict[str, float]) -> dict[str, float]:
    """How much carry the book earns per unit of the risk it is taking."""

    dg, ve = abs(greeks["dollar_gamma"]), abs(greeks["vega_dollars"])
    theta = greeks["theta_per_day"]
    return {"theta_per_dollar_gamma": theta / dg if dg > 0 else np.nan,
            "theta_per_vega": theta / ve if ve > 0 else np.nan}


def size_structures(unit: dict[str, float], config: StrategyConfig) -> dict[str, float]:
    """Vega budget sets the size; the gamma stress cap can only reduce it."""

    unit_vega = abs(unit["vega_dollars"])
    unit_stress = 0.5 * abs(unit["dollar_gamma"]) * config.gamma_stress_move**2
    if unit_vega <= 0:
        return {"desired": 0.0, "structures": 0.0, "gamma_capped": False,
                "realised_vega": 0.0, "rounding_error": 0.0, "unit_stress_loss": unit_stress}

    if config.sizing_mode == "gamma_stress":
        desired = config.gamma_stress_cap / unit_stress if unit_stress > 0 else 0.0
        capped = False
    else:
        desired = config.target_vega_dollars / unit_vega
        capped = unit_stress > 0 and desired * unit_stress > config.gamma_stress_cap
        if capped:
            desired = config.gamma_stress_cap / unit_stress

    structures = float(max(int(np.floor(desired)), 0))
    return {"desired": desired, "structures": structures, "gamma_capped": bool(capped),
            "realised_vega": structures * unit_vega,
            "rounding_error": (structures - desired) * unit_vega,
            "unit_stress_loss": unit_stress,
            "sized_stress_loss": structures * unit_stress}


def _trade_options(
    legs: list[dict[str, Any]], structures: float, opening: bool, config: StrategyConfig,
    quotes: dict[tuple[str, float], tuple[float, float]] | None = None,
) -> tuple[float, float, float, float]:
    """Execute all option legs. Returns (cash flow, mid value, spread cost, commissions).

    ``opening`` flips every leg's side: a leg that is short in the structure is
    sold to open and bought to close.
    """

    cash = mid_value = spread_cost = commissions = 0.0
    for leg in legs:
        q = float(leg["quantity"]) * structures
        if q == 0:
            continue
        key = (str(leg["right"]), float(leg["strike"]))
        bid, ask = quotes[key] if quotes is not None else (float(leg["bid"]), float(leg["ask"]))
        if not (np.isfinite(bid) and np.isfinite(ask) and ask > bid and bid >= 0):
            continue
        signed = q if opening else -q
        side = "sell" if signed < 0 else "buy"
        fill = option_fill(bid, ask, side, config.execution_lambda)
        size = abs(signed) * MULTIPLIER
        cash += -signed * fill.price * MULTIPLIER          # selling brings cash in
        mid_value += -signed * 0.5 * (bid + ask) * MULTIPLIER
        spread_cost += size * fill.execution_cost_per_share
        commissions += option_commission(
            max(int(round(abs(q))), 1), legs=1, per_contract=config.option_commission_per_contract
        )
    return cash, mid_value, spread_cost, commissions


def run_listed_trade(
    legs: list[dict[str, Any]],
    structures: float,
    panel: pd.DataFrame,
    config: StrategyConfig,
    rate: float,
) -> dict[str, Any]:
    """Run one structure from entry to the close-before-expiry date.

    ``panel`` holds one row per (trading day, strike) for the traded expiry, with
    quotes, spot, DTE and the day's rate. The book is delta hedged with SPY at
    every observation using point-in-time Black-Scholes deltas.
    """

    dates = sorted(panel.quote_date.unique())
    cash = CashAccount(rate=rate)
    held_shares = 0.0
    hedge_slippage = shares_traded = 0.0
    option_spread = option_comm = 0.0
    daily: list[dict[str, float]] = []
    entry_mid = exit_mid = 0.0
    exit_date = None
    last_vol: dict[tuple[str, float], float] = {}
    stale_days = 0
    previous: list[dict[str, Any]] | None = None
    previous_spot = np.nan

    for i, day in enumerate(dates):
        rows = panel[panel.quote_date == day]
        dte = float(rows.dte.iloc[0])
        spot = float(rows.spot.iloc[0])
        year_fraction = dte / DAYS_PER_YEAR
        day_rate = float(rows.rate.iloc[0]) if np.isfinite(rows.rate.iloc[0]) else rate
        quotes = {(r, float(row.strike)): leg_quote(row, r)
                  for _, row in rows.iterrows() for r in ("call", "put")}

        if i > 0:
            cash.accrue((pd.Timestamp(day) - pd.Timestamp(dates[i - 1])).days)

        if i == 0:
            flow, entry_mid, sc, cm = _trade_options(legs, structures, True, config)
            cash.flow("option_open", flow)
            cash.flow("option_commissions", -cm)
            option_spread += sc
            option_comm += cm

        # --- point-in-time Greeks on live quotes ---
        forward = parity_forward(rows, day_rate, year_fraction) if year_fraction > 0 else spot
        div = implied_dividend(forward, spot, day_rate, year_fraction) if year_fraction > 0 else 0.0
        live: list[dict[str, Any]] = []
        stale_here = 0
        for leg in legs:
            row = rows[rows.strike == float(leg["strike"])]
            if row.empty:
                continue
            key = (str(leg["right"]), float(leg["strike"]))
            s = solve_leg(row.iloc[0], str(leg["right"]), spot, year_fraction, day_rate, div,
                          last_vol.get(key))
            if s is not None:
                if not s.get("stale_vol", False):
                    last_vol[key] = float(s["implied_vol"])
                else:
                    stale_here += 1
                live.append({**s, "right": leg["right"], "quantity": leg["quantity"]})
        stale_days += 1 if stale_here else 0
        if len(live) < len(legs):
            # No usable delta at all. Hold the existing hedge rather than
            # liquidating it: flattening here would trade on a data gap.
            greeks = {"delta": np.nan, "gamma": np.nan, "vega": np.nan, "theta": np.nan,
                      "dollar_gamma": np.nan, "vega_dollars": np.nan, "theta_per_day": np.nan,
                      "delta_shares": np.nan}
        else:
            greeks = aggregate_greeks(live, spot, structures)

        # --- Greek attribution of the option leg over the interval just ended ---
        att = {"delta_pnl": np.nan, "gamma_pnl": np.nan, "vega_pnl": np.nan,
               "theta_pnl": np.nan, "option_mark_pnl": np.nan}
        if previous is not None and len(live) == len(previous):
            ds = spot - previous_spot
            dt_years = (pd.Timestamp(day) - pd.Timestamp(dates[i - 1])).days / DAYS_PER_YEAR
            scale = structures * MULTIPLIER
            by_key = {(str(x["right"]), float(x["strike"])): x for x in live}
            d_pnl = g_pnl = v_pnl = t_pnl = mark = 0.0
            for prev in previous:
                key = (str(prev["right"]), float(prev["strike"]))
                now = by_key.get(key)
                if now is None:
                    continue
                q = float(prev["quantity"]) * scale
                d_pnl += q * float(prev["delta"]) * ds
                g_pnl += 0.5 * q * float(prev["gamma"]) * ds**2
                v_pnl += q * float(prev["vega"]) * (float(now["implied_vol"]) - float(prev["implied_vol"]))
                t_pnl += q * float(prev["theta"]) * dt_years
                mark += q * (float(now["mid"]) - float(prev["mid"]))
            att = {"delta_pnl": d_pnl, "gamma_pnl": g_pnl, "vega_pnl": v_pnl,
                   "theta_pnl": t_pnl, "option_mark_pnl": mark}
        previous = live if len(live) == len(legs) else previous
        previous_spot = spot if len(live) == len(legs) else previous_spot

        closing = dte <= config.exit_dte or i == len(dates) - 1
        target = 0.0 if closing else -greeks["delta_shares"]     # hedge the option delta to flat
        if not np.isfinite(target):
            target = held_shares
        trade = target - held_shares
        if trade != 0:
            slip = abs(trade) * spot * config.hedge_slippage_bps / 10_000.0
            cash.flow("hedge_trade", -trade * spot)
            cash.flow("hedge_slippage", -slip)
            hedge_slippage += slip
            shares_traded += abs(trade)
            held_shares = target

        daily.append({"date": pd.Timestamp(day), "dte": dte, "spot": spot, "forward": forward,
                      "dividend": div, "rate": day_rate, "structures": structures,
                      **{k: greeks[k] for k in ("delta", "gamma", "vega", "theta",
                                                "dollar_gamma", "vega_dollars", "theta_per_day")},
                      "hedge_shares": held_shares, "hedge_trade": trade,
                      "mean_iv": float(np.mean([float(x["implied_vol"]) for x in live])) if live else np.nan,
                      "stale_legs": stale_here, "closing": closing, **att,
                      "residual_delta": (greeks["delta_shares"] + held_shares) if not closing else 0.0,
                      "cash_balance": cash.balance})

        if closing:
            flow, exit_mid, sc, cm = _trade_options(legs, structures, False, config, quotes)
            cash.flow("option_close", flow)
            cash.flow("option_commissions", -cm)
            option_spread += sc
            option_comm += cm
            exit_date = pd.Timestamp(day)
            break

    option_pnl = entry_mid + exit_mid          # mid-to-mid, costs reported separately
    total_costs = option_spread + option_comm + hedge_slippage
    hedge_pnl = cash.balance - cash.interest + total_costs - option_pnl
    return {
        "exit_date": exit_date, "days_held": len(daily), "structures": structures,
        "option_pnl": option_pnl, "hedge_pnl": hedge_pnl,
        "gross_pnl": option_pnl + hedge_pnl,
        "financing": cash.interest, "option_spread_cost": option_spread,
        "option_commissions": option_comm, "hedge_slippage": hedge_slippage,
        "total_costs": total_costs, "net_pnl": cash.balance,
        "reconciliation_error": cash.balance - (option_pnl + hedge_pnl + cash.interest - total_costs),
        "shares_traded": shares_traded, "stale_vol_days": stale_days,
        "max_residual_delta": float(np.nanmax(np.abs([d["residual_delta"] for d in daily]))) if daily else 0.0,
        "daily": pd.DataFrame(daily),
    }
