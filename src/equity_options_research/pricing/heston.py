"""Heston stochastic volatility: characteristic function, vanillas, and paths.

The canonical V5 engine prices variance model-free, without committing to any
volatility dynamics. That works because a variance swap's payoff is spanned by
vanillas. A *capped* realised-variance payoff is not: ``min(RV, C)`` is a
path-dependent functional with no static replication, so valuing it requires a
model of how variance actually moves. This module supplies that model.

Under the risk-neutral measure,

    dS_t = (r - q) S_t dt + sqrt(v_t) S_t dW1
    dv_t = kappa (theta - v_t) dt + xi sqrt(v_t) dW2
    d<W1, W2> = rho dt

Everything here is quoted off the forward, so the drift never appears in the
characteristic function and ``E[S_T] = F`` holds by construction — a property
the tests exploit as a correctness check.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

__all__ = [
    "HestonParams",
    "characteristic_function",
    "call_prices",
    "put_prices",
    "expected_integrated_variance",
    "simulate_paths",
    "realised_variance_from_paths",
]


@dataclass(frozen=True)
class HestonParams:
    """Risk-neutral Heston parameters.

    ``feller`` reports whether ``2 kappa theta >= xi^2``. A violation does not
    invalidate the fit — index surfaces routinely need one — but it means the
    variance process can reach zero, so it is carried alongside every result
    rather than silently accepted.
    """

    v0: float
    kappa: float
    theta: float
    xi: float
    rho: float

    def __post_init__(self) -> None:
        if self.v0 <= 0 or self.theta <= 0 or self.kappa <= 0 or self.xi <= 0:
            raise ValueError("v0, kappa, theta and xi must be strictly positive")
        if not -1.0 < self.rho < 1.0:
            raise ValueError("rho must lie strictly inside (-1, 1)")

    @property
    def feller(self) -> bool:
        return 2.0 * self.kappa * self.theta >= self.xi**2

    @property
    def feller_ratio(self) -> float:
        return float(2.0 * self.kappa * self.theta / self.xi**2)

    def as_array(self) -> np.ndarray:
        return np.array([self.v0, self.kappa, self.theta, self.xi, self.rho], float)

    @classmethod
    def from_array(cls, values: np.ndarray) -> HestonParams:
        return cls(*(float(x) for x in values))


def characteristic_function(u: np.ndarray, T: float, p: HestonParams) -> np.ndarray:
    """CF of ``ln(S_T / F)`` — the forward-normalised log return.

    Uses the Albrecher "little Heston trap" branch, which keeps the complex
    logarithm continuous for long maturities where the textbook form flips sign
    and produces oscillating garbage.
    """

    u = np.asarray(u, dtype=complex)
    iu = 1j * u
    kappa, theta, xi, rho, v0 = p.kappa, p.theta, p.xi, p.rho, p.v0

    beta = kappa - rho * xi * iu
    d = np.sqrt(beta**2 + xi**2 * (iu + u**2))
    # the trap-free branch keeps |g| < 1, so log(1 - g exp(-dT)) never winds
    g = (beta - d) / (beta + d)

    exp_dt = np.exp(-d * T)
    log_term = np.log(np.where(np.abs(1.0 - g) < 1e-300, 1e-300, (1.0 - g * exp_dt) / (1.0 - g)))
    term_theta = (kappa * theta / xi**2) * ((beta - d) * T - 2.0 * log_term)
    term_v0 = (v0 / xi**2) * (beta - d) * (1.0 - exp_dt) / (1.0 - g * exp_dt)
    return np.exp(term_theta + term_v0)


def _gauss_legendre(nodes: int, upper: float) -> tuple[np.ndarray, np.ndarray]:
    x, w = np.polynomial.legendre.leggauss(nodes)
    return 0.5 * upper * (x + 1.0), 0.5 * upper * w


def call_prices(
    forward: float,
    strikes: np.ndarray,
    T: float,
    rate: float,
    params: HestonParams,
    nodes: int = 192,
    upper: float = 200.0,
) -> np.ndarray:
    """European call prices by Lewis' single-integral formula.

        C = e^{-rT} [ F - sqrt(F K)/pi * int_0^inf Re(e^{iuk} psi(u - i/2)) / (u^2 + 1/4) du ]

    with ``k = ln(F/K)``. One integral for the whole strike vector at a given
    maturity, since the characteristic function does not depend on the strike.
    """

    strikes = np.atleast_1d(np.asarray(strikes, float))
    if T <= 0:
        return np.maximum(forward - strikes, 0.0)
    u, w = _gauss_legendre(nodes, upper)
    psi = characteristic_function(u - 0.5j, T, params) / (u**2 + 0.25)
    k = np.log(forward / strikes)
    integrand = np.real(np.exp(1j * np.outer(k, u)) * psi[None, :])
    integral = integrand @ w
    prices = np.exp(-rate * T) * (forward - np.sqrt(forward * strikes) / np.pi * integral)
    return np.maximum(prices, 0.0)


def put_prices(
    forward: float,
    strikes: np.ndarray,
    T: float,
    rate: float,
    params: HestonParams,
    nodes: int = 192,
    upper: float = 200.0,
) -> np.ndarray:
    """European puts, by parity off the calls so the two can never disagree."""

    calls = call_prices(forward, strikes, T, rate, params, nodes, upper)
    return calls - np.exp(-rate * T) * (forward - np.atleast_1d(np.asarray(strikes, float)))


def expected_integrated_variance(T: float, p: HestonParams) -> float:
    """``E^Q[(1/T) int_0^T v_t dt]`` — the continuously monitored fair strike.

    Closed form under Heston, so it benchmarks the Monte Carlo engine without
    simulation error.
    """

    if T <= 0:
        return float(p.v0)
    decay = (1.0 - np.exp(-p.kappa * T)) / (p.kappa * T)
    return float(p.theta + (p.v0 - p.theta) * decay)


def simulate_paths(
    params: HestonParams,
    T: float,
    steps: int,
    paths: int,
    seed: int,
    psi_cut: float = 1.5,
    return_variance: bool = False,
) -> np.ndarray | tuple[np.ndarray, np.ndarray]:
    """Andersen's Quadratic-Exponential scheme. Returns log returns, shape (paths, steps).

    QE matches the first two moments of the exact non-central chi-squared
    transition and is unconditionally positive, so the variance process can never
    go negative and no truncation bias is introduced. Log-spot uses the standard
    drift interpolation with central weights, which removes the leading
    discretisation bias in the correlation term.

    Returns forward-normalised log returns: the drift is excluded, so summing a
    row gives ``ln(S_T / F)``. With ``return_variance`` the variance path is
    returned alongside, which the tests use to assert positivity directly.
    """

    rng = np.random.default_rng(seed)
    dt = T / steps
    kappa, theta, xi, rho = params.kappa, params.theta, params.xi, params.rho
    exp_kdt = np.exp(-kappa * dt)
    k0 = -rho * kappa * theta * dt / xi
    k1 = 0.5 * dt * (kappa * rho / xi - 0.5) - rho / xi
    k2 = 0.5 * dt * (kappa * rho / xi - 0.5) + rho / xi
    k3 = 0.5 * dt * (1.0 - rho**2)

    v = np.full(paths, params.v0, dtype=float)
    out = np.empty((paths, steps), dtype=float)
    variance = np.empty((paths, steps + 1), dtype=float) if return_variance else None
    if variance is not None:
        variance[:, 0] = v
    for i in range(steps):
        zv = rng.standard_normal(paths)
        uv = rng.random(paths)
        zx = rng.standard_normal(paths)

        m = theta + (v - theta) * exp_kdt
        s2 = (v * xi**2 * exp_kdt / kappa) * (1.0 - exp_kdt) + (theta * xi**2 / (2.0 * kappa)) * (1.0 - exp_kdt) ** 2
        psi = np.where(m > 0, s2 / np.maximum(m**2, 1e-300), np.inf)

        # quadratic branch for low variance-of-variance
        inv_psi = 2.0 / np.maximum(psi, 1e-300)
        b2 = np.maximum(inv_psi - 1.0 + np.sqrt(np.maximum(inv_psi * (inv_psi - 1.0), 0.0)), 0.0)
        a = m / (1.0 + b2)
        v_quad = a * (np.sqrt(b2) + zv) ** 2

        # exponential branch with an atom at zero for high variance-of-variance
        p_atom = np.clip((psi - 1.0) / (psi + 1.0), 0.0, 1.0 - 1e-12)
        beta = (1.0 - p_atom) / np.maximum(m, 1e-300)
        v_exp = np.where(uv <= p_atom, 0.0, np.log(np.maximum((1.0 - p_atom) / np.maximum(1.0 - uv, 1e-300), 1e-300)) / beta)

        v_next = np.where(psi <= psi_cut, v_quad, v_exp)
        v_next = np.maximum(v_next, 0.0)
        out[:, i] = k0 + k1 * v + k2 * v_next + np.sqrt(np.maximum(k3 * (v + v_next), 0.0)) * zx
        v = v_next
        if variance is not None:
            variance[:, i + 1] = v
    if variance is not None:
        return out, variance
    return out


def realised_variance_from_paths(log_returns: np.ndarray, T: float) -> np.ndarray:
    """Annualised realised variance under the canonical V5 convention.

    Sum of squared log returns sampled at the contract's observation times,
    divided by the calendar year fraction — identical to
    ``canonical_variance_engine.realised_variance`` applied to a simulated path.
    """

    return np.sum(np.asarray(log_returns, float) ** 2, axis=1) / T
