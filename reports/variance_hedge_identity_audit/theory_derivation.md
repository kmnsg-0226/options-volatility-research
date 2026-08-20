# Variance-swap replication: derivation and what our implementation actually targets

## 1. The seven objects, kept distinct

| | Object | Definition |
|---|---|---|
| **A** | Continuous-path quadratic variation | `[log S]_T = ∫₀ᵀ σ_t² dt` for a continuous semimartingale |
| **B** | Continuously monitored realised variance | `(1/T)∫₀ᵀ σ_t² dt` — the annualised limit of B as sampling → 0 |
| **C** | **Our realised leg** | `RV = (252/n) Σ_{i=1..n} [ln(S_i/S_{i-1})]²`, daily close-to-close |
| **D** | Model-free implied variance | `σ²(T) = (2/T)Σ ΔK/K² e^{rT} Q(K) − (1/T)(F/K₀−1)²` — the CBOE fair strike |
| **E** | Static terminal log-contract replication | A strip of OTM options paying `(2/T)[S_T/F − 1 − ln(S_T/F)]` |
| **F** | Dynamic underlying position required by the identity | derived in §3 |
| **G** | Conventional BSM delta hedging of an option portfolio | `Σ nᵢ·mult·δᵢ(BSM, IVᵢ)` |

**F and G are not identical by definition.** Whether they coincide is the empirical
question this audit answers.

## 2. The continuous-time identity

For a strictly positive continuous semimartingale, Itô gives

    d(log S_t) = dS_t/S_t − ½ σ_t² dt

Integrating over [0,T] and rearranging:

    ∫₀ᵀ σ_t² dt = 2∫₀ᵀ dS_t/S_t − 2 log(S_T/S_0)                    (1)

so annualised quadratic variation is

    RV_T = (1/T)[ 2∫₀ᵀ dS_t/S_t − 2 log(S_T/S_0) ]                   (2)

Identity (1) is **pathwise and model-free**: no volatility process is assumed. It
requires only continuity and positivity. Both requirements fail for real SPY
paths, which is the subject of §5.

## 3. The dynamic position F

The term `2∫dS_t/S_t` is the gain of holding `2/S_t` shares continuously, i.e. a
**constant dollar exposure of $2**, rebalanced as S moves. Scaling by `1/T` for
annualisation and by variance notional `N` (dollars per unit annualised variance):

    h_t^dyn = N · (2/T) · (1/S_t)     shares, long, for a LONG variance position

with constant dollar exposure `2N/T`.

## 4. Rates, dividends, and why the forward enters

Under `dS/S = (r−q)dt + σ dW`, the drift cancels in (1) — the identity is
unaffected. What changes is the *reference point*. Writing `F = S_0 e^{(r−q)T}`:

    −2 log(S_T/S_0) = −2 log(S_T/F) − 2(r−q)T

so

    RV_T = (1/T)[ 2∫dS/S − 2 log(S_T/F) ] − 2(r−q)                   (3)

The `−2(r−q)` is a deterministic constant, not a traded leg.

**Our realised leg uses SPY price returns, not total returns.** SPY distributes
dividends, so its price path drops on ex-dates. Those drops enter C as genuine
squared returns even though they are not volatility. Over ~30 days SPY pays at
most one quarterly distribution of roughly 0.35%, contributing about
`(0.0035)² × 252/21 ≈ 1.5e-4` of annualised variance against a typical level of
~0.027 — about **0.5%**, and always upward. It is small but systematic, and it
biases measured realised variance *up*, i.e. against a short-variance position.

## 5. Decomposing the log contract (E)

The Carr–Madan representation of a twice-differentiable payoff about `F`:

    f(S_T) = f(F) + f'(F)(S_T−F) + ∫₀^F f''(K)(K−S_T)⁺dK + ∫_F^∞ f''(K)(S_T−K)⁺dK

