"""Analytic BSM Greeks, expressed per share.

Theta is calendar-time decay per year: d(option price)/d(calendar time), normally
negative for long options. Vega is the price change for a 1.00 volatility change.
"""

from __future__ import annotations

from math import exp, sqrt

from scipy.stats import norm

from .black_scholes import d1_d2


def _expiry_delta(S: float, K: float, right: str) -> float:
    if S == K:
        return 0.5 if right == "call" else -0.5
    if right == "call":
        return 1.0 if S > K else 0.0
    return -1.0 if S < K else 0.0


def call_delta(S: float, K: float, T: float, r: float, q: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0:
        return _expiry_delta(S * exp(-q * max(T, 0)), K * exp(-r * max(T, 0)), "call")
    d1, _ = d1_d2(S, K, T, r, q, sigma)
    return float(exp(-q * T) * norm.cdf(d1))


def put_delta(S: float, K: float, T: float, r: float, q: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0:
        return _expiry_delta(S * exp(-q * max(T, 0)), K * exp(-r * max(T, 0)), "put")
    d1, _ = d1_d2(S, K, T, r, q, sigma)
    return float(exp(-q * T) * (norm.cdf(d1) - 1.0))


def gamma(S: float, K: float, T: float, r: float, q: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0:
        return 0.0
    d1, _ = d1_d2(S, K, T, r, q, sigma)
    return float(exp(-q * T) * norm.pdf(d1) / (S * sigma * sqrt(T)))


def vega(S: float, K: float, T: float, r: float, q: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0:
        return 0.0
    d1, _ = d1_d2(S, K, T, r, q, sigma)
    return float(S * exp(-q * T) * norm.pdf(d1) * sqrt(T))


def call_theta(S: float, K: float, T: float, r: float, q: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0:
        return 0.0
    d1, d2 = d1_d2(S, K, T, r, q, sigma)
    diffusion = -S * exp(-q * T) * norm.pdf(d1) * sigma / (2 * sqrt(T))
    return float(
        diffusion
        - r * K * exp(-r * T) * norm.cdf(d2)
        + q * S * exp(-q * T) * norm.cdf(d1)
    )


def put_theta(S: float, K: float, T: float, r: float, q: float, sigma: float) -> float:
    if T <= 0 or sigma <= 0:
        return 0.0
    d1, d2 = d1_d2(S, K, T, r, q, sigma)
    diffusion = -S * exp(-q * T) * norm.pdf(d1) * sigma / (2 * sqrt(T))
    return float(
        diffusion
        + r * K * exp(-r * T) * norm.cdf(-d2)
        - q * S * exp(-q * T) * norm.cdf(-d1)
    )


def all_greeks(right: str, S: float, K: float, T: float, r: float, q: float, sigma: float) -> dict[str, float]:
    is_call = right.lower() in {"c", "call"}
    if not is_call and right.lower() not in {"p", "put"}:
        raise ValueError("invalid option right")
    return {
        "delta": (call_delta if is_call else put_delta)(S, K, T, r, q, sigma),
        "gamma": gamma(S, K, T, r, q, sigma),
        "vega": vega(S, K, T, r, q, sigma),
        "theta": (call_theta if is_call else put_theta)(S, K, T, r, q, sigma),
    }
