"""Configuration for turning raw WRDS files into the research input panel.

Only the fields ``prepare_wrds_inputs`` actually reads. The maturity band and
the fallback rate shape which contracts are loaded and how a missing zero-curve
observation is filled; nothing here decides how a strategy trades, because
ingestion does not know about strategies.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IngestionConfig:
    """Maturity band and rate fallback used when building the option panel.

    The chain is loaded over a wider band than any strategy trades, so an open
    position stays markable as its own expiration approaches. ``min_dte`` and
    ``max_dte`` record the *selection* band for the data-quality report;
    ``exit_dte`` records the convention a downstream strategy is expected to
    use, and is likewise reported rather than enforced here.
    """

    min_dte: float = 21
    max_dte: float = 45
    exit_dte: float = 7
    risk_free_rate: float = 0.04
