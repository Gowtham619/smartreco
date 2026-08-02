# SmartReco

A behavioral AI recommendation agent for a course marketplace. It tracks what a user does
(views, searches, clicks, time spent), reasons about their interests with a LangGraph agent,
retrieves the most relevant courses via RAG over a Chroma vector store, and generates a
persuasive, catalog-grounded recommendation that refreshes as behavior changes.

Built for the SmartReco Build Challenge 2026.

## Architecture

```
Browser (tracker.js)                FastAPI backend
  batches events  ──POST /api/events/batch──▶  bulk insert (SQLite)
  (sendBeacon /                                      │
   fetch keepalive,                        background task: cheap threshold
   non-blocking)                           + cooldown check (no LLM call
                                            on every event)
                                                      │ triggers when crossed
                                                      ▼
                                        LangGraph recommendation agent
                                        analyze_activity (no LLM, aggregates
                                          recent events into an interest profile)
                                            │
                                            ▼
                                          retrieve (Mesh embeddings ──▶ Chroma
                                          top-k, metadata-filtered by category)
                                            │
                                            ▼
                                    evaluate_retrieval ──(too few hits, retry once)──▶ retrieve
                                            │ (enough hits)
                                            ▼
                                          generate (single Mesh chat completion,
                                          JSON-structured: narrative + ranked,
                                          grounded picks with per-course reasons)
                                            │
                                            ▼
                                Recommendation + RecommendationItem rows (cached,
                                served instantly on /recommendations until the
                                next trigger fires)
```

Admin product CRUD dual-writes: every create/update writes to SQLite first, then upserts
the same row into Chroma (embedded through Mesh). If the vector write fails, the SQL row
is marked `sync_status=error` (never crashes the request) and an admin "Resync vector
store" action retries it — verified live by breaking the Mesh key and watching product
rows land in SQL with `error` status, then clearing after a successful resync.

## What's implemented

**Foundation**
- Email/password auth (bcrypt + signed session cookie), two roles: `user` and `admin`.
- SQLite schema: `users`, `products`, `events`, `recommendations`, `recommendation_items`,
  `recommendation_state` (the last one tracks per-user trigger/cooldown bookkeeping).

**Product management with dual-write**
- Admin CRUD UI at `/admin/products` (create/edit/delete), writing to SQLite + Chroma.
- `sync_status` (`synced`/`pending`/`error`) surfaced in the UI, with a one-click resync.

**Behavioral tracking**
- `static/js/tracker.js`: buffers events in memory, flushes on a 5s timer, when the buffer
  hits 10 events, or on page hide/unload via `navigator.sendBeacon` — never blocks
  navigation. No raw mousemove/scroll spam; only discrete signals (page/product view,
  search, click) plus a coarse time-on-page heartbeat.
- `POST /api/events/batch` bulk-inserts and hands off trigger evaluation to a FastAPI
  `BackgroundTask`, so the response returns immediately.

**Agentic recommendation engine**
- LangGraph `StateGraph` with a real conditional edge: `retrieve` → `evaluate_retrieval`
  → (retry once with a broadened query if too few results) → `generate`.
- Retrieval is grounded in the actual catalog (Chroma top-k + category metadata filter);
  the generation step validates that every recommended `product_id` was actually
  retrieved, dropping anything hallucinated.
- One LLM call does both the ranking/reasoning ("retrieval polish") and the persuasive
  narrative — efficient, and the copy is written using the user's real activity
  (categories, searches, viewed titles), not generic marketing text.

**Efficiency & production thinking**
- No LLM call fires on every event. A recommendation only regenerates when a user crosses
  an event-count threshold (default 5, or 3 for a first-ever recommendation) **and** a
  cooldown window (default 5 min) has passed — checked with cheap SQL counts before any
  Mesh call.
- A `generating` flag per user prevents duplicate concurrent generations.
- An APScheduler safety-net job (default every 20 min) catches activity that trickled in
  without crossing the real-time trigger.
- Every Mesh call in the agent is wrapped so a transient failure (bad key, rate limit,
  outage) degrades to a friendly fallback recommendation instead of crashing — verified
  live against a real `spend_limit_exceeded` response from Mesh.

**Bonuses implemented**
- ⭐ **Structured agent framework** — LangGraph, as described above (not a single prompt).
- ⭐ **Scheduled proactive delivery** — APScheduler cron job (`DIGEST_HOUR`/`DIGEST_MINUTE`,
  default 17:00 UTC) emails a daily digest to every user with activity that day. Real
  SMTP if configured; otherwise the email body is logged so the app stays runnable
  without mail credentials.
- ⭐ **Observability** — the agent's Mesh calls go through `langchain_openai.ChatOpenAI` /
  `OpenAIEmbeddings`, so setting `LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY` traces
  the full LangGraph run in LangSmith with zero extra instrumentation code.
- ⭐ **Retrieval polish** — category metadata filtering at retrieval time, a broaden-and-
  retry loop when the filtered query comes back thin, and an LLM rerank/reason pass over
  the retrieved candidates before the narrative is written.

## Setup

Requires Python 3.13 (chromadb's dependencies don't yet build on 3.14).

```bash
cd smartreco
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env: set MESH_API_KEY to your real Mesh key (rsk_...), and anything else you want to change
python -m app.seed        # creates the admin user + an 18-course sample catalog (dual-written)
uvicorn app.main:app --reload --port 8010
```

Visit `http://localhost:8010`. Log in as the seeded admin with `ADMIN_EMAIL` /
`ADMIN_PASSWORD` from `.env` to manage the catalog at `/admin/products`, or register a
normal account to browse and get recommendations at `/recommendations`.

Note: both chat and embedding calls go through Mesh's **paid** models (there is currently
no free-tier embedding model on Mesh), so your Mesh account needs a positive balance for
live retrieval/generation to succeed — otherwise the agent still runs end-to-end but falls
back to a generic "explore more" recommendation instead of a real one.

### Key environment variables (see `.env.example` for the full list)

| Variable | Purpose |
|---|---|
| `MESH_API_KEY`, `MESH_BASE_URL` | Mesh gateway credentials/endpoint (mandatory for all LLM calls) |
| `MESH_CHAT_MODEL`, `MESH_EMBEDDING_MODEL` | Models used for generation and retrieval |
| `RECOMMENDATION_EVENT_THRESHOLD`, `RECOMMENDATION_FIRST_EVENT_THRESHOLD`, `RECOMMENDATION_COOLDOWN_MINUTES` | Trigger tuning |
| `SCHEDULER_REFRESH_MINUTES`, `DIGEST_HOUR`, `DIGEST_MINUTE` | Scheduler cadence |
| `SMTP_*` | Optional real email delivery for the daily digest |
| `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT` | Optional LangSmith tracing |

## Project layout

See inline comments in `app/main.py` for the router wiring. Key modules:

- `app/agent/` — the LangGraph recommendation agent (state, nodes, graph, prompts)
- `app/services/vector_store.py` — Chroma wrapper (Mesh-embedded, never Chroma's default embedder)
- `app/services/product_service.py` — dual-write create/update/delete + resync
- `app/services/recommendation_service.py` — trigger/cooldown/dedup logic, persistence
- `app/scheduler.py` — APScheduler jobs (refresh safety-net + daily digest)
- `static/js/tracker.js` — the non-blocking behavioral tracker

## CI

`.github/workflows/smartreco-checks.yml` runs the challenge's automated checks (syntax +
dependency presence) on every push. Add `MESH_API_KEY` and `SUBMISSION_TOKEN` as GitHub
Actions secrets (Settings → Secrets and variables → Actions) for it to run against your repo.
