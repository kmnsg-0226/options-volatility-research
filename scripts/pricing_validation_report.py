"""Generate a deterministic pricing/Greeks validation artifact."""

from __future__ import annotations

import json
from math import exp
from pathlib import Path

from equity_options_research.pricing.black_scholes import bsm_call_price, bsm_put_price
from equity_options_research.pricing.bounds import put_call_parity
from equity_options_research.pricing.greeks import all_greeks
from equity_options_research.pricing.implied_vol import implied_volatility


def main() -> None:
    S, K, T, r, q, sigma = 100.0, 100.0, 1.0, 0.05, 0.0, 0.2
    call = bsm_call_price(S, K, T, r, q, sigma)
    put = bsm_put_price(S, K, T, r, q, sigma)
    parity = put_call_parity(call, put, S, K, T, r, q, tolerance=1e-10)
    iv = implied_volatility("call", call, S, K, T, r, q)
    report = {
        "scope": "deterministic_european_bsm_validation",
        "inputs": {"S": S, "K": K, "T": T, "r": r, "q": q, "sigma": sigma},
        "call_price": call,
        "put_price": put,
        "expected_call_reference": 10.450583572185565,
        "expected_put_reference": 5.573526022256971,
        "parity_residual": parity.residual,
        "direct_parity_residual": call - put - (S - K * exp(-r * T)),
        "call_greeks": all_greeks("call", S, K, T, r, q, sigma),
        "recovered_iv": iv.volatility,
        "iv_reconstruction_error": iv.absolute_error,
        "american_option_warning": (
            "SPY is American-style; BSM is the V1 IV/Greek convention."
        ),
    }
    destination = Path("reports/pricing_validation.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(destination)


if __name__ == "__main__":
    main()
