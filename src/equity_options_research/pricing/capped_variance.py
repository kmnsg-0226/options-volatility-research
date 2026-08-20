"""Fair pricing of a capped realised-variance swap under calibrated Heston.

A capped variance swap pays the seller ``N (K_cap - min(RV, C))``. The cap is not
a discount: because the seller's downside is truncated, the fair strike drops,
and the drop is exactly the risk-neutral value of the tail that was given away,

    K_cap = K_var - E^Q[(RV - C)+]

which follows from the pathwise identity ``min(x, C) + (x - C)+ = x``. That
identity is used deliberately rather than pricing ``E^Q[min(RV, C)]`` directly:
``K_var`` is observable model-free from the listed strip, so anchoring to it
confines the model's influence to the one quantity that genuinely requires a
model — the value of the far tail of the realised-variance distribution.

Nothing here replicates the product with listed options. A capped realised
variance payoff is path-dependent and is *not* spanned by a static strip, so
these are model prices for a hypothetical OTC contract, not a tradable backtest.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from equity_options_research.pricing.heston import (
    HestonParams,
    expected_integrated_variance,
    realised_variance_from_paths,
    simulate_paths,
)


@dataclass(frozen=True)
class CappedVarianceQuote:
    """A fair capped strike with the Monte Carlo uncertainty attached to it."""

    multiplier: float
    cap: float
    fair_strike_uncapped_market: float
    fair_strike_model: float
    tail_value: float
    tail_value_stderr: float
    fair_strike_capped: float
    concession: float
    probability_cap_binds: float
    expected_rv: float
    expected_rv_stderr: float
    continuous_expected_variance: float
    monitoring_difference: float
    paths: int
    steps: int
    seed: int

    @property
    def confidence_interval(self) -> tuple[float, float]:
        half = 1.96 * self.tail_value_stderr
        return (self.fair_strike_capped - half, self.fair_strike_capped + half)

    def as_row(self) -> dict[str, float]:
        lo, hi = self.confidence_interval
        return {
            "cap_multiplier": self.multiplier, "cap_level": self.cap,
            "k_var_market": self.fair_strike_uncapped_market,
            "k_var_model_mc": self.fair_strike_model,
            "model_market_variance_basis": self.fair_strike_model - self.fair_strike_uncapped_market,
            "tail_value": self.tail_value, "tail_value_stderr": self.tail_value_stderr,
            "k_cap": self.fair_strike_capped, "k_cap_ci_low": lo, "k_cap_ci_high": hi,
            "concession": self.concession,
            "concession_fraction_of_strike": self.concession / self.fair_strike_uncapped_market,
            "prob_cap_binds": self.probability_cap_binds,
            "expected_rv_mc": self.expected_rv, "expected_rv_stderr": self.expected_rv_stderr,
            "continuous_expected_variance": self.continuous_expected_variance,
            "monitoring_difference": self.monitoring_difference,
            "paths": self.paths, "steps": self.steps, "seed": self.seed,
        }


def simulate_realised_variance(
    params: HestonParams, year_fraction: float, steps: int, paths: int, seed: int
) -> np.ndarray:
    """Annualised daily-monitored realised variance, one value per path.

    ``steps`` is the contract's actual number of daily observations, so the
    simulated payoff is monitored exactly as the historical one is.
    """

    returns = simulate_paths(params, year_fraction, steps, paths, seed)
    assert isinstance(returns, np.ndarray)
    return realised_variance_from_paths(returns, year_fraction)


def price_capped_variance(
    realised: np.ndarray,
    fair_strike_market: float,
    multiplier: float,
    params: HestonParams,
    year_fraction: float,
    paths: int,
    steps: int,
    seed: int,
) -> CappedVarianceQuote:
    """Fair capped strike for ``C = multiplier * K_var``.

    ``realised`` is reused across cap levels, which makes the comparison between
    2.0x, 2.5x and 3.0x a common-random-numbers comparison: their differences
    carry no independent simulation noise.
    """

    cap = multiplier * fair_strike_market
    excess = np.maximum(realised - cap, 0.0)
    tail = float(excess.mean())
    tail_se = float(excess.std(ddof=1) / np.sqrt(len(excess)))
    expected_rv = float(realised.mean())
    return CappedVarianceQuote(
        multiplier=multiplier, cap=cap,
        fair_strike_uncapped_market=fair_strike_market,
        fair_strike_model=expected_rv,
        tail_value=tail, tail_value_stderr=tail_se,
        fair_strike_capped=fair_strike_market - tail,
        concession=tail,
        probability_cap_binds=float((realised > cap).mean()),
        expected_rv=expected_rv,
        expected_rv_stderr=float(realised.std(ddof=1) / np.sqrt(len(realised))),
        continuous_expected_variance=expected_integrated_variance(year_fraction, params),
        monitoring_difference=expected_rv - expected_integrated_variance(year_fraction, params),
        paths=paths, steps=steps, seed=seed,
    )


def capped_payoff(
    realised_variance: float, fair_strike_capped: float, cap: float, notional: float
) -> float:
    """Seller's P&L on a capped variance swap: ``N (K_cap - min(RV, C))``."""

    return float(notional * (fair_strike_capped - min(realised_variance, cap)))


def uncapped_payoff(realised_variance: float, fair_strike: float, notional: float) -> float:
    """Seller's P&L on the plain variance swap: ``N (K_var - RV)``."""

    return float(notional * (fair_strike - realised_variance))


def hypothetical_capped_payoff(
    realised_variance: float, fair_strike_uncapped: float, cap: float, notional: float
) -> float:
    """Diagnostic only: the uncapped strike retained alongside a capped payoff.

    This is what a naive "just cap the losses" calculation produces. It is not a
    traded contract — it hands the seller the tail protection without charging
    for it — and exists here solely so the memo can quantify how much of that
    apparent benefit disappears once the strike concession is paid.
    """

    return float(notional * (fair_strike_uncapped - min(realised_variance, cap)))
