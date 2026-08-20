"""Black--Scholes--Merton pricing with continuous dividend yield.

SPY options are American-style; this module deliberately uses European BSM as a
consistent IV/Greek convention. Callers should flag dividend-sensitive dates.
"""

from __future__ import annotations

from math import exp, log, sqrt

from scipy.stats import norm


def _validate(S: float, K: float, T: float, sigma: float) -> None:
    if S <= 0 or K <= 0:
        raise ValueError("S and K must be positive")
    if T < 0 or sigma < 0:
        raise ValueError("T and sigma must be non-negative")


def _deterministic_prices(S: float, K: float, T: float, r: float, q: float) -> tuple[float, float]:
    forward_pv = S * exp(-q * T) - K * exp(-r * T)
    return max(forward_pv, 0.0), max(-forward_pv, 0.0)


def d1_d2(S: float, K: float, T: float, r: float, q: float, sigma: float) -> tuple[float, float]:
    _validate(S, K, T, sigma)
    if T == 0 or sigma == 0:
        raise ValueError("d1/d2 are undefined at zero time or volatility")
    d1 = (log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * sqrt(T))
    return d1, d1 - sigma * sqrt(T)


def bsm_call_price(S: float, K: float, T: float, r: float, q: float, sigma: float) -> float:
    _validate(S, K, T, sigma)
    if T == 0:
        return max(S - K, 0.0)
    if sigma == 0:
        return _deterministic_prices(S, K, T, r, q)[0]
    d1, d2 = d1_d2(S, K, T, r, q, sigma)
    return float(S * exp(-q * T) * norm.cdf(d1) - K * exp(-r * T) * norm.cdf(d2))


def bsm_put_price(S: float, K: float, T: float, r: float, q: float, sigma: float) -> float:
    _validate(S, K, T, sigma)
    if T == 0:
        return max(K - S, 0.0)
    if sigma == 0:
        return _deterministic_prices(S, K, T, r, q)[1]
    d1, d2 = d1_d2(S, K, T, r, q, sigma)
    return float(K * exp(-r * T) * norm.cdf(-d2) - S * exp(-q * T) * norm.cdf(-d1))


def price(right: str, S: float, K: float, T: float, r: float, q: float, sigma: float) -> float:
    if right.lower() in {"c", "call"}:
        return bsm_call_price(S, K, T, r, q, sigma)
    if right.lower() in {"p", "put"}:
        return bsm_put_price(S, K, T, r, q, sigma)
    raise ValueError("right must be call/c or put/p")
