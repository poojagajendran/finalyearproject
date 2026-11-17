# SHOPCART DEVELOPMENT TRACKER

AI-Powered Collaborative E-Commerce Platform with Multi-User Payment Authorization, Dynamic Payment Redistribution, and Fault-Tolerant Transaction Recovery.

---

## 📌 Phase Overview & Status

| Phase | Description | Status | Verification & Artifacts |
|---|---|---|---|
| **Phase 1** | Workspace & Infrastructure | ✅ Completed | Project directories, Docker Compose, Env templates, Python virtualenv |
| **Phase 2** | Database & Authentication | ✅ Completed | Models, Argon2 hashing, JWT cookies, User lookup & tests passing |
| **Phase 3** | Product Catalog & Shopping Cart | ✅ Completed | Catalog, Categories, Search, Cart management, Inventory locks & tests passing |
| **Phase 4** | SimBank Service | ✅ Completed | Standalone FastAPI bank, VPA/PIN, Funds-lock, Debit, Release, Refund, Signed HMAC webhooks & tests passing |
| **Phase 5** | Group Payment State Machine | ✅ Completed | 8 formal states, validated transitions, split calculation, human consent & tests passing |
| **Phase 6** | Payment Recovery & Reconciliation | ✅ Completed | Dynamic redistribution, isolation, compensating refunds, timeout recovery, idempotency & tests passing |
| **Phase 7** | AI Shopping Agent | ✅ Completed | Anthropic SDK / Tool calling, read/propose-only boundaries, structured responses & tests passing |
| **Phase 8** | Next.js Frontend | ⏳ Pending | App Router, Tailwind, shadcn/ui, 14 required screens |
| **Phase 9** | Real-Time Updates | ⏳ Pending | Webhooks, SSE / Polling, Live status progress indicators |
| **Phase 10** | Fault-Injection Testing & Evaluation | ✅ Completed | 27 fault scenarios, LOCK vs WALLET vs NAIVE benchmark, research reports generated |

---

## Phase Details & Task Breakdown

### Phase 1: Workspace & Infrastructure
- [x] Inspect existing workspace, runtimes, and system tools
- [x] Set up Python virtual environment (`.venv`) and verify dependencies
- [x] Create project layout (`backend/`, `simbank/`, `frontend/`, `experiments/`, `docker/`)
- [x] Configure `.env.example` and `.env` with dual-mode database support (PostgreSQL + SQLite fallback)
- [x] Create `docker-compose.yml` defining PostgreSQL 16 (pgvector), SimBank PostgreSQL, Redis 7, Backend, SimBank, Worker, and Frontend
- [x] Add PostgreSQL initializers and Dockerfiles
- [x] Initialize `DEVELOPMENT.md` and `README.md`

### Phase 2: Database & Authentication
- [x] SQLAlchemy 2 async database engine and async session factory
- [x] User model and migration scripts
- [x] Password hashing with Argon2id
- [x] JWT authentication with HTTP-only cookies
- [x] Auth endpoints: `/register`, `/login`, `/logout`, `/me`, `/users/by-handle/{handle}`, `/users/search`
- [x] Unit & integration tests for Auth (100% pass)

### Phase 3: Product Catalog & Shopping Cart
- [x] Product, Category, and Inventory models
- [x] Seed catalog data with realistic Indian e-commerce products (in paise)
- [x] Catalog search and filter endpoints
- [x] Shopping cart endpoints: add item, remove item, update quantity, clear cart
- [x] Server-side pricing recalculation and inventory check
- [x] Tests for Cart and Catalog operations (100% pass)

### Phase 4: SimBank Service
- [x] Separate FastAPI application with independent database
- [x] Bank account model with VPA (`user@simbank`), balance, and hashed PIN
- [x] Idempotent funds-lock endpoint (`/api/v1/bank/locks`)
- [x] Capture / Debit endpoint (`/api/v1/bank/debits`)
- [x] Release lock endpoint (`/api/v1/bank/releases`)
- [x] Refund endpoint (`/api/v1/bank/refunds`)
- [x] HMAC-SHA256 signature generation on webhook delivery
- [x] Automated seed accounts with test balances
- [x] Tests for SimBank financial operations (100% pass)

### Phase 5: Group Payment State Machine
- [x] State definition: `DRAFT`, `COLLECTING`, `RESPLIT_PENDING`, `COMMITTING`, `CONFIRMED`, `COMPENSATING`, `ABORTING`, `ABORTED`
- [x] Group purchase model, participants, and allocations
- [x] State transition engine with invariant checks
- [x] Split calculation: Equal split & Custom split (with remainder handling in paise)
- [x] Human participant authorization endpoint (PIN + SimBank Lock)
- [x] Group payment dashboard endpoints
- [x] State transition validation tests (100% pass)

### Phase 6: Payment Recovery & Reconciliation
- [x] Participant decline handling and trigger to `RESPLIT_PENDING`
- [x] Dynamic redistribution algorithm recalculating shares among remaining active participants
- [x] Revised participant consent tracking (explicit human approval required)
- [x] Isolated retries for transient failures
- [x] SAGA-style compensating refunds for partial debit failures
- [x] Two-phase commit / Lock-Commit protocol
- [x] Background reconciliation worker for network timeouts and unconfirmed webhooks
- [x] Recovery engine tests (100% pass)

### Phase 7: AI Shopping Agent
- [x] Anthropic SDK integration with tool-calling schema
- [x] Tool definitions: `search_products`, `get_product`, `view_cart`, `add_to_cart`, `remove_from_cart`, `prepare_checkout`, `get_group_status`, `offer_resolution`
- [x] Security boundary: Agent proposals only, cannot authorize debits or releases
- [x] Identity isolation: Current user identity bound to session, never LLM tool arguments
- [x] AI agent deterministic mode for offline testing and evaluation
- [x] Natural language interaction tests (100% pass)

### Phase 8: Next.js Frontend
- [ ] Next.js App Router project setup with TypeScript, Tailwind CSS, TanStack Query
- [ ] 14 required views:
  1. Landing Page
  2. Login
  3. Register
  4. Product Catalog
  5. Product Details
  6. Shopping Cart
  7. AI Shopping Assistant
  8. Manual Group Checkout
  9. Approval Inbox
  10. Group Payment Dashboard
  11. SimBank Authorization Screen
  12. Payment Recovery Screen
  13. Order History
  14. Admin Fault-Injection Dashboard
- [ ] E-commerce styling, progress bars, responsive UI, toast notifications

### Phase 9: Real-Time Updates
- [ ] SSE or WebSocket updates for group checkout state changes
- [ ] Polling fallback for resilient dashboard updates
- [ ] Instant visual notification on participant approvals or declines

### Phase 10: Fault-Injection Testing & Evaluation
- [x] Experiment test harness with 27 fault scenarios:
  - Network timeouts during lock/debit
  - SimBank insufficient funds
  - Participant decline midway
  - Redis restart / temporary crash
  - Webhook drop / delayed delivery
  - Duplicate webhook delivery
  - Concurrent approval race conditions
- [x] Comparative benchmark: LOCK vs WALLET vs NAIVE
- [x] Metrics: Consistency (0 double debits), Recovery rate (100%), Average latency (ms)
- [x] Automated markdown experiment report generator (`experiments/results/EXPERIMENT_REPORT.md`)
