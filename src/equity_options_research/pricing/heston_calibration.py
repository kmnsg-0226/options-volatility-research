"""Point-in-time Heston calibration to a listed option surface.

The calibration universe, the loss and the weights are all fixed here, before
any capped-variance result is computed, so that no downstream P&L can influence
how the model was fitted.

Loss. Residuals are quoted-spread-normalised price errors,

    residual_i = (P_model,i - P_mid,i) / max(ask_i - bid_i, floor * vega_i)

which is a first-order approximation to a spread-weighted implied-volatility
error, since ``dIV = dP / vega``. Wide-spread wing options therefore carry small
weight automatically, and the floor stops a single tight-spread at-the-money
quote from dominating the fit. Implied-volatility RMSE is reported afterwards
from the fitted parameters as a quality diagnostic, but is never optimised
directly - inverting Heston prices to implied volatility inside the objective
would cost far more than it adds.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd
from scipy.optimize import least_squares

from equity_options_research.pricing.greeks import vega as bs_vega
from equity_options_research.pricing.heston import HestonParams, call_prices, put_prices
from equity_options_research.pricing.implied_vol import implied_volatility

# Fixed before any result is examined.
MIN_DTE, MAX_DTE = 7, 60
MIN_MONEYNESS, MAX_MONEYNESS = 0.80, 1.20
MIN_MID = 0.05
MAX_RELATIVE_SPREAD = 0.60
MIN_QUOTES_PER_MATURITY = 5
MIN_MATURITIES = 2
SPREAD_FLOOR = 0.02

LOWER = np.array([1e-4, 0.20, 1e-3, 0.05, -0.985])
UPPER = np.array([2.50, 20.0, 1.00, 5.00, 0.30])
START = np.array([0.03, 2.50, 0.04, 0.80, -0.70])


@dataclass
class CalibrationResult:
    """Fitted parameters plus everything needed to judge whether to trust them."""

    date: pd.Timestamp
    params: HestonParams | None
    success: bool
    reason: str = ""
    n_quotes: int = 0
    n_maturities: int = 0
    price_rmse: float = np.nan
    price_mae: float = np.nan
    iv_rmse: float = np.nan
    iv_mae: float = np.nan
    iv_median_abs: float = np.nan
    max_iv_error: float = np.nan
    cost: float = np.nan
    optimality: float = np.nan
    n_function_evals: int = 0
    errors_by_moneyness: dict[str, float] = field(default_factory=dict)
    errors_by_maturity: dict[str, float] = field(default_factory=dict)

    def as_row(self) -> dict[str, object]:
        p = self.params
        return {
            "date": self.date, "success": self.success, "reason": self.reason,
            "v0": p.v0 if p else np.nan, "kappa": p.kappa if p else np.nan,
            "theta": p.theta if p else np.nan, "xi": p.xi if p else np.nan,
            "rho": p.rho if p else np.nan,
            "feller_ok": p.feller if p else False,
            "feller_ratio": p.feller_ratio if p else np.nan,
            "n_quotes": self.n_quotes, "n_maturities": self.n_maturities,
            "price_rmse": self.price_rmse, "price_mae": self.price_mae,
            "iv_rmse": self.iv_rmse, "iv_mae": self.iv_mae,
            "iv_median_abs": self.iv_median_abs, "max_iv_error": self.max_iv_error,
            "cost": self.cost, "optimality": self.optimality,
            "n_function_evals": self.n_function_evals,
            **{f"iv_rmse_{k}": v for k, v in self.errors_by_moneyness.items()},
            **{f"iv_rmse_dte_{k}": v for k, v in self.errors_by_maturity.items()},
        }


def forward_from_parity(group: pd.DataFrame, rate: float, year_fraction: float) -> float:
    """Forward implied by put-call parity at the strike where the two are closest.

    Same convention as the canonical model-free engine, so the calibration and
    the variance strike see the same forward.
    """

    both = group[(group.call_bid > 0) & (group.put_bid > 0)]
    if both.empty:
        return float(group.spot.iloc[0] * np.exp(rate * year_fraction))
    call_mid = 0.5 * (both.call_bid + both.call_ask)
    put_mid = 0.5 * (both.put_bid + both.put_ask)
    i = int((call_mid - put_mid).abs().to_numpy().argmin())
    k = float(both.strike.iloc[i])
    return float(k + np.exp(rate * year_fraction) * (call_mid.iloc[i] - put_mid.iloc[i]))


def build_universe(chain: pd.DataFrame, rate: float) -> pd.DataFrame:
    """Out-of-the-money quotes that are liquid enough to inform a fit.

    Only OTM options are kept: they carry the surface information and avoid
    double-counting the same volatility through parity.
    """

    rows = []
    for expiry, g in chain.groupby("expiration"):
        dte = float(g.dte.iloc[0])
        if not MIN_DTE <= dte <= MAX_DTE:
            continue
        T = dte / 365.0
        F = forward_from_parity(g, rate, T)
        for _, r in g.iterrows():
            k = float(r.strike)
            m = k / F
            if not MIN_MONEYNESS <= m <= MAX_MONEYNESS:
                continue
            right = "call" if k >= F else "put"
            bid = float(r.call_bid if right == "call" else r.put_bid)
            ask = float(r.call_ask if right == "call" else r.put_ask)
            if not (np.isfinite(bid) and np.isfinite(ask)) or bid <= 0 or ask <= bid:
                continue
            mid = 0.5 * (bid + ask)
            if mid < MIN_MID or (ask - bid) / mid > MAX_RELATIVE_SPREAD:
                continue
            rows.append({"expiry": expiry, "dte": dte, "year_fraction": T, "forward": F, "strike": k,
                         "moneyness": m, "right": right, "bid": bid, "ask": ask, "mid": mid,
                         "spread": ask - bid, "spot": float(r.spot)})
    if not rows:
        return pd.DataFrame()
    u = pd.DataFrame(rows)
    counts = u.groupby("expiry").size()
    return u[u.expiry.isin(counts[counts >= MIN_QUOTES_PER_MATURITY].index)].reset_index(drop=True)


def market_implied_vols(universe: pd.DataFrame, rate: float) -> np.ndarray:
    """Implied volatilities of the mid quotes, on the calibration's own forward."""

    out = np.full(len(universe), np.nan)
    for i, r in enumerate(universe.itertuples()):
        spot = r.forward * np.exp(-rate * r.year_fraction)          # price off the forward, q folded in
        res = implied_volatility(r.right, r.mid, spot, r.strike, r.year_fraction, rate, 0.0)
        if res.success and res.volatility is not None:
            out[i] = res.volatility
    return out


