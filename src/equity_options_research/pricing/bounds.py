"""European no-arbitrage price bounds and put-call parity diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from math import exp


def european_bounds(right: str, S: float, K: float, T: float, r: float, q: float) -> tuple[float, float]:
    if S <= 0 or K <= 0 or T < 0:
        raise ValueError("S/K must be positive and T non-negative")
    discounted_spot = S * exp(-q * T)
    discounted_strike = K * exp(-r * T)
    if right.lower() in {"c", "call"}:
        return max(0.0, discounted_spot - discounted_strike), discounted_spot
    if right.lower() in {"p", "put"}:
        return max(0.0, discounted_strike - discounted_spot), discounted_strike
    raise ValueError("invalid option right")


@dataclass(frozen=True)
class ParityDiagnostic:
    observed_difference: float
    theoretical_difference: float
    residual: float
    within_tolerance: bool


def put_call_parity(call: float, put: float, S: float, K: float, T: float, r: float, q: float, tolerance: float = 0.05) -> ParityDiagnostic:
    observed = call - put
    theoretical = S * exp(-q * T) - K * exp(-r * T)
    residual = observed - theoretical
    return ParityDiagnostic(observed, theoretical, residual, abs(residual) <= tolerance)


def validate_market_price(right: str, market_price: float, S: float, K: float, T: float, r: float, q: float, tolerance: float = 1e-10) -> tuple[bool, str | None]:
    if not (market_price >= 0):
        return False, "negative_or_nonfinite_price"
    lower, upper = european_bounds(right, S, K, T, r, q)
    if market_price < lower - tolerance:
        return False, "below_no_arbitrage_lower_bound"
    if market_price > upper + tolerance:
        return False, "above_no_arbitrage_upper_bound"
    return True, None

