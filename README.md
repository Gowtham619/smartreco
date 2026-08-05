# SmartReco

A behavioral AI recommendation agent for a course marketplace. It tracks what a user does
(views, searches, clicks, time spent), reasons about their interests with a LangGraph agent,
retrieves the most relevant courses via RAG over a Qdrant vector store, and generates a
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
                                          retrieve (Mesh embeddings ──▶ Qdrant
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
the same row into Qdrant (embedded through Mesh). If the vector write fails, the SQL row
is marked `sync_status=error` (never crashes the request) and an admin "Resync vector
store" action retries it — verified live by breaking the Mesh key and watching product
rows land in SQL with `error` status, then clearing after a successful resync.

**Vector store note:** this originally used Chroma. Its embedded mode's native `hnswlib`
extension crashed with `SIGILL` on Render's free-tier CPU — a virtualized-host bug where
`cpuid` over-reports AVX-512 support the hypervisor can't actually execute, not anything
specific to how we used it. Qdrant was swapped in instead: its embedded "local mode" is
pure Python (no native extension, so no equivalent crash risk) for local dev, and a real
Qdrant Cloud instance is used in production, which also solves Render's ephemeral-disk
problem for vector data. See the docstring in `app/services/vector_store.py` for detail.

## What's implemented

**Foundation**
- Email/password auth (bcrypt + signed session cookie), two roles: `user` and `admin`.
- SQLite schema: `users`, `products`, `events`, `recommendations`, `recommendation_items`,
  `recommendation_state` (the last one tracks per-user trigger/cooldown bookkeeping).

**Product management with dual-write**
- Admin CRUD UI at `/admin/products` (create/edit/delete), writing to SQLite + Qdrant.
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
- Retrieval is grounded in the actual catalog (Qdrant top-k + category metadata filter);
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
  `OpenAIEmbeddings`, so setting `LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY` traces the
  full LangGraph run in LangSmith with zero extra instrumentation code — each run is also
  tagged with the trigger reason and `user_id` (see `recommendation_service._run_generation`)
  so traces are filterable by *why* a recommendation fired and for *whom*, not just a wall
  of identically-named node runs. Note: LangSmith's SDK reads these vars straight from the
  process environment, not through our own config — `app/config.py` calls `load_dotenv()`
  specifically so values in `.env` actually reach it (pydantic-settings' own env-file
  loading only populates our internal `Settings` object, not `os.environ`).
- ⭐ **Retrieval polish** — category metadata filtering at retrieval time, a broaden-and-
  retry loop when the filtered query comes back thin, and an LLM rerank/reason pass over
  the retrieved candidates before the narrative is written.

## Setup

Requires Python 3.13 (that's what this was built and verified against; not a hard
requirement of the current dependencies the way it was when this used Chroma).

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

No separate vector DB setup needed for local dev — leaving `QDRANT_URL` unset in `.env`
uses `qdrant-client`'s embedded local mode (a local file-backed store under `./data/qdrant`,
no server required).

Visit `http://localhost:8010`. Log in as the seeded admin with `ADMIN_EMAIL` /
`ADMIN_PASSWORD` from `.env` to manage the catalog at `/admin/products`, or register a
normal account to browse and get recommendations at `/recommendations`.

Note: both chat and embedding calls go through Mesh's **paid** models (there is currently
no free-tier embedding model on Mesh), so your Mesh account needs a positive balance for
live retrieval/generation to succeed — otherwise the agent still runs end-to-end but falls
back to a generic "explore more" recommendation instead of a real one. At current Mesh
pricing this app costs roughly $0.0007 per recommendation generation and a fraction of a
cent to embed the whole sample catalog — a $1-5 top-up covers thousands of test runs.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite runs against an isolated temp SQLite DB/Qdrant local-mode dir (never your real `.env`
values) and never calls Mesh — LLM/embedding calls are monkeypatched per-test. It covers
the parts most likely to hide real bugs: dual-write success/failure/resync, the
event-threshold + cooldown trigger gating, the retrieve→evaluate→retry loop, and the
grounding guard that drops any LLM-recommended product id not actually in the retrieved
candidate set.

### Key environment variables (see `.env.example` for the full list)

| Variable | Purpose |
|---|---|
| `MESH_API_KEY`, `MESH_BASE_URL` | Mesh gateway credentials/endpoint (mandatory for all LLM calls) |
| `MESH_CHAT_MODEL`, `MESH_EMBEDDING_MODEL`, `MESH_EMBEDDING_DIM` | Models used for generation/retrieval, and the embedding vector size |
| `QDRANT_URL`, `QDRANT_API_KEY` | Point at a real Qdrant server/Cloud instance; leave blank for local embedded mode |
| `RECOMMENDATION_EVENT_THRESHOLD`, `RECOMMENDATION_FIRST_EVENT_THRESHOLD`, `RECOMMENDATION_COOLDOWN_MINUTES` | Trigger tuning |
| `SCHEDULER_REFRESH_MINUTES`, `DIGEST_HOUR`, `DIGEST_MINUTE` | Scheduler cadence |
| `SMTP_*` | Optional real email delivery for the daily digest |
| `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, `LANGSMITH_ENDPOINT` | Optional LangSmith tracing |

## Deploying (Render, free tier)

`render.yaml` defines the service as a Render Blueprint:

1. Create a free [Qdrant Cloud](https://cloud.qdrant.io) cluster and grab its URL + API key.
   (Required for deployment — see the vector store note above for why local-mode Chroma,
   and by extension anything relying on a native vector-index extension, isn't safe to run
   on Render's free-tier CPU. Qdrant Cloud's free tier is unaffected since it's a remote
   server, not code running inside your app's container.)
2. Push this repo to GitHub (already done if you're reading this from the repo).
3. On Render: New → Blueprint → connect the repo → Render reads `render.yaml` automatically.
4. Render will prompt for the secrets not stored in the blueprint: `MESH_API_KEY`,
   `ADMIN_PASSWORD`, `QDRANT_URL`, and `QDRANT_API_KEY`. `SECRET_KEY` is auto-generated.
5. Deploy. `AUTO_SEED=true` is set in the blueprint, so the app seeds its own admin user +
   sample catalog on every boot.

**Caveat:** Render's free web services use an ephemeral filesystem — SQLite data (under
`./data`) does not reliably survive a redeploy or a spin-down/spin-up cycle. Vector data is
fine (it lives in Qdrant Cloud, not on Render's disk), but SQLite is why auto-seeding on
startup exists: the app self-heals back to a working demo state instead of booting with an
empty catalog, though any user accounts/events/recommendations created during a session are
lost when the instance recycles. For full persistence, either upgrade to a Render paid disk,
or deploy to a host with a persistent volume (e.g. Fly.io).

## Project layout

See inline comments in `app/main.py` for the router wiring. Key modules:

- `app/agent/` — the LangGraph recommendation agent (state, nodes, graph, prompts)
- `app/services/vector_store.py` — Qdrant wrapper (Mesh-embedded; local mode for dev, real Qdrant Cloud in production)
- `app/services/product_service.py` — dual-write create/update/delete + resync
- `app/services/recommendation_service.py` — trigger/cooldown/dedup logic, persistence
- `app/scheduler.py` — APScheduler jobs (refresh safety-net + daily digest)
- `static/js/tracker.js` — the non-blocking behavioral tracker

## CI

`.github/workflows/smartreco-checks.yml` runs the challenge's automated checks (syntax +
dependency presence) on every push. Add `MESH_API_KEY` and `SUBMISSION_TOKEN` as GitHub
Actions secrets (Settings → Secrets and variables → Actions) for it to run against your repo.
