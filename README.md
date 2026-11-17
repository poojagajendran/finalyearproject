# SHOPCART – AI-Powered Collaborative E-Commerce Platform

ShopCart is a production-grade, research-focused collaborative e-commerce platform featuring multi-user payment authorization, dynamic payment redistribution, and fault-tolerant transaction recovery.

Built for final-year research evaluation, ShopCart demonstrates provable financial consistency, zero duplicate debits, and resilient state transitions across network failures and participant dropouts.

---

## Architecture Overview

```
                                      +--------------------+
                                      |   Next.js 14+ UI   |
                                      | (14 Core Screens)  |
                                      +---------+----------+
                                                |
                                    REST / SSE  | JWT Cookies
                                                v
+------------------+                 +---------------------+                 +--------------------+
|  Anthropic AI    | <--- Tool Calls |  ShopCart Backend   | --------------> |   SimBank API      |
|  Shopping Agent  |                 |  (FastAPI / Python) |   Locked Holds  |  (Isolated Bank)   |
+------------------+                 +----------+----------+   Debits/Refunds+---------+----------+
                                                |                                      |
                         +----------------------+----------------------+               |
                         |                      |                      |               |
                         v                      v                      v               v
                +-----------------+    +-----------------+    +-----------------+ +-----------------+
                | PostgreSQL (16) |    |  Redis 7 Cache  |    |  arq Background | | PostgreSQL (16) |
                |  with pgvector  |    |   & Pub/Sub     |    |  Reconciliation | |  SimBank DB     |
                +-----------------+    +-----------------+    +-----------------+ +-----------------+
```

### Technology Stack
- **Frontend**: Next.js App Router, TypeScript, Tailwind CSS, TanStack Query, Lucide Icons.
- **Backend**: Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2 (Async), Alembic.
- **SimBank**: Standalone FastAPI microservice simulating UPI VPA holds, debits, releases, refunds, and HMAC-signed webhooks.
- **Databases**: PostgreSQL 16 (pgvector), Redis 7 (or SQLite/in-memory fallback for local environments).
- **AI Agent**: Anthropic Python SDK with structured tool calling and security boundaries (read/propose only).
- **Testing**: pytest, pytest-asyncio, Hypothesis property-based testing.

---

## Monetary System & Security Guarantees
- **Integer Paise Representation**: All prices, cart values, and payment amounts are stored and calculated strictly in integer paise (`₹1.00 = 100 paise`), avoiding IEEE 754 floating-point inaccuracies.
- **LOCK Strategy (Zero Escrow Risk)**: Funds remain securely in user accounts at SimBank under an authorized hold until the commit phase. ShopCart never holds or pools user funds.
- **Human Payment Gate**: The AI agent is architecturally blocked from initiating or authorizing financial transactions. Only authenticated human PIN entry can approve holds and debits.
- **Two-Phase Commit (2PC) & Compensating Sagas**: If any participant debit fails permanently during commit, all previously debited participants receive automated compensating refunds.

---

## State Machine
The group purchase state transitions through 8 strictly validated states:
1. `DRAFT`: Group initialized, participants invited, cart items attached.
2. `COLLECTING`: Split finalized; awaiting individual participant PIN authorizations.
3. `RESPLIT_PENDING`: A participant declined or expired; dynamic redistribution recalculates shares.
4. `COMMITTING`: All participants locked funds; atomic debit execution in progress.
5. `CONFIRMED`: All debits succeeded; order created and inventory committed.
6. `COMPENSATING`: Partial debit failure occurred; executing compensating refunds and releasing holds.
7. `ABORTING`: Cancellation initiated by host or unresolvable failure.
8. `ABORTED`: Final terminal state; all holds released and refunded.

---

## Quick Start

### 1. Docker Compose (Full Stack)
```bash
docker compose up --build
```
- **ShopCart Frontend**: [http://localhost:3000](http://localhost:3000)
- **ShopCart Backend API**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **SimBank API**: [http://localhost:8001/docs](http://localhost:8001/docs)

### 2. Standalone Local Development
Activate the virtual environment and launch backend services:
```bash
# Backend
.\.venv\Scripts\uvicorn backend.app.main:app --port 8000 --reload

# SimBank
.\.venv\Scripts\uvicorn simbank.app.main:app --port 8001 --reload

# Frontend
cd frontend && npm run dev
```

---

## Project Structure
```
├── backend/                  # ShopCart FastAPI backend
│   ├── app/
│   │   ├── api/              # API Route handlers (auth, cart, groups, payments, ai)
│   │   ├── core/             # Database, security, config
│   │   ├── models/           # SQLAlchemy async models
│   │   ├── schemas/          # Pydantic v2 schemas
│   │   ├── services/         # State machine, payment recovery, AI service
│   │   └── workers/          # arq reconciliation background workers
│   └── Dockerfile
├── simbank/                  # Isolated bank simulator
│   ├── app/                  # VPA accounts, holds, debits, webhooks
│   └── Dockerfile
├── frontend/                 # Next.js 14 App Router UI
│   ├── src/
│   │   ├── app/              # 14 App pages & layouts
│   │   ├── components/       # UI components & design system
│   │   └── lib/              # API client & state management
│   └── Dockerfile
├── experiments/              # 27 Fault-injection scenarios & benchmark harness
├── docker/                   # Postgres init scripts & configurations
├── docker-compose.yml        # Orchestrates the 7 services
├── DEVELOPMENT.md            # Detailed phase tracking
└── README.md
```