For `f(S) = −(2/T)log(S/F)`: `f(F)=0`, `f'(F) = −2/(TF)`, `f''(K) = 2/(TK²)`.

    −(2/T)log(S_T/F) = −(2/(TF))(S_T−F) + (2/T)[∫₀^F (K−S_T)⁺/K² dK + ∫_F^∞ (S_T−K)⁺/K² dK]

Therefore:

| Payoff piece | Instrument |
|---|---|
| `∫ dK/K²` weighted OTM puts (K<F) and calls (K>F) | **the option strip** |
| `−(2/(TF))(S_T − F)` linear term | **forward / stock**, not options |
| `f(F) = 0` and discounting | **cash/bond** |
| `−(1/T)(F/K₀−1)²` in the CBOE formula | **valuation adjustment to the fair strike — NOT a tradeable leg** |

**The strip alone pays `(2/T)[S_T/F − 1 − ln(S_T/F)]`** — the log contract *plus*
the linear term, because the strip does not include the offsetting short forward.

### Answering §3 of the brief directly

1. Our CBOE-style strip replicates the log contract **plus** a static long
   forward of `2/(TF)` units.
2. Options represent the `dK/K²` curvature only.
3. The linear term needs stock/forward; the constant needs cash.
4. `−(1/T)(F/K₀−1)²` is a **valuation adjustment**, correcting the fair strike for
   `K₀ ≠ F`. It is not an instrument.
5. **We have not previously traded that term as a leg** — it appears only in
   `replicated_fair_strike`, i.e. in valuation. That is correct.

## 6. The required hedge for a SHORT variance position

From (3), the strip payoff `(2/T)[S_T/F − 1 − ln(S_T/F)]`, and `RV`:

    RV = (2/T)∫dS/S + strip − (2/T)(S_T/F − 1) − 2(r−q)

A **seller** of variance holds `−RV`, i.e. short strip, short the dynamic leg,
long `2/(TF)` forward. The **net share position** is

    h_t^theory = N · (2/T) · ( 1/F − 1/S_t )     shares                (4)

This is the object the audit will compare against. Its properties:

- `h = 0` at inception when `S_0 = F`;
- **short stock as S falls, long stock as S rises** — the short-gamma signature;
- it is **model-free**: it depends only on `S_t`, `F`, `T`, `N`. No implied
  volatility, no BSM, no strike truncation.

Property three is the crux. The current implementation's hedge (G) is
`Σ nᵢ·mult·δᵢ(BSM, IVᵢ)`, which *does* depend on the implied-volatility surface,
on the dividend and rate assumptions, and on which strikes survive truncation.
**(4) does not.** Any empirical gap between them must come from those channels.

## 7. Discrete monitoring (§5 of the brief)

Identity (1) holds pathwise in continuous time. Our payoff C is a **discrete**
sum of squared daily log returns. Over one interval,

    2·(ΔS/S_{i-1}) − 2·ln(S_i/S_{i-1}) = 2[ (e^x − 1) − x ]  where x = ln(S_i/S_{i-1})
                                       = x² + x³/3 + O(x⁴)

so each interval reconstructs its squared return **plus a third-order term**. The
discretisation error is therefore

    Σ x_i³/3 + O(x⁴)

which is **signed**: negative returns contribute negative cubic terms, so the
replication *under*-delivers on down moves and *over*-delivers on up moves. For a
1% daily move the relative error is ~0.33%; for a −10% move it is ~−3.3%. This is
a genuine, quantifiable property of discretely monitored variance, **not a coding
defect**, and there is no exact static-plus-daily-dynamic hedge for the
close-to-close definition. §6-C of the brief is therefore answered below in the
implementation as NOT EXACTLY IMPLEMENTABLE; we implement (4) — the best
theoretically justified approximation — and quantify the residual.

Jumps break (1) more severely: a jump contributes `x²` to C but the hedge captures
only the linear response, leaving the full cubic-and-higher remainder.
