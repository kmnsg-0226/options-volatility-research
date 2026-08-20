"""Point-in-time exposure rules for the canonical variance-carry strategy.

The V5 engine established that SPY carries a genuine positive variance premium
whose payoff is violently negatively skewed. This module holds the small set of
*ex-ante* rules V6 tests against that problem: how large a position to take, and
whether to take one at all.

Two design constraints run through everything here:

* **Causality.** Every reference level is estimated from observations strictly
  before the decision date. A scaler that peeks at its own outcome would
  manufacture exactly the result this phase is trying to test for.
* **Exposure honesty.** Any adaptive rule is normalised so its *average*
  development exposure is one, and is always reported beside a flat control at
  the same average. Reducing risk by holding less is not a finding.

Because the canonical engine uses fractional contracts, every cash flow in a
trade is exactly linear in the variance notional, so scaling a trade's P&L by an
exposure multiplier is exact rather than an approximation.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FLOOR, CAP = 0.25, 1.50


def expanding_reference(values: pd.Series, minimum_observations: int = 24) -> pd.Series:
    """Expanding median of strictly prior observations."""

    return values.shift(1).expanding(min_periods=minimum_observations).median().rename("reference")


def expanding_error_scale(
    errors: pd.Series,
    observable_from: pd.Series,
    minimum_observations: int = 12,
) -> pd.Series:
    """Causal dispersion of past forecast errors.

    ``observable_from`` gives the date each error becomes known — the contract's
    expiry, not its entry. Monthly entries overlap the previous contract by a few
    days, so keying off entry dates would leak the outcome of a trade that is
    still open.
    """

    known = pd.DataFrame({"error": errors, "from": observable_from}).dropna()
    out = pd.Series(np.nan, index=errors.index, name="error_scale")
    for date in errors.index:
        past = known.loc[known["from"] < date, "error"]
        if len(past) >= minimum_observations:
            out.loc[date] = float(past.std(ddof=1))
    return out


def inverse_variance_scale(
    fair_strike: pd.Series, floor: float = FLOOR, cap: float = CAP
) -> pd.Series:
    """A1: exposure inversely proportional to the entry variance level."""

    ref = expanding_reference(fair_strike)
    return (ref / fair_strike.replace(0, np.nan)).clip(floor, cap).rename("scale")


def inverse_vol_scale(
    fair_strike: pd.Series, floor: float = FLOOR, cap: float = CAP
) -> pd.Series:
    """A2: exposure inversely proportional to entry volatility (square root)."""

    ref = expanding_reference(fair_strike)
    return np.sqrt(ref / fair_strike.replace(0, np.nan)).clip(floor, cap).rename("scale")


def expected_vrp(fair_strike: pd.Series, expected_variance: pd.Series) -> pd.Series:
    """Entry-time expected premium, both legs in annualised variance units."""

    return (fair_strike - expected_variance).rename("evrp")


def participate_if_positive(evrp: pd.Series) -> pd.Series:
    """C1: take the trade only when the expected premium is positive."""

    return (evrp > 0).astype(float).rename("scale")


def participate_with_buffer(
    evrp: pd.Series, error_scale: pd.Series, coefficient: float = 0.5
) -> pd.Series:
    """C2: require the premium to clear a multiple of the forecast-error scale."""

    threshold = coefficient * error_scale
    return ((evrp > threshold) & threshold.notna()).astype(float).rename("scale")


def continuous_premium_scale(
    evrp: pd.Series,
    error_scale: pd.Series,
    floor: float = 0.0,
    cap: float = CAP,
) -> pd.Series:
    """C3: exposure rising monotonically with premium measured in error units."""

    ratio = (evrp / error_scale.replace(0, np.nan)).fillna(0.0)
    return ratio.clip(floor, cap).rename("scale")


def term_structure_scale(
    ratio_short_long: pd.Series,
    minimum_observations: int = 24,
    sensitivity: float = 0.25,
    floor: float = 0.25,
    cap: float = 1.0,
) -> pd.Series:
    """D: cut exposure as front variance becomes rich relative to longer dated.

    The z-score is expanding and excludes the current observation. The cap of one
    prevents a calm curve from levering the position up.
    """

    prior = ratio_short_long.shift(1).expanding(min_periods=minimum_observations)
    z = (ratio_short_long - prior.mean()) / prior.std(ddof=1).replace(0, np.nan)
    return (1.0 - sensitivity * z.fillna(0.0)).clip(floor, cap).rename("scale")


def carry_to_risk_scale(
    evrp: pd.Series,
    risk: pd.Series,
    minimum_observations: int = 24,
    floor: float = 0.0,
    cap: float = CAP,
) -> pd.Series:
    """F: exposure proportional to expected premium per unit of ex-ante risk."""

    ratio = evrp / risk.replace(0, np.nan)
    ref = expanding_reference(ratio, minimum_observations)
    return (ratio / ref.replace(0, np.nan)).fillna(0.0).clip(floor, cap).rename("scale")


def normalise_average_exposure(scale: pd.Series, target: float = 1.0) -> pd.Series:
    """Rescale so mean exposure equals ``target`` over the window supplied.

    Applied on development only; the resulting constant is frozen with the
    specification so the rule stays point-in-time out of sample.
    """

    mean = float(scale.mean())
    if not np.isfinite(mean) or mean <= 0:
        return scale
    return (scale * target / mean).rename("scale")


def flat_control(scale: pd.Series) -> pd.Series:
    """Constant exposure at the adaptive rule's own average."""

    return pd.Series(float(scale.mean()), index=scale.index, name="scale")


