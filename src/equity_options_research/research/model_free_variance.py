"""CBOE-style model-free implied variance from a discrete option chain.

The at-the-money implied variance used by the earlier phases prices a single
strike and therefore ignores the equity skew.  The variance-swap rate that the
variance-risk-premium literature is defined on integrates option prices across
*all* strikes, which is what this module computes:

    sigma^2(T) = (2/T) * sum_i (dK_i / K_i^2) * exp(rT) * Q(K_i)
                 - (1/T) * (F/K0 - 1)^2

``Q(K)`` is the midpoint of the out-of-the-money option at strike ``K`` -- puts
below ``K0``, calls above it, and the average of the two at ``K0`` itself.  The
forward is recovered by put-call parity at the strike where the call and put
midpoints are closest, exactly as in the CBOE VIX white paper.

The zero-bid truncation rule is applied on each wing: strikes are walked outward
from ``K0`` and the wing is cut once two consecutive strikes quote a zero bid.
Every rejection is reported rather than silently dropped, because the number of
usable strikes is itself a data-quality signal.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class StripSelection:
    """The strikes the estimator integrates over, and their integration weights.

    Trading the premium requires the *same* strikes the measurement used, so the
    selection is exposed here rather than re-derived by the execution layer.
    """

    strikes: np.ndarray
    rights: np.ndarray          # "put", "call", or "both" at K0
    quotes: np.ndarray          # the Q(K) midpoints entering the sum
    bids: np.ndarray
    asks: np.ndarray
    delta_k: np.ndarray
    forward: float
    k0: float
    year_fraction: float
    rate: float


@dataclass(frozen=True)
class VarianceResult:
    """Outcome of one strike integration, successful or not."""

    success: bool
    variance: float | None
    forward: float | None
    k0: float | None
    strikes_used: int
    put_strikes: int
    call_strikes: int
    lowest_strike: float | None
    highest_strike: float | None
    correction_term: float | None
    reason: str | None = None
    strip: StripSelection | None = None


def _truncate_zero_bids(bids: np.ndarray) -> int:
    """Return how many leading strikes survive the two-consecutive-zero rule."""

    zeros = 0
    for position, bid in enumerate(bids):
        if bid <= 0:
            zeros += 1
            if zeros >= 2:
                return max(position - 1, 0)
        else:
            zeros = 0
    return len(bids)


def strike_intervals(strikes: np.ndarray) -> np.ndarray:
    """Central differences between neighbouring strikes, one-sided at the ends."""

    if len(strikes) == 1:
        return np.array([strikes[0]])
    intervals = np.empty(len(strikes))
    intervals[1:-1] = (strikes[2:] - strikes[:-2]) / 2.0
    intervals[0] = strikes[1] - strikes[0]
    intervals[-1] = strikes[-1] - strikes[-2]
    return intervals


def model_free_variance(
    strikes: np.ndarray,
    call_bid: np.ndarray,
    call_ask: np.ndarray,
    put_bid: np.ndarray,
    put_ask: np.ndarray,
    rate: float,
    year_fraction: float,
    minimum_strikes: int = 8,
    max_relative_spread: float | None = None,
) -> VarianceResult:
    """Integrate an option chain into a variance-swap rate for one expiry."""

    if year_fraction <= 0:
        return VarianceResult(False, None, None, None, 0, 0, 0, None, None, None, "nonpositive_maturity")

    order = np.argsort(strikes)
    strikes = np.asarray(strikes, dtype=float)[order]
    call_bid, call_ask = np.asarray(call_bid, float)[order], np.asarray(call_ask, float)[order]
    put_bid, put_ask = np.asarray(put_bid, float)[order], np.asarray(put_ask, float)[order]

    if len(np.unique(strikes)) != len(strikes):
        return VarianceResult(False, None, None, None, 0, 0, 0, None, None, None, "duplicate_strikes")

    call_mid = (call_bid + call_ask) / 2.0
    put_mid = (put_bid + put_ask) / 2.0
    tradeable = (
        np.isfinite(call_mid) & np.isfinite(put_mid)
        & (call_ask > call_bid) & (put_ask > put_bid)
        & (call_bid >= 0) & (put_bid >= 0)
    )
    if max_relative_spread is not None:
        with np.errstate(divide="ignore", invalid="ignore"):
            call_ok = np.where(call_mid > 0, (call_ask - call_bid) / call_mid, np.inf) <= max_relative_spread
            put_ok = np.where(put_mid > 0, (put_ask - put_bid) / put_mid, np.inf) <= max_relative_spread
        tradeable &= call_ok | put_ok

    # the forward needs a strike with a usable call AND put on both legs
    parity = tradeable & (call_ask > call_bid) & (put_ask > put_bid)
    if parity.sum() == 0:
        return VarianceResult(False, None, None, None, 0, 0, 0, None, None, None, "no_parity_pair")

    difference = np.where(parity, np.abs(call_mid - put_mid), np.inf)
    anchor = int(np.argmin(difference))
    discount = float(np.exp(rate * year_fraction))
    forward = float(strikes[anchor] + discount * (call_mid[anchor] - put_mid[anchor]))
    if not np.isfinite(forward) or forward <= 0:
        return VarianceResult(False, None, None, None, 0, 0, 0, None, None, None, "invalid_forward")

    at_or_below = strikes[strikes <= forward]
    if at_or_below.size == 0:
        return VarianceResult(False, None, forward, None, 0, 0, 0, None, None, None, "no_strike_below_forward")
    k0 = float(at_or_below.max())
    k0_index = int(np.where(strikes == k0)[0][0])

    # walk outward from K0, cutting each wing on two consecutive zero bids
    put_side = np.arange(k0_index - 1, -1, -1)
    call_side = np.arange(k0_index + 1, len(strikes))
    put_keep = put_side[: _truncate_zero_bids(put_bid[put_side])]
    call_keep = call_side[: _truncate_zero_bids(call_bid[call_side])]
    put_keep = put_keep[tradeable[put_keep]]
    call_keep = call_keep[tradeable[call_keep]]

    if not tradeable[k0_index]:
        return VarianceResult(False, None, forward, k0, 0, 0, 0, None, None, None, "k0_not_tradeable")

    selected = np.sort(np.concatenate([put_keep, [k0_index], call_keep]))
    if len(selected) < minimum_strikes:
        return VarianceResult(
            False, None, forward, k0, len(selected), len(put_keep), len(call_keep),
            float(strikes[selected].min()), float(strikes[selected].max()), None,
            "insufficient_strike_coverage",
        )

    quotes = np.empty(len(selected))
    for position, index in enumerate(selected):
        if index < k0_index:
            quotes[position] = put_mid[index]
        elif index > k0_index:
            quotes[position] = call_mid[index]
        else:
            quotes[position] = (call_mid[index] + put_mid[index]) / 2.0
    if not np.isfinite(quotes).all() or (quotes < 0).any():
        return VarianceResult(False, None, forward, k0, len(selected), len(put_keep), len(call_keep),
                              None, None, None, "invalid_quote_in_sum")

    used = strikes[selected]
    intervals = strike_intervals(used)
    rights = np.where(selected < k0_index, "put", np.where(selected > k0_index, "call", "both"))
    strip_bids = np.where(selected < k0_index, put_bid[selected],
                          np.where(selected > k0_index, call_bid[selected],
                                   (call_bid[selected] + put_bid[selected]) / 2.0))
    strip_asks = np.where(selected < k0_index, put_ask[selected],
                          np.where(selected > k0_index, call_ask[selected],
                                   (call_ask[selected] + put_ask[selected]) / 2.0))
    contribution = float(np.sum(intervals / used**2 * discount * quotes))
    correction = float((forward / k0 - 1.0) ** 2)
    variance = 2.0 / year_fraction * contribution - correction / year_fraction
    if not np.isfinite(variance) or variance <= 0:
        return VarianceResult(False, None, forward, k0, len(selected), len(put_keep), len(call_keep),
                              float(used.min()), float(used.max()), correction, "nonpositive_variance")
    return VarianceResult(
        True, float(variance), forward, k0, len(selected), len(put_keep), len(call_keep),
        float(used.min()), float(used.max()), correction, None,
        StripSelection(used, rights, quotes, strip_bids, strip_asks, intervals,
                       forward, k0, year_fraction, rate),
    )


def interpolate_total_variance(
    near_variance: float,
    near_year_fraction: float,
    next_variance: float,
    next_year_fraction: float,
    target_year_fraction: float,
) -> float:
    """Interpolate in TOTAL variance, then re-express as a variance rate.

    Interpolating the variance *rate* would distort the term structure; the
    quantity that is linear in maturity is ``sigma^2 * T``.
    """

    if not near_year_fraction < next_year_fraction:
        raise ValueError("near maturity must be shorter than next maturity")
    if near_variance <= 0 or next_variance <= 0 or target_year_fraction <= 0:
        raise ValueError("variances and target maturity must be positive")
    near_total = near_variance * near_year_fraction
    next_total = next_variance * next_year_fraction
    weight = (next_year_fraction - target_year_fraction) / (next_year_fraction - near_year_fraction)
    total = weight * near_total + (1.0 - weight) * next_total
    return float(total / target_year_fraction)


def chain_variance_frame(
    options: pd.DataFrame,
    rates: pd.Series | None = None,
    fallback_rate: float = 0.04,
    minimum_strikes: int = 8,
    minimum_dte: float = 1.0,
) -> pd.DataFrame:
    """Compute the variance-swap rate for every (quote date, expiry) pair.

    Expiration-day chains are excluded rather than integrated: the variance
    *rate* carries a ``2/T`` factor, so as maturity approaches zero the estimate
    diverges without describing anything economically meaningful.
    """

    records: list[dict[str, object]] = []
    for (date, expiration), group in options.groupby(["quote_date", "expiration"], sort=True):
        dte = float(group["dte"].iloc[0])
        if dte < minimum_dte:
            records.append({
                "quote_date": date, "expiration": expiration, "dte": dte,
                "year_fraction": dte / 365.0, "rate": np.nan, "success": False,
                "model_free_variance": None, "forward": None, "k0": None,
                "strikes_used": 0, "put_strikes": 0, "call_strikes": 0,
                "lowest_strike": None, "highest_strike": None, "correction_term": None,
                "reason": "expiration_day", "available_strikes": len(group),
            })
            continue
        year_fraction = max(dte / 365.0, 1e-8)
        if rates is not None and (date, expiration) in rates.index:
            rate = float(rates.loc[(date, expiration)])
        elif "risk_free_rate" in group.columns and np.isfinite(group["risk_free_rate"].iloc[0]):
            rate = float(group["risk_free_rate"].iloc[0])
        else:
            rate = fallback_rate
        result = model_free_variance(
            group["strike"].to_numpy(float),
            group["call_bid"].to_numpy(float), group["call_ask"].to_numpy(float),
            group["put_bid"].to_numpy(float), group["put_ask"].to_numpy(float),
            rate, year_fraction, minimum_strikes=minimum_strikes,
        )
        records.append({
            "quote_date": date, "expiration": expiration, "dte": dte,
            "year_fraction": year_fraction, "rate": rate,
            "success": result.success, "model_free_variance": result.variance,
            "forward": result.forward, "k0": result.k0,
            "strikes_used": result.strikes_used, "put_strikes": result.put_strikes,
            "call_strikes": result.call_strikes, "lowest_strike": result.lowest_strike,
            "highest_strike": result.highest_strike, "correction_term": result.correction_term,
            "reason": result.reason, "available_strikes": len(group),
        })
    return pd.DataFrame(records)
