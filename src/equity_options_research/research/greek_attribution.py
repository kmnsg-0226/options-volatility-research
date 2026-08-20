"""Black-Scholes P&L attribution for an option book.

This does not replace the canonical variance hedge and is not used to trade.
The canonical engine hedges a variance swap with the model-free log-contract
identity, which is a statement about the *whole* strip and needs no volatility
model. Greeks answer a different question: given that the book moved, which
local risk factor moved it. That is a diagnostic, and a Black-Scholes one is
appropriate for it even though Black-Scholes is the wrong model for the payoff.

A one-day move is decomposed as

    dV ~= delta dS + 0.5 gamma dS^2 + vega dSigma + theta dt

with each leg's own implied volatility supplying ``dSigma``. Vanna and volga are
available as diagnostics for days when the four-Greek form leaves a large
residual; they are not part of the headline decomposition.

Sign convention: every function here returns the P&L of the *position* as held.
A short strip carries negative quantities, so its theta contribution is positive
and its gamma contribution is negative, which is the economically intuitive
reading for a variance seller.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import norm

from equity_options_research.pricing.black_scholes import d1_d2, price
from equity_options_research.pricing.greeks import all_greeks
from equity_options_research.pricing.implied_vol import implied_volatility

DAYS_PER_YEAR = 365.0
GREEK_COLUMNS = ["delta_pnl", "gamma_pnl", "vega_pnl", "theta_pnl"]
# A quote worth less than this carries no usable volatility information: the
# Black-Scholes price is flat in sigma out there, so a root finder will happily
# return an arbitrary value that reprices to within its own tolerance.
MIN_INVERTIBLE_PRICE = 1e-4
MAX_REPRICE_RELATIVE_ERROR = 1e-3


@dataclass(frozen=True)
class Leg:
    """One option position. ``quantity`` is signed: negative is short."""

    right: str
    strike: float
    quantity: float
    multiplier: int = 100


def vanna(S: float, K: float, T: float, r: float, q: float, sigma: float) -> float:
    """d(delta)/d(sigma) — how the hedge ratio drifts when volatility moves."""

    if T <= 0 or sigma <= 0:
        return 0.0
    d1, d2 = d1_d2(S, K, T, r, q, sigma)
    return float(-np.exp(-q * T) * norm.pdf(d1) * d2 / sigma)


def volga(S: float, K: float, T: float, r: float, q: float, sigma: float) -> float:
    """d(vega)/d(sigma) — the convexity of value in volatility."""

    if T <= 0 or sigma <= 0:
        return 0.0
    d1, d2 = d1_d2(S, K, T, r, q, sigma)
    return float(S * np.exp(-q * T) * norm.pdf(d1) * np.sqrt(T) * d1 * d2 / sigma)


def leg_state(
    leg: Leg, spot: float, year_fraction: float, rate: float, dividend: float, market_price: float
) -> dict[str, float]:
    """Point-in-time value, implied volatility and Greeks for one leg.

    Uses only same-date inputs: the quote, the spot, the rate and the remaining
    maturity. Nothing from later in the trade enters.
    """

    if market_price < MIN_INVERTIBLE_PRICE:
        sigma = np.nan
    else:
        iv = implied_volatility(leg.right, market_price, spot, leg.strike, year_fraction, rate, dividend)
        reprices = iv.relative_error is None or iv.relative_error < MAX_REPRICE_RELATIVE_ERROR
        sigma = float(iv.volatility) if iv.success and iv.volatility is not None and reprices else np.nan
    out = {"implied_vol": sigma, "market_price": market_price, "quantity": leg.quantity,
           "strike": leg.strike, "year_fraction": year_fraction}
    if not np.isfinite(sigma) or year_fraction <= 0:
        out.update({k: np.nan for k in ("model_price", "delta", "gamma", "vega", "theta", "vanna", "volga")})
        return out
    g = all_greeks(leg.right, spot, leg.strike, year_fraction, rate, dividend, sigma)
    out.update({"model_price": price(leg.right, spot, leg.strike, year_fraction, rate, dividend, sigma), **g,
                "vanna": vanna(spot, leg.strike, year_fraction, rate, dividend, sigma),
                "volga": volga(spot, leg.strike, year_fraction, rate, dividend, sigma)})
    return out


def second_order_pnl(
    state: pd.DataFrame,
    spot_change: float,
    vol_change: pd.Series | np.ndarray,
    time_change_days: float,
    include_cross_terms: bool = False,
) -> pd.DataFrame:
    """Attribute a one-day move across legs.

    ``state`` holds the Greeks at the *start* of the interval, so the
    decomposition is a forward-looking Taylor expansion rather than a fit.
    """

    q = state["quantity"].to_numpy(float) * state.get("multiplier", 100)
    dt = time_change_days / DAYS_PER_YEAR
    dv = np.asarray(vol_change, float)
    out = pd.DataFrame(index=state.index)
    out["delta_pnl"] = q * state["delta"].to_numpy(float) * spot_change
    out["gamma_pnl"] = 0.5 * q * state["gamma"].to_numpy(float) * spot_change**2
    out["vega_pnl"] = q * state["vega"].to_numpy(float) * dv
    out["theta_pnl"] = q * state["theta"].to_numpy(float) * dt
    if include_cross_terms:
        out["vanna_pnl"] = q * state["vanna"].to_numpy(float) * spot_change * dv
        out["volga_pnl"] = 0.5 * q * state["volga"].to_numpy(float) * dv**2
    out["approx_pnl"] = out[[c for c in out.columns if c.endswith("_pnl")]].sum(axis=1)
    return out


def attribution_quality(actual: pd.Series, approximated: pd.Series) -> dict[str, float]:
    """How much of the realised option P&L the local expansion accounts for."""

    a, b = pd.Series(actual).astype(float), pd.Series(approximated).astype(float)
    ok = a.notna() & b.notna()
    a, b = a[ok], b[ok]
    if len(a) < 3:
        return {"n": float(len(a)), "correlation": np.nan, "rmse": np.nan, "mae": np.nan,
                "explained_variance": np.nan, "mean_residual": np.nan}
    residual = a - b
    return {
        "n": float(len(a)),
        "correlation": float(a.corr(b)),
        "rmse": float(np.sqrt((residual**2).mean())),
        "mae": float(residual.abs().mean()),
        # share of the realised variation the expansion reproduces; negative means
        # the approximation is worse than predicting the mean
        "explained_variance": float(1.0 - residual.var(ddof=0) / a.var(ddof=0)) if a.var(ddof=0) > 0 else np.nan,
        "mean_residual": float(residual.mean()),
        "residual_skew": float(residual.skew()),
        "worst_residual": float(residual.abs().max()),
    }
