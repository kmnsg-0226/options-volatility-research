# Realised-variance leg — exact definition

```
RV_annualised = ( Σ_{i=1..n} [ ln(S_i / S_{i-1}) ]² ) / T_contract
```

where `S_0` is the entry close, `S_n` the expiry close, and
`T_contract = (expiry − entry)/365`.

## Why this annualisation

The legacy engine annualised realised variance by `252/n` while pricing the strip
on `dte/365`, and closed the position at DTE ≤ 2 so the two windows did not even
cover the same days. The audit measured the resulting bias at **−5.9%**, with a
calendar/trading horizon ratio of **1.076**.

Dividing total realised variance by the *same* `T` that prices the strip removes
the mismatch by construction: there is now exactly one horizon in the system.

## Unit vocabulary

| Quantity | Meaning | Typical value |
|---|---|---|
| Total variance | `Σ x²`, dimensionless | ~0.0029 |
| **Annualised variance rate** | `Σ x² / T` — **what N multiplies** | ~0.035 |
| Variance points | annualised rate × 10⁴ | ~350 |
| Volatility | `√(annualised rate)` | ~0.187 |
| Variance notional `N` | **dollars per unit annualised variance** | $1,000,000 |

A 0.01 move in the annualised rate is worth `0.01 × N = $10,000`.

## Discrete monitoring

Per interval, `2[(e^x − 1) − x] = x² + x³/3 + O(x⁴)`, so the identity reconstructs
squared returns plus a **signed** cubic remainder — down moves under-deliver, up
moves over-deliver. Jumps break it further, since a daily hedge cannot react
inside a gap. Empirically the residual correlates with realised variance (0.444)
and the largest daily move (0.349), and **not** with leg count (0.024), which is
the signature of monitoring error rather than an implementation defect.
