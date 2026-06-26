# StageWise — Documento de Trabajo
**Última actualización:** 26 junio 2026

---

## 1. Visión del Producto

**StageWise** es un feed rankeado de oportunidades de inversión en acciones US, combinando dos metodologías clásicas:

- **Stage Analysis de Stan Weinstein** — identifica en qué fase del ciclo está cada acción (base, avance, techo, declive)
- **CAN SLIM de William O'Neil** — filtra por calidad fundamental (EPS, crecimiento, fuerza relativa, soporte institucional)

El resultado: un **feed tipo Netflix** donde el usuario ve las mejores oportunidades del día, rankeadas por score combinado (0-100), con explicación en español generada por IA.

> Sin simulador. Sin brokers. Sin alertas de trading. Solo información de calidad para el inversor que quiere tomar sus propias decisiones con criterio.

---

## 2. Estado Actual del Sistema

| Componente | Estado | URL / Ruta |
|---|---|---|
| Frontend | ✅ Producción | `https://frontend-inky-nine-48.vercel.app` |
| Backend API | ✅ Producción | `https://invest-feed-mvp-production.up.railway.app` |
| Base de datos | ✅ Producción | PostgreSQL en Railway |
| Screener diario | ✅ Cron 06:00 UTC | Railway (Alpaca + SEC EDGAR) |
| Explicaciones IA | ✅ Activo | Top 50 tickers/corrida con Claude |

**Corrida de hoy (26-Jun-2026):** ~600 tickers procesados, top scorer ASML con 88 puntos.

---

## 3. Arquitectura del Sistema

### 3.1 Vista General

```
┌─────────────────────────────────────────────────────────────────┐
│                        FUENTES DE DATOS                         │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │   ALPACA     │  │  SEC EDGAR   │  │     WIKIPEDIA        │  │
│  │  Markets API │  │ data.sec.gov │  │  (S&P500 + Nasdaq)   │  │
│  │  (OHLCV)     │  │ (EPS + SO)   │  │   ~604 tickers       │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
└─────────┼─────────────────┼─────────────────────┼──────────────┘
          │                 │                     │
          └─────────────────┴─────────────────────┘
                            │
                     ┌──────▼──────┐
                     │  SCREENER   │
                     │  (Python)   │
                     │             │
                     │ ┌─────────┐ │
                     │ │Weinstein│ │  Stage 1-4 sobre MA30 semanal
                     │ └────┬────┘ │
                     │      │      │
                     │ ┌────▼────┐ │
                     │ │CAN SLIM │ │  7 criterios C-A-N-S-L-I-M
                     │ └────┬────┘ │
                     │      │      │
                     │ ┌────▼────┐ │
                     │ │ SCORING │ │  Score 0-100 combinado
                     │ └────┬────┘ │
                     └──────┼──────┘
                            │
              ┌─────────────┴─────────────┐
              │                           │
       ┌──────▼──────┐            ┌───────▼──────┐
       │  PostgreSQL │            │  Claude API  │
       │  (Railway)  │            │ Explicaciones│
       │             │            │ Top 50/día   │
       └──────┬──────┘            └──────────────┘
              │
       ┌──────▼──────┐
       │  FastAPI    │
       │  (Railway)  │
       │  REST API   │
       └──────┬──────┘
              │
       ┌──────▼──────┐
       │  Next.js    │
       │  (Vercel)   │
       │  Frontend   │
       └─────────────┘
```

### 3.2 Flujo de Datos por Ticker

