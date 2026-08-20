# Heston methodology — pricing a path-dependent variance payoff

## Why a model is needed at all

Every earlier phase of this project priced variance *model-free*. That was
possible because a variance swap's payoff is spanned by vanilla options: the
Carr–Madan log-contract decomposition replicates `[log S]_T` from a static strip
weighted `dK/K²`, so the fair strike is a portfolio price and no dynamics are
assumed.

A **capped** realised-variance payoff breaks that. `min(RV, C)` is a
path-dependent functional of the whole trajectory, and no static portfolio of
European options replicates it. To value the cap you must say how variance
itself moves. That is what V7 adds, and it is the only reason a model appears.

## Four structures that must not be confused

| | Payoff | Replication |
|---|---|---|
| **A. Variance swap** | `N(K_var − RV)` | static strip + dynamic log-contract hedge; exact |
| **B. Capped variance swap** | `N(K_cap − min(RV, C))` | **no static replication**; path-dependent, model-priced |
| **C. Truncated option strip** | strip with wing strikes removed | a static portfolio; prices a *corridor* of the log contract, not a cap on RV |
| **D. Corridor / conditional variance** | variance accumulated only while `S ∈ [A, B]` | conditions on the *spot level*, not on accumulated variance |

Deleting deep-put strikes from a vanilla strip does **not** create a capped
variance swap. C truncates the strike domain; B truncates the accumulated
variance. They coincide only by accident.

## The cap is not a discount

The fair capped strike follows from the pathwise identity
`min(x, C) + (x − C)⁺ = x`:

    K_cap = E^Q[min(RV, C)] = K_var − E^Q[(RV − C)⁺]

The seller gives up the tail and is paid less for the swap by exactly the
risk-neutral value of that tail. Any comparison that keeps `K_var` while capping
the payoff is measuring a contract nobody would write. That quantity is computed
here only as a diagnostic, and is labelled *not a contract* wherever it appears.

`K_var` is taken from the observable model-free strip rather than from the model.
This confines the model's influence to `E^Q[(RV − C)⁺]` — the one term that
genuinely needs dynamics — and means the model never has to reproduce the
variance *level* correctly for the capped price to be right.

## Model and conventions

    dS_t = (r − q) S_t dt + √v_t S_t dW¹
    dv_t = κ(θ − v_t) dt + ξ √v_t dW²,   d⟨W¹, W²⟩ = ρ dt

Everything is quoted off the forward, so the drift never enters the
characteristic function and `E[S_T] = F` holds by construction. The forward comes
from put–call parity at the strike where call and put mid prices are closest —
the same convention the canonical V5 engine uses — so the dividend yield is
implied point-in-time rather than assumed.

Vanillas are priced by Lewis' single-integral formula using the Albrecher
"little trap" branch of the characteristic function, which keeps the complex
logarithm continuous at long maturities. 192-node Gauss–Legendre quadrature on
[0, 200] converges to 1.3 × 10⁻⁸ against a 768-node reference. The one known
weakness is the far wing at low volatility, where the absolute error floor is
about 4 × 10⁻⁴ price units on options worth essentially nothing; the calibration
universe excludes that corner.

## Calibration

Universe, loss and weights were fixed before any capped-variance result was
computed.

- **Universe**: out-of-the-money quotes only, 7–60 DTE, moneyness 0.80–1.20,
  positive bid, mid ≥ $0.05, relative spread ≤ 60%, at least 5 quotes per
  maturity and at least 2 maturities. Only OTM options are used: they carry the
  surface information and avoid double-counting the same volatility through parity.
- **Loss**: spread-normalised price error,
  `residual = (P_model − P_mid) / max(ask − bid, 0.02 · vega)`.
  Since `dIV = dP / vega`, this is a first-order approximation to a
  spread-weighted implied-volatility error. Wide-spread wings automatically
  carry little weight, and the vega floor stops one tight at-the-money quote
  from dominating. Implied-volatility RMSE is reported from the fitted
  parameters as a diagnostic but never optimised directly.
- **Constraints**: `v0, κ, θ, ξ > 0`, `−0.985 < ρ < 0.30`, `κ ≤ 20`. The Feller
  condition is monitored and reported, not enforced.
- **Cold start** at a fixed point on every date, so no calibration depends on its
  neighbours and the parameter-stability analysis is not smoothed by warm starts.

## Monte Carlo

Andersen's Quadratic-Exponential scheme, which matches the first two moments of
the exact non-central chi-squared transition and is unconditionally positive.
Variance can never go negative, so no truncation bias is introduced — which
matters here because the Feller condition is violated on every date. Log-spot
uses the standard drift interpolation with central weights.

Realised variance is simulated at the contract's **own** daily observation count
and annualised by the same calendar year fraction as the historical contract, so
the simulated payoff is monitored exactly as the traded one is. The difference
between daily-monitored and continuously-monitored variance is measured rather
than assumed: median +0.04%.

## What is not claimed

These are **model prices for a hypothetical OTC capped variance swap**. No
exchange-listed replication is derived, no dealer bid–offer is modelled, and no
claim is made that the capped payoff was directly tradable through the SPY
vanilla chain. A real capped swap would carry a spread over the model-fair
strike computed here.
