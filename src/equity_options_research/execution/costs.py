from __future__ import annotations


def option_commission(contracts: int, legs: int = 2, per_contract: float = 0.65) -> float:
    return abs(contracts) * legs * per_contract


def financing_cost(cash_balance: float, annual_rate: float, elapsed_days: float) -> float:
    """Positive cost for borrowing; negative value represents interest income."""
    return -cash_balance * annual_rate * elapsed_days / 365.0

