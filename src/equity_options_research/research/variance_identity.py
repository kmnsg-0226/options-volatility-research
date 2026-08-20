"""The log-contract identity that makes variance replication work.

Everything a variance swap needs follows from one algebraic fact,

    [log S]_T = 2 * integral(dS_t / S_t) - 2 * log(S_T / S_0)

which says realised variance is a *static* short log contract plus a *dynamic*
share position. This module owns that identity and nothing else: no strikes, no
quotes, no execution. ``canonical_variance_engine`` imports ``hedge_shares``
from here rather than restating the formula, so the hedge has exactly one
definition in the codebase.

The identity is exact in continuous time. Sampled discretely it leaves a signed
third-order remainder, since per interval

    2[(e^x - 1) - x] = x^2 + x^3/3 + O(x^4)

so down moves under-deliver variance and up moves over-deliver it.
``discretisation_residual`` measures exactly that gap.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

__all__ = [
    "hedge_shares",
    "dynamic_leg_gain",
    "log_contract_gain",
    "reconstructed_variance",
    "discretisation_residual",
    "hedge_pnl_from_path",
    "theoretical_hedge_path",
]


def hedge_shares(
    notional: float,
    year_fraction: float,
    forward: float,
    spot: float | np.ndarray | pd.Series,
) -> np.ndarray:
    """Share position a SHORT variance replication must hold: ``N (2/T)(1/F - 1/S)``.

    Model-free by construction. It needs no implied volatility, no dividend
    assumption and no option Greeks — which is precisely why it is not the same
    object as the aggregate Black-Scholes delta of an option strip.
    """

    if year_fraction <= 0:
        raise ValueError("year_fraction must be positive")
    if forward <= 0:
        raise ValueError("forward must be positive")
    return notional * (2.0 / year_fraction) * (1.0 / forward - 1.0 / np.asarray(spot, dtype=float))


def dynamic_leg_gain(spot_path: np.ndarray) -> float:
    """Discrete analogue of ``2 * integral(dS/S)``: ``2 * sum(dS_i / S_{i-1})``."""

    s = np.asarray(spot_path, dtype=float)
    if s.size < 2:
        return 0.0
    return float(2.0 * np.sum(np.diff(s) / s[:-1]))


def log_contract_gain(spot_path: np.ndarray) -> float:
    """The ``-2 log(S_T / S_0)`` leg — the part a static option strip replicates."""

    s = np.asarray(spot_path, dtype=float)
    if s.size < 2:
        return 0.0
    return float(-2.0 * np.log(s[-1] / s[0]))


def reconstructed_variance(spot_path: np.ndarray, year_fraction: float) -> float:
    """Annualised variance the identity delivers on a discrete path.

    Annualised by the contract's own ``year_fraction``, matching
    ``canonical_variance_engine.realised_variance`` so the two are directly
    comparable.
    """

    if year_fraction <= 0:
        raise ValueError("year_fraction must be positive")
    return (dynamic_leg_gain(spot_path) + log_contract_gain(spot_path)) / year_fraction


def discretisation_residual(spot_path: np.ndarray) -> float:
    """Signed third-and-higher-order gap between the identity and squared returns.

    Returns ``sum(2[(e^x - 1) - x] - x^2)``. Negative for a path dominated by
    down moves, positive for one dominated by up moves.
    """

    s = np.asarray(spot_path, dtype=float)
    if s.size < 2:
        return 0.0
    x = np.log(s[1:] / s[:-1])
    return float(np.sum(2.0 * (np.expm1(x) - x) - x**2))


def hedge_pnl_from_path(shares: np.ndarray, spot_path: np.ndarray) -> float:
    """P&L of holding ``shares[i]`` across the step from ``spot[i]`` to ``spot[i+1]``.

    The final share count is deliberately ignored: there is no step after it.
    """

    h = np.asarray(shares, dtype=float)
    s = np.asarray(spot_path, dtype=float)
    if s.size < 2:
        return 0.0
    return float(np.sum(h[:-1] * np.diff(s)))


def theoretical_hedge_path(
    spot_path: np.ndarray, notional: float, year_fraction: float, forward: float
) -> tuple[np.ndarray, float, float]:
    """``(share path, hedge P&L, share turnover)`` for the identity hedge."""

    shares = np.asarray(hedge_shares(notional, year_fraction, forward, spot_path), dtype=float)
    pnl = hedge_pnl_from_path(shares, spot_path)
    turnover = float(np.abs(np.diff(np.concatenate(([0.0], shares, [0.0])))).sum())
    return shares, pnl, turnover