```
Para cada ticker del universo (~604):
─────────────────────────────────────────────────────────────

1. OHLCV Semanal (Alpaca)
   └─► 104 semanas de barras diarias → resample a W-FRI
       └─► DataFrame [Open, High, Low, Close, Volume]

2. Análisis Weinstein
   └─► MA30 + pendiente → Stage 1/2/3/4
       └─► Bonus: transición 1→2 con volumen confirmado

3. SEC EDGAR (1 sola petición HTTP)
   ├─► EPS Diluido (10-Q / 10-K) → Criterios C y A
   └─► Shares Outstanding histórico → Criterio S (buyback)

4. Perfil (Alpaca Assets API)
   └─► Nombre de la empresa

5. CAN SLIM (7 criterios)
   ├─ C: EPS Q YoY ≥ 25%          (SEC EDGAR 10-Q)
   ├─ A: EPS Anual ≥ 25%          (SEC EDGAR 10-K)
   ├─ N: Cerca de máximo 52s + vol (OHLCV)
   ├─ S: Buyback / shares ↓        (SEC EDGAR)
   ├─ L: Outperforma SPY 52s       (OHLCV vs benchmark)
   ├─ I: Tenencia institucional     (no disponible free tier → None)
   └─ M: Mercado en Stage 2        (Weinstein sobre SPY)

6. Score Combinado
   └─► Weinstein (50 pts) + CAN SLIM (50 pts) = 0-100

7. Persistencia (PostgreSQL)
   ├─► opportunities (score + criterios por día)
   └─► price_snapshots (OHLCV semanal histórico)

8. Explicación IA (solo si score ≥ 40, máx 50/corrida)
   └─► Claude Sonnet → texto en español → explanations table
```

### 3.3 Modelo de Datos

```
tickers
  id | symbol | name | sector | universe | is_active
  ──────────────────────────────────────────────────
  1  | AAPL   | Apple Inc. | Technology | sp500 | true

price_snapshots                          ← histórico OHLCV
  id | ticker_id | date | open | high | low | close | volume
  (UniqueConstraint: ticker_id + date)

opportunities                            ← 1 fila por ticker/día
  id | ticker_id | run_date
  weinstein_stage | weinstein_transition | weeks_in_stage
  weinstein_ma_slope_pct | weinstein_relative_volume
  canslim_criteria (JSON) | canslim_score
  combined_score | risk_bucket
  (UniqueConstraint: ticker_id + run_date)

explanations                             ← texto IA por ticker/día
  id | ticker_id | run_date | text | model_used | combined_score_at_generation
```

---

## 4. Scoring System

### 4.1 Weinstein (0-50 puntos)

| Condición | Puntos |
|---|---|
| Stage 2 (avance) | 30 |
| Stage 1 (base, acumulación) | 10 |
| Stage 3 (techo) | 5 |
| Stage 4 (declive) | 0 |
| Bonus: transición 1→2 con volumen | +15 |
| Bonus: semanas en Stage 2 (máx 5) | +0 a +5 |

### 4.2 CAN SLIM (0-50 puntos)

Puntos distribuidos equitativamente entre criterios verificables (se excluyen los `None`):

| Criterio | Fuente | Umbral |
|---|---|---|
| C — EPS Trimestral YoY | SEC EDGAR | ≥ 25% |
| A — EPS Anual | SEC EDGAR | ≥ 25% |
| N — Nuevo máximo + volumen | OHLCV | Cierre ≥ 98% del máx 52s + vol 1.5x |
| S — Buyback / Supply ↓ | SEC EDGAR | Shares -1% en 4 trimestres |
| L — Leader (fuerza relativa) | OHLCV vs SPY | Retorno 52s > benchmark |
| I — Institucional | No disponible (free tier) | 15%-90% |
| M — Market direction | Weinstein SPY | SPY en Stage 2 |

### 4.3 Risk Bucket

| Score | Bucket |
|---|---|
| ≥ 70 | 🔴 Alto (alta convicción, más volátil) |
| 50-69 | 🟡 Medio |
| < 50 | 🟢 Bajo |

---

## 5. Stack Tecnológico

### Backend
| Componente | Tecnología | Notas |
|---|---|---|
| API | FastAPI + Uvicorn | Python 3.11 |
| ORM | SQLAlchemy 2.0 | Modelos tipados |
| Scheduler | APScheduler | Cron 06:00 UTC diario |
| Config | Pydantic Settings | Variables de entorno |
| IA | Anthropic Claude Sonnet 4.6 | Explicaciones en español |

