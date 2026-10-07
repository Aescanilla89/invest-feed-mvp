# Tradefinder · Market Desk

## Purpose

Market Desk is a deterministic description of current US market conditions. The composite is a **regime indicator**, not a price target, return forecast, or investment recommendation. Each displayed observation links to its source and carries its own date, frequency, and freshness status. Missing or stale observations are excluded; they are never filled with examples or last-known values without disclosure.

## Architecture and refresh

- `GET /api/market-desk` returns a typed Pydantic response independently of the opportunities endpoint.
- FRED observations are requested from the official St. Louis Fed API and cached in process for 30 minutes. The requests run concurrently with bounded timeouts. `FRED_API_KEY` is already used by the scheduled macro-release job and is required for live FRED readings.
- ETF bars are requested from the official Alpaca Market Data API (IEX feed) when Alpaca credentials are configured. They are requested only for this endpoint and cached with the same response. IEX is a single-exchange feed, so the ETF trend comparison is not consolidated market breadth.
- `Watch next` reads verified upcoming macro catalysts already stored by the daily FRED release-calendar job. Consensus is always null because this app has no licensed consensus source.
- If a provider or series fails, its values and score are null. The API still returns a partial response. The Market Desk UI has its own error state and does not gate opportunities.

## Signals and source series

| Desk | Signal | FRED series | Interpretation |
|---|---|---|---|
| Liquidity | Fed assets | WALCL | Direction of recent balance-sheet change; a higher balance is supportive only as one liquidity proxy. |
| Liquidity | Bank reserves | WRESBAL | Recent direction in reserve balances. |
| Liquidity | Treasury cash balance | WTREGEN | Recent decline is supportive for cash availability; it is not a complete measure of Treasury flows. |
| Liquidity | ON RRP | RRPONTSYD | Recent decline can indicate less cash parked at the Fed; context matters. |
| Liquidity | SOFR and funding spread | SOFR, EFFR | Both daily rates are displayed. A separate spread signal (SOFR minus EFFR, in basis points) scores funding conditions; the nominal level is not treated as stress. A wider positive spread is the warning signal. This still does not show repo volumes or intraday tails. |
| Stress | Equity volatility | VIXCLS | Broad equity volatility; not treated alone as systemic stress. |
| Stress | Financial conditions | NFCI | Chicago Fed broad financial conditions index (positive readings indicate tighter-than-average conditions). |
| Stress | Financial stress | STLFSI4 | St. Louis Fed financial stress index. |
| Stress / credit | High-yield OAS | BAMLH0A0HYM2 | Credit spread conditions; a widening spread is adverse. |
| Macro | CPI, Core CPI, PCE, Core PCE | CPIAUCSL, CPILFESL, PCEPI, PCEPILFE | Year-over-year rates calculated from the published index. Directional changes are shown separately from the latest inflation level. |
| Macro / labour | Unemployment and payrolls | UNRATE, PAYEMS | Latest unemployment level and change in monthly payroll additions. |
| Macro / growth | Real GDP and industrial production | GDPC1, INDPRO | GDP quarter-on-quarter annualized and industrial production year-over-year. |
| Rates | Effective Fed Funds, 2y / 10y Treasury and breakeven | EFFR, DGS2, DGS10, T10YIE | Rates context and market-implied inflation compensation. EFFR is also the reference for the SOFR funding spread. |
| Internals | SPY, QQQ, IWM, RSP trend | Alpaca IEX daily bars | Price relative to 50- and 200-day averages for cap-weighted, tech, small-cap, and equal-weight ETFs. These are trend proxies, **not constituent breadth**. |

We deliberately do not display MOVE, repo trading volumes, advances/declines, constituent percentages above moving averages, new highs/lows, or sector breadth: the current configured sources do not provide a sufficiently reliable, licensed, production-ready feed for those measures.

## Transformations and scores

Each signal is scaled to 0–100, where 50 is neutral and higher values indicate more supportive conditions. For the balance-sheet and liquidity stock measures (WALCL, WRESBAL, WTREGEN, RRPONTSYD), the recent change is ranked against that series' own recent historical changes, then inverted when a falling level is considered supportive. This avoids comparing raw dollars across series. Funding uses the SOFR minus EFFR spread (3bp is the reference level); volatility and credit use broad reference bands centered around 20 VIX and 5% HY OAS respectively. These are transparent heuristic bands, not policy or crisis thresholds. NFCI/STLFSI use zero as the broad normal/stress reference. Remaining macro observations use direction of change, with inflation and unemployment direction inverted where applicable.

The composite uses **30% Liquidity, 30% Stress/Credit, 20% Macro, and 20% Internals**. Within Liquidity, weights are Fed assets 2, reserves 2, TGA 1, RRP 1, SOFR − EFFR spread 2; raw SOFR is context only. Stress weights are VIX 1, NFCI 0.5, STLFSI 0.5, and HY OAS 2; the two broad financial-condition/stress composites receive half weights because their underlying components overlap. Macro first averages headline/core inflation series, labour series, and growth series separately, then weights Inflation 35%, Labour 25%, Growth 40%; this avoids giving inflation extra weight merely because both headline and core series are present. Internals average SPY, QQQ, IWM, and RSP trend proxies. Missing inputs are omitted and component weights renormalized, but the overall regime score is withheld unless at least two of the four major components are available. Confidence also falls with indicator coverage. This means scores can be less comparable when coverage changes; always read coverage and desk rows with the composite.

Regime thresholds: 0–<20 Stress; 20–<40 Risk-Off; 40–<60 Neutral; 60–<80 Risk-On; 80–100 Strong Risk-On. The UI may say `PARTIAL DATA` as the data status even when a score can be calculated from available components.

## Macro regime

The classifier needs at least one fresh inflation series and one fresh growth series. Growth direction is the average change in the GDP and industrial-production growth rates; inflation direction is the average month-to-month change in the year-over-year CPI/PCE rates. It labels the two directions as follows: growth improving + inflation cooling = Goldilocks; growth improving + inflation rising = Reflation; growth cooling + inflation cooling = Slowdown; growth cooling + inflation rising = Stagflation. Labour is a separately reported context and does not override the two-axis label. Confidence is a coverage heuristic, not a statistical probability.

## Cross-asset rules and change list

Rules only fire when required observations are available: SPY up on its latest daily bar while HY OAS widens by more than 0.1 percentage point; SPY trend materially stronger than RSP (narrow participation); RSP positive trend while IWM is weak (small caps lagging); or liquidity and stress scores both supportive. `What changed` selects the largest normalized moves over the latest close/observation (1D where daily), approximately 1W, and approximately 1M where the series frequency permits. It labels the horizon and observation date; quarterly series do not masquerade as monthly changes.

## Limitations

- FRED series publish at daily, weekly, monthly, or quarterly frequency and are revised. The observation date is not necessarily the data's economic reference period or release timestamp.
- The overnight reverse repo and balance-sheet components are proxies, not an identity called “net liquidity”. The display explicitly says so.
- The score uses transparent heuristic scaling and fixed weights; it is not estimated from a calibrated forecasting model.
- Treasury volatility (MOVE), market-wide constituent breadth, official release consensus, and intraday funding tail data are not included.
- Data freshness thresholds are series-specific and conservative. Stale observations remain visible with their date but do not contribute to the score.
- The regime arrow stays neutral until a prior Market Desk snapshot exists; it does not claim that the composite rose or fell based only on today's level.
- This project currently uses in-process caching. A multi-worker deployment can refresh once per worker after expiry. Real yields can be derived from the 10-year nominal yield less 10-year breakeven, but this first version avoids displaying that derived series until its metadata is modeled explicitly.
