import pandas as pd
import pytest

from equity_options_research.research.final_test_guard import (
    FINAL_TEST_START,
    FinalTestGuard,
    FinalTestLockError,
)


def frame():
    idx = pd.to_datetime(["2021-06-01", "2022-12-31", "2023-01-02", "2025-08-01"])
    return pd.DataFrame({"net_pnl": [1.0, 2.0, 3.0, 4.0]}, index=idx)


def test_locked_by_default() -> None:
    assert FinalTestGuard().allow_final_test is False
    assert FINAL_TEST_START == pd.Timestamp("2023-01-01")


def test_development_frame_excludes_the_locked_window() -> None:
    out = FinalTestGuard().development_frame(frame())
    assert len(out) == 2 and out.index.max() < FINAL_TEST_START


def test_requesting_final_test_while_locked_raises() -> None:
    with pytest.raises(FinalTestLockError, match="locked"):
        FinalTestGuard().final_test_frame(frame())


def test_unlock_requires_a_reason() -> None:
    g = FinalTestGuard()
    with pytest.raises(ValueError, match="reason"):
        g.unlock("")
    with pytest.raises(ValueError, match="reason"):
        g.unlock("   ")
    assert g.allow_final_test is False


def test_unlock_opens_the_window_and_records_why() -> None:
    g = FinalTestGuard()
    g.unlock("specification frozen and pre-2023 memo written")
    out = g.final_test_frame(frame())
    assert len(out) == 2 and out.index.min() >= FINAL_TEST_START
    assert "frozen" in g.unlock_reason


def test_development_output_containing_locked_dates_is_rejected() -> None:
    with pytest.raises(FinalTestLockError, match="on or after"):
        FinalTestGuard().check_development_only(frame())


def test_clean_development_output_passes_the_check() -> None:
    g = FinalTestGuard()
    g.check_development_only(g.development_frame(frame()))     # must not raise


def test_guard_works_on_a_date_column_too() -> None:
    g = FinalTestGuard()
    f = frame().reset_index(names="entry_date")
    assert len(g.development_frame(f, "entry_date")) == 2
    with pytest.raises(FinalTestLockError):
        g.check_development_only(f, "entry_date")


def test_boundary_date_belongs_to_the_locked_window() -> None:
    g = FinalTestGuard()
    edge = pd.DataFrame({"x": [1]}, index=pd.to_datetime(["2023-01-01"]))
    assert g.development_frame(edge).empty
    with pytest.raises(FinalTestLockError):
        g.check_development_only(edge)


def test_unlocking_one_guard_does_not_unlock_another() -> None:
    a, b = FinalTestGuard(), FinalTestGuard()
    a.unlock("final evaluation")
    assert a.allow_final_test and not b.allow_final_test
    with pytest.raises(FinalTestLockError):
        b.final_test_frame(frame())