### Data Sources
| Fuente | Datos | Límites |
|---|---|---|
| Alpaca Markets (free) | OHLCV histórico (IEX feed) | 200 req/min |
| SEC EDGAR XBRL | EPS + Shares Outstanding | ~10 req/s |
| Wikipedia | Universo S&P500 + Nasdaq100 | Sin límite |

### Infraestructura
| Servicio | Plan | Coste aprox. |
|---|---|---|
| Railway (backend + DB) | Hobby | ~$5/mes |
| Vercel (frontend) | Free | Gratis |
| Alpaca (datos) | Free tier | Gratis |
| SEC EDGAR | Público | Gratis |
| Anthropic API | Pay-per-use | ~$8/mes |

**Coste total estimado: ~$13/mes**

---

## 6. Lo Implementado en Esta Sesión

### 6.1 Migración a Alpaca Markets API

**Problema:** Yahoo Finance bloqueaba IPs de datacenter → screener solo podía correr en local, sin histórico automático.

**Solución:**
- `AlpacaDataSource` reemplaza `YFinanceDataSource` para OHLCV
- Auto-selección: si `ALPACA_API_KEY` + `ALPACA_SECRET_KEY` → Alpaca; si no → yfinance fallback
- Alpaca corre en Railway sin bloqueos → el cron de las 06:00 UTC ya acumula histórico automáticamente

### 6.2 EPS desde SEC EDGAR (sin Yahoo)

**Problema:** Los fundamentales (EPS para criterios C y A) venían de Yahoo Finance, también bloqueado.

**Solución:**
- `get_edgar_data(symbol)` extrae EPS de `us-gaap/EarningsPerShareDiluted` del endpoint XBRL de SEC EDGAR
- Misma infra que ya teníamos para shares outstanding (criterio S) → reutilización limpia
- 1 sola petición HTTP por ticker extrae supply signal + EPS (antes eran 2 peticiones)

### 6.3 Optimización de llamadas SEC EDGAR

```
ANTES:  get_supply_signal(symbol)  →  HTTP GET companyfacts
        get_eps_series(symbol)     →  HTTP GET companyfacts (misma URL, doble gasto)
        Total: 2 × 604 = 1.208 peticiones/corrida

AHORA:  get_edgar_data(symbol)     →  HTTP GET companyfacts (única)
        ├─► _extract_supply(facts)
        └─► _extract_eps(facts)
        Total: 1 × 604 = 604 peticiones/corrida
        + delay 120ms entre llamadas (~8 req/s, dentro del límite SEC)
```

### 6.4 Otros cambios

- **Endpoint de diagnóstico** `GET /api/admin/diagnose` — verifica en Railway que Alpaca, SEC EDGAR y el universo funcionan correctamente
- **Error handling** en el thread del screener — errores quedan en logs de Railway en vez de fallar silenciosamente
- **Texto criterio I** — eliminada referencia incorrecta a "yfinance" en el mensaje

---

## 7. Roadmap — Próximos Pasos

### Prioridad Alta

#### 🔔 Alertas Telegram (estimado: 1 sesión)
Resumen diario automático a las 07:00 UTC con los top 5 tickers (score ≥ 70).

```
Implementación:
├── Bot de Telegram (@BotFather → token)
├── Chat ID del canal/grupo de destino
├── Nueva función en run_screener.py: _send_telegram_summary()
└── Llamada tras _generate_explanations()

Mensaje ejemplo:
🏆 StageWise Daily — 26 Jun 2026
────────────────────────
1. ASML  88pts  Stage 2 🔴
2. AVGO  83pts  Stage 2 🔴
3. GLW   83pts  Stage 2 🔴
4. JNJ   83pts  Stage 2 🟡
5. FRT   83pts  Stage 2 🟢
────────────────────────
Ver feed completo: stagewise.app
```

#### 📈 Histórico de Scores en UI (estimado: 1-2 sesiones)
Gráfico de evolución del score por ticker en el tiempo (los datos ya se acumulan en `opportunities`).

