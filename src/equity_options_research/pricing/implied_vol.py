"""Structured implied-volatility solvers."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite

from scipy.optimize import brentq

from .black_scholes import price
from .bounds import validate_market_price
from .greeks import vega


@dataclass(frozen=True)
class IVResult:
    success: bool
    volatility: float | None
    reason: str | None
    repriced: float | None
    absolute_error: float | None
    relative_error: float | None
    iterations: int | None = None


def implied_volatility(right: str, market_price: float, S: float, K: float, T: float, r: float, q: float, lower: float = 1e-6, upper: float = 5.0, xtol: float = 1e-10) -> IVResult:
    if not all(isfinite(x) for x in (market_price, S, K, T, r, q)):
        return IVResult(False, None, "nonfinite_input", None, None, None)
    if T <= 0:
        return IVResult(False, None, "nonpositive_time", None, None, None)
    if lower <= 0 or upper <= lower:
        return IVResult(False, None, "invalid_bracket", None, None, None)
    valid, reason = validate_market_price(right, market_price, S, K, T, r, q)
    if not valid:
        return IVResult(False, None, reason, None, None, None)

    def objective(sigma: float) -> float:
        return price(right, S, K, T, r, q, sigma) - market_price

    f_lower, f_upper = objective(lower), objective(upper)
    if f_lower == 0:
        sigma = lower
    elif f_upper == 0:
        sigma = upper
    elif f_lower * f_upper > 0:
        return IVResult(False, None, "root_not_bracketed", None, None, None)
    else:
        try:
            sigma, result = brentq(objective, lower, upper, xtol=xtol, full_output=True)
            iterations = result.iterations
        except (ValueError, RuntimeError) as exc:
            return IVResult(False, None, f"solver_failure:{type(exc).__name__}", None, None, None)
        repriced = price(right, S, K, T, r, q, sigma)
        error = abs(repriced - market_price)
        return IVResult(True, sigma, None, repriced, error, error / max(abs(market_price), 1e-12), iterations)
    repriced = price(right, S, K, T, r, q, sigma)
    error = abs(repriced - market_price)
    return IVResult(True, sigma, None, repriced, error, error / max(abs(market_price), 1e-12), 0)


def implied_volatility_newton(right: str, market_price: float, S: float, K: float, T: float, r: float, q: float, initial: float = 0.2, max_iterations: int = 50, tolerance: float = 1e-8) -> IVResult:
    """Optional comparison solver; Brent remains the production default."""
    sigma = initial
    for iteration in range(1, max_iterations + 1):
        model = price(right, S, K, T, r, q, sigma)
        option_vega = vega(S, K, T, r, q, sigma)
        if option_vega < 1e-12:
            return IVResult(False, None, "zero_vega", model, abs(model - market_price), None, iteration)
        sigma -= (model - market_price) / option_vega
        if sigma <= 0 or not isfinite(sigma):
            return IVResult(False, None, "newton_left_domain", None, None, None, iteration)
        if abs(model - market_price) <= tolerance:
            repriced = price(right, S, K, T, r, q, sigma)
            error = abs(repriced - market_price)
            return IVResult(True, sigma, None, repriced, error, error / max(abs(market_price), 1e-12), iteration)
    return IVResult(False, None, "max_iterations", None, None, None, max_iterations)

