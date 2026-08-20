# Self-financing cash account

## Convention

The book starts with zero cash. Every movement is recorded:

| Event | Cash flow |
|---|---|
| Sell the strip | `+ Σ nᵢ · mult · fill_priceᵢ` |
| Option commissions | `− $0.65 per contract per leg` |
| Hedge trade | `− Δh · S` |
| Hedge slippage | `− |Δh| · S · 0.5bps` |
| Interest | `balance × r × days/365`, accrued each step |
| Settlement | `− strip intrinsic` |
| Hedge unwind | `+ h · S_T`, less slippage |

**Final balance is the trade's P&L.** The identity
`net = gross + financing − costs` reconciles to **1.16e-09**.

`r` is the same-date zero-curve rate interpolated to the option's maturity, held
fixed for the trade's life — a simple, documented choice. Borrowing and lending
are charged at the same rate; no bid/offer spread on funding is modelled, which
understates real financing cost.

## Size of the effect

| Period | Financing |
|---|---|
| pre-2023 | **−$789** |
| OOS 2023–2025 | **−$16,692** |

Near-zero pre-2023 because the rate was near zero for much of it; materially
negative OOS because rates rose above 5% while the hedge runs a net cash debit.
Setting financing to zero — as the legacy engine did — was harmless in the ZIRP
era and is **not** harmless now.