```
Implementación:
├── Nuevo endpoint: GET /api/tickers/{symbol}/history
│   └─► Devuelve array de {run_date, combined_score, weinstein_stage}
├── Frontend: componente LineChart (recharts o similar)
└── Visible en el detalle de cada ticker del feed
```

### Prioridad Media

#### 🌐 Dominio propio
- `stagewise.app` o `stagewise.es`
- Apuntar Vercel al dominio custom (5 minutos de config)
- Estimado: 30 minutos + coste dominio (~$12/año)

#### 🏠 Landing Page (antes del feed)
Una página de aterrizaje que explique qué es StageWise antes de mostrar el feed:
- Qué es el Stage Analysis / CAN SLIM (educativo)
- CTA: "Ver el feed de hoy"
- Sin registro requerido en MVP

### Prioridad Baja / Fase 2

#### 💹 Criterio I completo (Institutional Sponsorship)
- Requiere agregar Form 13F de SEC (dataset bulk trimestral, varios GB)
- Alternativa: Alpaca paid tier que incluye datos de institucionales

#### 🌍 Ampliar universo
- Añadir Russell 2000 (small caps) → ~1.500 tickers adicionales
- Mercados europeos (si Alpaca lo soporta)

#### 👤 Registro de usuarios y personalización
- Guardar tickers favoritos
- Filtros personalizados por sector, stage, score mínimo

---

## 8. Comandos Útiles

### Lanzar screener manualmente (local)
```bash
cd backend
# Universo completo
python -m app.jobs.run_screener --delay 0.3

# Solo algunos tickers (debug)
python -m app.jobs.run_screener --tickers AAPL,MSFT,NVDA --delay 0

# Limitar a N tickers
python -m app.jobs.run_screener --limit 20 --delay 0.3
```

### Lanzar screener en Railway (vía API)
```bash
# Universo completo
curl -X POST "https://invest-feed-mvp-production.up.railway.app/api/admin/run-screener" \
  -H "X-Admin-Secret: stagewise-admin-2026"

# Limitado a N tickers (para test)
curl -X POST "https://invest-feed-mvp-production.up.railway.app/api/admin/run-screener?limit=10" \
  -H "X-Admin-Secret: stagewise-admin-2026"
```

### Diagnóstico de Railway
```bash
curl "https://invest-feed-mvp-production.up.railway.app/api/admin/diagnose" \
  -H "X-Admin-Secret: stagewise-admin-2026"
```

### Variables de entorno necesarias (Railway backend)
```
DATABASE_URL          = postgresql://... (auto-configurado por Railway)
ANTHROPIC_API_KEY     = sk-ant-...
ADMIN_SECRET          = stagewise-admin-2026
ALPACA_API_KEY        = PK...
ALPACA_SECRET_KEY     = ...
SCREENER_SCHEDULE_ENABLED = true
```

---

## 9. Decisiones de Arquitectura (no re-discutir)

| Decisión | Alternativas descartadas | Motivo |
|---|---|---|
| Alpaca free (IEX feed) para OHLCV | yfinance, Polygon, Alpha Vantage | Sin bloqueo en Railway, gratis, estable |
| SEC EDGAR XBRL para EPS | Yahoo Finance, FMP, Alpaca paid | Gratis, oficial, ya teníamos la infra |
| Screener corre en Railway vía cron | Solo local, GitHub Actions | Autonomía sin intervención manual |
| Score: 50pts Weinstein + 50pts CAN SLIM | Pesos diferentes | Equilibrio entre técnico y fundamental |
| `canslim_criteria` como JSON en BD | Columnas separadas | Flexibilidad para añadir criterios |
| `value=None` cuando no verificable | `value=False` | No fingir cobertura de datos inexistente |
| Explicaciones solo top 50 (umbral ≥40) | Todas las oportunidades | Control de coste de API Anthropic |

---

*Documento generado con Claude Code — StageWise v0.1 MVP*
