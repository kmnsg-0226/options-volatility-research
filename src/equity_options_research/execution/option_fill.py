from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class OptionFill:
    price: float
    midpoint: float
    spread: float
    execution_cost_per_share: float


def option_fill(bid: float, ask: float, side: str, execution_lambda: float = 0.75) -> OptionFill:
    if bid < 0 or ask <= bid:
        raise ValueError("quote must have bid >= 0 and ask > bid")
    if not 0 <= execution_lambda <= 1:
        raise ValueError("execution_lambda must be in [0, 1]")
    midpoint, spread = (bid + ask) / 2, ask - bid
    half_cost = execution_lambda * spread / 2
    if side == "buy":
        return OptionFill(midpoint + half_cost, midpoint, spread, half_cost)
    if side == "sell":
        return OptionFill(midpoint - half_cost, midpoint, spread, half_cost)
    raise ValueError("side must be buy or sell")


def delayed_rows(frame: pd.DataFrame, bars: int = 1) -> pd.DataFrame:
    """Shift execution data backward so a decision at t sees its fill at t+bars."""
    if bars < 1:
        raise ValueError("at least one bar of delay is required for realistic execution")
    return frame.shift(-bars)
