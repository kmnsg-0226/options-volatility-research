"""Guardrail quarantining the final test period during strategy development.

The 2023-01-01 onward window is locked. Any attempt to read strategy performance
from it raises unless the caller deliberately unlocks it, so a development script
cannot rank, plot or summarise the locked period by accident. Unlocking is an
explicit, auditable act rather than a default.

The guard deliberately refuses silently-truncating behaviour: asking for locked
data returns an error, not a quietly shortened frame, because a silent truncation
is exactly how a leak survives review.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

FINAL_TEST_START = pd.Timestamp("2023-01-01")


class FinalTestLockError(RuntimeError):
    """Raised when locked final-test data is requested without an unlock."""


@dataclass
class FinalTestGuard:
    """Gatekeeper for development access to the quarantined window."""

    final_test_start: pd.Timestamp = FINAL_TEST_START
    allow_final_test: bool = False
    _unlock_reason: str | None = field(default=None, repr=False)

    def unlock(self, reason: str) -> None:
        """Deliberately open the final test window, recording why."""

        if not reason or not reason.strip():
            raise ValueError("unlocking requires a stated reason")
        self.allow_final_test = True
        self._unlock_reason = reason.strip()

    @property
    def unlock_reason(self) -> str | None:
        return self._unlock_reason

    def development_frame(self, frame: pd.DataFrame, date_column: str | None = None) -> pd.DataFrame:
        """Return only pre-lock rows, for use in development."""

        stamps = self._stamps(frame, date_column)
        return frame.loc[stamps < self.final_test_start]

    def check_development_only(self, frame: pd.DataFrame, date_column: str | None = None) -> None:
        """Assert a frame destined for a development artifact carries no locked rows."""

        stamps = self._stamps(frame, date_column)
        if len(stamps) and stamps.max() >= self.final_test_start:
            raise FinalTestLockError(
                f"development output contains dates on or after "
                f"{self.final_test_start.date()}; maximum found {stamps.max().date()}"
            )

    def final_test_frame(self, frame: pd.DataFrame, date_column: str | None = None) -> pd.DataFrame:
        """Return locked-window rows; refuses while the guard is locked."""

        if not self.allow_final_test:
            raise FinalTestLockError(
                "final test period is locked; freeze the specification and call "
                "unlock(reason) before requesting these results"
            )
        stamps = self._stamps(frame, date_column)
        return frame.loc[stamps >= self.final_test_start]

    def _stamps(self, frame: pd.DataFrame, date_column: str | None) -> pd.DatetimeIndex:
        if date_column is not None:
            return pd.DatetimeIndex(pd.to_datetime(frame[date_column]))
        return pd.DatetimeIndex(pd.to_datetime(frame.index))