def _model_prices(universe: pd.DataFrame, rate: float, params: HestonParams) -> np.ndarray:
    out = np.empty(len(universe))
    for _, idx in universe.groupby("expiry").groups.items():
        block = universe.loc[idx]
        F, T = float(block.forward.iloc[0]), float(block["year_fraction"].iloc[0])
        strikes = block.strike.to_numpy(float)
        is_call = (block.right == "call").to_numpy()
        calls = call_prices(F, strikes, T, rate, params)
        puts = put_prices(F, strikes, T, rate, params)
        out[universe.index.get_indexer(idx)] = np.where(is_call, calls, puts)
    return out


def calibrate(
    chain: pd.DataFrame,
    date: pd.Timestamp,
    rate: float,
    start: np.ndarray | None = None,
) -> tuple[CalibrationResult, pd.DataFrame]:
    """Fit Heston to one day's surface. Returns the result and the universe used."""

    universe = build_universe(chain, rate)
    if len(universe) == 0 or universe.expiry.nunique() < MIN_MATURITIES:
        return CalibrationResult(date, None, False, "insufficient quotes"), universe

    market = universe.mid.to_numpy(float)
    iv_market = market_implied_vols(universe, rate)
    universe = universe.assign(iv_market=iv_market)
    keep = np.isfinite(iv_market) & (iv_market > 0.01) & (iv_market < 3.0)
    universe = universe[keep].reset_index(drop=True)
    if len(universe) == 0 or universe.expiry.nunique() < MIN_MATURITIES:
        return CalibrationResult(date, None, False, "no invertible quotes"), universe

    market = universe.mid.to_numpy(float)
    spots = universe.forward.to_numpy(float) * np.exp(-rate * universe["year_fraction"].to_numpy(float))
    vegas = np.array([bs_vega(s, r.strike, r.year_fraction, rate, 0.0, r.iv_market)
                      for s, r in zip(spots, universe.itertuples(), strict=True)])
    denom = np.maximum(universe.spread.to_numpy(float), SPREAD_FLOOR * np.maximum(vegas, 1e-8))
    weights = 1.0 / denom

    def residuals(x: np.ndarray) -> np.ndarray:
        try:
            p = HestonParams.from_array(x)
        except ValueError:
            return np.full(len(universe), 1e6)
        model = _model_prices(universe, rate, p)
        if not np.all(np.isfinite(model)):
            return np.full(len(universe), 1e6)
        return weights * (model - market)

    x0 = np.clip(START if start is None else start, LOWER, UPPER)
    try:
        fit = least_squares(residuals, x0, bounds=(LOWER, UPPER), method="trf",
                            xtol=1e-10, ftol=1e-10, max_nfev=400)
    except Exception as exc:                                  # noqa: BLE001
        return CalibrationResult(date, None, False, f"optimiser failed: {exc}"), universe

    params = HestonParams.from_array(fit.x)
    model = _model_prices(universe, rate, params)
    iv_model = np.array([
        (lambda res: res.volatility if res.success and res.volatility is not None else np.nan)(
            implied_volatility(r.right, float(m), float(s), r.strike, r.year_fraction, rate, 0.0))
        for m, s, r in zip(model, spots, universe.itertuples(), strict=True)
    ])
    iv_err = iv_model - universe.iv_market.to_numpy(float)
    ok = np.isfinite(iv_err)
    bucket = pd.cut(universe.moneyness, [0.0, 0.90, 0.97, 1.03, 1.10, np.inf],
                    labels=["deep_put", "otm_put", "atm", "otm_call", "deep_call"])
    dte_bucket = pd.cut(universe.dte, [0, 14, 30, 45, 61], labels=["7_14", "15_30", "31_45", "46_60"])
    frame = pd.DataFrame({"err": iv_err, "m": bucket, "d": dte_bucket})

    result = CalibrationResult(
        date=date, params=params, success=bool(fit.success), reason=str(fit.message)[:80],
        n_quotes=len(universe), n_maturities=int(universe.expiry.nunique()),
        price_rmse=float(np.sqrt(np.mean((model - market) ** 2))),
        price_mae=float(np.mean(np.abs(model - market))),
        iv_rmse=float(np.sqrt(np.nanmean(iv_err[ok] ** 2))) if ok.any() else np.nan,
        iv_mae=float(np.nanmean(np.abs(iv_err[ok]))) if ok.any() else np.nan,
        iv_median_abs=float(np.nanmedian(np.abs(iv_err[ok]))) if ok.any() else np.nan,
        max_iv_error=float(np.nanmax(np.abs(iv_err[ok]))) if ok.any() else np.nan,
        cost=float(fit.cost), optimality=float(fit.optimality), n_function_evals=int(fit.nfev),
        errors_by_moneyness={str(k): float(np.sqrt(np.nanmean(v.err ** 2)))
                             for k, v in frame.groupby("m", observed=True)},
        errors_by_maturity={str(k): float(np.sqrt(np.nanmean(v.err ** 2)))
                            for k, v in frame.groupby("d", observed=True)},
    )
    return result, universe.assign(iv_model=iv_model, model_price=model)