def apply_scale(trade_pnl: pd.DataFrame, scale: pd.Series, columns: list[str]) -> pd.DataFrame:
    """Scale a canonical trade ledger; exact because the engine is linear in N."""

    s = scale.reindex(trade_pnl.index).fillna(0.0)
    out = trade_pnl.copy()
    for column in columns:
        out[column] = trade_pnl[column] * s
    out["exposure_scale"] = s
    return out


def surface_state(
    strikes: np.ndarray,
    quotes: np.ndarray,
    delta_k: np.ndarray,
    forward: float,
    k0: float,
) -> dict[str, float]:
    """Where a model-free strip sources its variance across the surface.

    Each strike contributes ``dK/K**2 * Q(K)`` to the model-free integral, so the
    shares below describe which part of the surface is pricing the variance.

    The two ratio measures split at 2% out of the money rather than 5%: the call
    wing truncates near 1.04 forward on quiet days, and a 5% split leaves the
    denominator near zero, at which point the ratio measures how wide the strip
    happens to be instead of how asymmetric the surface is.

    Callers should treat the downside shares with care. They correlate strongly
    with how far the put wing extends, which in turn depends on how many deep
    puts held a non-zero bid that day — partly a quote-coverage property of the
    data rather than a market state.
    """

    c = np.asarray(delta_k, float) / np.asarray(strikes, float) ** 2 * np.asarray(quotes, float)
    total = float(c.sum())
    if total <= 0:
        raise ValueError("strip has no positive variance contribution")
    m = np.asarray(strikes, float) / forward
    down, up = c[m < 0.98].sum(), c[m > 1.02].sum()
    return {
        "put_share": float(c[np.asarray(strikes, float) < k0].sum() / total),
        "deep_down_share": float(c[m < 0.90].sum() / total),
        "skew_wedge": float((c[(m >= 0.85) & (m < 0.95)].sum() - c[(m > 1.05) & (m <= 1.15)].sum()) / total),
        "down_up_ratio": float(np.log(down / up)) if up > 0 and down > 0 else float("nan"),
        "strip_low_moneyness": float(m.min()),
        "strip_high_moneyness": float(m.max()),
    }
