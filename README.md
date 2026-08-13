<div align="center">

# EvidenceAI

## AI Investigation & Evidence Intelligence

An evidence-grounded AI investigation platform that researches claims, retrieves
sources, extracts supporting and contradicting evidence, challenges conclusions,
and preserves provenance — end to end, in the browser.

### Try the live demo

[![Live Demo](https://img.shields.io/badge/LIVE%20DEMO-Visit%20the%20app-009688?style=for-the-badge&logo=railway&logoColor=white)](https://ai-investigation-engine-production.up.railway.app/dashboard)

`https://ai-investigation-engine-production.up.railway.app/dashboard`

![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.141-009688?logo=fastapi&logoColor=white)
![Tests](https://img.shields.io/badge/tests-199%20passing-green)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)
[![CI](https://github.com/Manal5664/AI-Investigation-Engine/actions/workflows/test.yml/badge.svg)](https://github.com/Manal5664/AI-Investigation-Engine/actions/workflows/test.yml)

The public demo needs **no API key** and makes **no billable calls**.

</div>

---

## Project overview

EvidenceAI turns a question into a bounded, traceable investigation. Every step
is typed, validated, and recorded so a reviewer can follow exactly which source
produced which passage of evidence.

```text
Question
  → AI Investigation Plan
  → Research Provider (mock | Gemini)
  → Source Normalization
  → Evidence Extraction
  → Conflict Detection
  → Devil's Advocate
  → RAG + GraphRAG
  → Evidence-grounded Synthesis
```

> **EvidenceAI does not issue an absolute truth verdict.** It reports the
> completeness and consistency of the evidence picture, the strength of
> supporting and contradicting evidence, and unresolved conflicts. Deciding what
> is "true" stays with the human reviewer.

Everything works offline out of the box with deterministic mock providers, so a
reviewer needs no API key to evaluate the platform. Real Google Gemini
integrations are opt-in and clearly labeled.

---

## Live demo — Portfolio Demo Mode

The public Railway deployment intentionally runs in **Portfolio Demo Mode**:

- **Deterministic mock providers only** (`LLM_PROVIDER`, `SEARCH_PROVIDER`,
  `EVIDENCE_PROVIDER`, `EMBEDDING_PROVIDER`, `GRAPH_EXTRACTION_PROVIDER`,
  `VISION_PROVIDER` = `mock`; stores and persistence = `in_memory`).
- **No paid Gemini or Google Search APIs are required** — nothing to configure,
  nothing billable, nothing to leak.
- **`.example` sources are synthetic demo sources, not real citations.** Every
  response is labeled (`provider_used: "mock"`) so mock output is never mistaken
  for a real citation.
- **Real Gemini/provider integrations remain available in the architecture.**
  Set `SEARCH_PROVIDER=gemini_grounded` plus a real `GEMINI_API_KEY` and the
  same endpoints switch to live grounded search — no code change needed.

See [docs/demo-mode.md](docs/demo-mode.md) for the full demo-mode configuration
and the verified endpoint list.

---

## Key features

- **Agentic investigation workflow** — a bounded, observable orchestrator
  (planner → research → evidence → critic → synthesis) with a typed replay log
  and no runaway tool loops.
- **Evidence extraction with provenance** — verbatim passages keep source ID,
  URL, hash, and extraction metadata; source credibility is scored heuristically
  (never as truth).
- **Conflict detection & Devil's Advocate** — surfaces supporting vs.
  contradicting evidence and deliberately challenges the conclusion.
- **RAG** — chunking, embedding, provenance-checked retrieval, duplicate-safe
  indexing behind a `VectorStore` interface.
- **GraphRAG** — entities/relations extracted from sources, stored in a graph,
  and combined with vector retrieval during investigation.
- **Multimodal documents** — PDF, DOCX, TXT/Markdown, and images via validated
  uploads, page-preserving extraction, and a pluggable vision provider.
- **Vendor-neutral LLM layer** — a single async provider contract with mock and
  official Google Gemini adapters (planning, grounding, evidence, embeddings,
  vision, graph).
- **Production FastAPI engineering** — versioned `/api/v1`, strict Pydantic
  schemas, typed errors, request IDs, structured logging, health/readiness
  endpoints, env-based settings.
- **Browser case workspace** — a dashboard, investigation, documents, RAG, and
  graph UI reading live data from the same engine as the API.
- **PostgreSQL persistence** — SQLAlchemy + Alembic behind a provider-neutral
  repository interface, with an in-memory fallback for offline work.

### Feature matrix

| Feature | Status |
| --- | --- |
| FastAPI API (versioned `/api/v1`) | Implemented |
| Agentic workflow (bounded planner → research → evidence → critic → synthesis) | Implemented |
| Gemini provider (planning, grounding, evidence, embeddings, vision, graph) | Opt-in, requires `GEMINI_API_KEY` |
| Search grounding | Implemented (Gemini Google Search tool, billed) |
| Evidence extraction (verbatim, provenance-preserving) | Implemented |
| Source provenance + credibility scoring | Implemented (heuristic, not truth) |
| Conflict detection (no truth verdict) | Implemented |
| Devil's Advocate / critic agent | Implemented |
| RAG (chunk → embed → retrieve) | Implemented (in-memory vector store) |
| GraphRAG (entities/relations + retrieval) | Implemented (in-memory graph store) |
| PDF / DOCX / TXT / Markdown / Image ingestion | Implemented |
| PostgreSQL persistence (SQLAlchemy + Alembic) | Implemented (opt-in) |
| Docker / Compose | Implemented |
| CI (GitHub Actions: tests + Docker build) | Implemented |
| Browser frontend dashboard | Implemented |
| Production authentication layer | Not implemented (see Limitations) |
| Rate limiting | Not implemented (documented guidance only) |
| Persistent vector / graph storage | Not implemented (in-memory only) |

---

## Architecture

The app is one FastAPI process that serves both the machine API (`/api/v1`) and
the browser case workspace (`/dashboard`, `/investigate`, `/documents`,
`/history`, `/rag`, `/graph`). Every provider sits behind a vendor-neutral
interface so mock and Gemini implementations are interchangeable at startup via
environment configuration.

```mermaid
flowchart LR
    B["Browser / API client"] --> F["FastAPI (single process)"]
    F --> A["Agentic investigation (bounded)"]
    A --> R["Research / Evidence (mock | Gemini)"]
    A --> K["RAG / GraphRAG (mock | Gemini embeddings)"]
    F --> P["Persistence (in-memory | PostgreSQL)"]
```

Full diagrams (system, investigation pipeline, deployment):
[docs/architecture.md](docs/architecture.md).

### Project structure

```text
AI-Investigation-Engine/
├── app/
│   ├── agents/        Bounded agentic workflow (orchestrator, research,
│   │                  evidence, critic, synthesis)
│   ├── ai/            LLM provider contract, mock + Gemini, prompt builders
│   ├── api/           FastAPI routers (/api/v1 machine API + UI routes)
│   ├── research/      Search provider contract, mock + Gemini grounded search
│   ├── evidence/      Evidence extraction providers (mock + Gemini)
│   ├── rag/           Embeddings, chunker, vector store, retrieval
│   ├── graph/         Graph store, builder, retriever, GraphRAG
│   ├── documents/     Upload validation + PDF/DOCX/TXT/Image extraction
│   ├── database/      Persistence (unit of work, repositories, ORM, Alembic)
│   ├── services/      Application services (research, RAG, graph, documents)
│   ├── schemas/       Strict Pydantic request/response models
│   ├── static/        Browser UI CSS/JS
│   ├── templates/     Browser UI Jinja2 templates
│   └── tests/         Browser-UI HTTP tests
├── tests/             Backend pytest suite (fully offline)
├── alembic/           Relational schema migrations
├── scripts/           Opt-in real-provider experiment scripts
├── docs/              Architecture, API examples, demo mode, release checklist
├── examples/          Fictional sample inputs (request JSON, TXT document)
├── Dockerfile
├── compose.yaml
└── requirements.txt / requirements-dev.txt
```

---

## Technology stack

**Backend:** Python 3.12, FastAPI, Pydantic v2, uvicorn

**AI:** google-genai (Gemini adapter), provider-neutral async contracts,
deterministic mock providers

**Retrieval:** chunking, embedding providers, cosine-similarity vector search
(in-memory), knowledge-graph retrieval

**Data:** SQLAlchemy 2, Alembic, psycopg (PostgreSQL), SQLite (local/testing)

**Documents:** pypdf, python-docx, Pillow (image extraction + vision provider)

**Frontend:** Jinja2 templates, vanilla JavaScript, Chart.js (CDN), Bootstrap

**Testing:** pytest, httpx/TestClient, GitHub Actions CI

**Deployment:** Docker, Docker Compose, Railway, healthcheck-ready image,
non-root user

---

## Screenshots

Screenshots are captured from the running app in offline demo mode — never
fabricated. See [docs/screenshots/README.md](docs/screenshots/README.md) for
exactly what to capture and how.

| Dashboard | New investigation | Investigation result |
| --- | --- | --- |
| ![dashboard](docs/screenshots/dashboard.png) | ![new-investigation](docs/screenshots/new-investigation.png) | ![investigation-result](docs/screenshots/investigation-result.png) |

| Documents | RAG search | Graph |
| --- | --- | --- |
| ![documents](docs/screenshots/documents.png) | ![rag-search](docs/screenshots/rag-search.png) | ![graph](docs/screenshots/graph.png) |

---

## Quick start

Requirements: Python 3.12, or Docker. No API key is required for the demo.

### Option A — local Python

```powershell
python -m pip install -r requirements.txt
python -m uvicorn app.main:app
```

Open `http://127.0.0.1:8000/dashboard` for the browser UI or
`http://127.0.0.1:8000/docs` for the OpenAPI docs.

### Option B — Docker Compose (PostgreSQL + app)

```powershell
docker compose up --build
```

Compose starts PostgreSQL, runs `alembic upgrade head` once, then serves the app
on `http://127.0.0.1:8000`. Default credentials in `compose.yaml` are
development-only placeholders.

### Option C — offline demo mode (no key, no billable calls)

```powershell
$env:APP_ENV_FILE = "examples/demo.env"
python -m uvicorn app.main:app
```

This pins every provider to the offline mock implementation. All results are
labeled as mock data. See [docs/demo-mode.md](docs/demo-mode.md) for exactly
what the demo covers and the verified endpoint list.

### Example flow to try in demo mode

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/research/mock `
  -H "Content-Type: application/json" `
  -d '{"investigation_query": "Research renewable energy storage", "depth": "deep"}'

curl -X POST http://127.0.0.1:8000/api/v1/rag/index `
  -H "Content-Type: application/json" `
  -d '{"sources": [{"source_id": "s1", "source_url": "https://agency.example/r", "title": "Report", "content": "The trial reported a twelve-hour discharge duration."}]}'

curl -X POST http://127.0.0.1:8000/api/v1/rag/search `
  -H "Content-Type: application/json" `
  -d '{"query": "twelve-hour discharge duration", "top_k": 3}'
```

---

## Testing

The suite runs fully offline (in-memory persistence and mock providers):

```powershell
python -m pytest -q
python -m compileall app
python -m pip check
```

Current verified suite: **199 passing tests** across providers, services, the
API, persistence, RAG, graph, documents, and the browser UI. Run
`python -m pytest -q` for the current count.

Migration consistency can be checked with:

```powershell
$env:DATABASE_URL="sqlite:///./ai_investigation.db"
alembic upgrade head
alembic check
```

---

## Deployment

Production requires `ENVIRONMENT=production`, `PERSISTENCE_PROVIDER=sqlalchemy`
with a PostgreSQL `DATABASE_URL`, and `GEMINI_API_KEY` when a Gemini provider is
selected. The startup validation fails fast otherwise.

```powershell
docker build -t evidenceai .
docker run -d -p 8000:8000 `
  -e ENVIRONMENT=production `
  -e PERSISTENCE_PROVIDER=sqlalchemy `
  -e DATABASE_URL="postgresql+psycopg://investigator:PASSWORD@dbhost:5432/ai_investigation" `
  -e GEMINI_API_KEY="<your-key>" `
  evidenceai
```

Or with the full local stack:

```powershell
docker compose up --build
```

The public deployment runs on Railway in Portfolio Demo Mode (see above).
Health endpoints: `GET /health`, `GET /health/live`, `GET /health/ready`.
Health responses never expose secrets or the full `DATABASE_URL`.

---

## Security

- **Secrets via environment** — `GEMINI_API_KEY` is read from the environment or
  a secret manager; `.env.example` ships empty placeholders and `.env` is
  gitignored. No secrets are committed.
- **Upload validation** — server-side extension/MIME allowlist, per-file byte
  cap, per-request count, filename sanitization, and SHA-256 duplicate
  detection. Browser-side validation is never trusted.
- **Request IDs** — every request carries an `X-Request-ID` (validated, else
  generated), returned on responses and stored for correlation; logs never
  include bodies, keys, or credentials.
- **Production error masking** — internal errors return a generic body; only
  `DEBUG=true` (development) reveals exception details.
- **Security headers** — `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: same-origin`, `X-Frame-Options: DENY`, and a
  Content-Security-Policy tuned for the CDN-based frontend.
- **Non-root Docker** — the image runs as `appuser` (uid 1000) and exposes only
  port 8000.
- **Production fast-fail** — startup rejects in-memory persistence, SQLite URLs,
  `DEBUG=true`, and Gemini providers without a key when `ENVIRONMENT=production`.

EvidenceAI makes no claim of third-party security certification.

---

## Honest limitations

- Gemini grounding (planning, grounded search, evidence, embeddings, vision,
  graph extraction) may require a paid quota/tier and can consume quota or incur
  charges. Every Gemini integration is opt-in.
- The vector store is **process-local and in-memory only**
  (`InMemoryVectorStore`); it is cleared on restart and not shared across
  workers. Persistent vector storage is a future enhancement.
- The graph store is **process-local and in-memory only**
  (`InMemoryGraphStore`); same restart/worker constraints.
- There is **no distributed worker queue**; agentic work runs synchronously
  inside the request and is bounded by request validation.
- There is **no full production authentication or authorization layer**. The
  `/api/v1/users` endpoint persists identity records only. Put the service
  behind an authenticating reverse proxy for any public deployment.
- The CSP currently includes `'unsafe-inline'` for `script-src` and
  `style-src` because templates use inline scripts/styles; tightening it needs
  nonces/hashes.
- The app is designed to run with a **single uvicorn worker** because vector
  and graph stores are process-local.
- The agentic, end-to-end research, and web-research endpoints use the
  `SEARCH_PROVIDER` configured at startup; `gemini_grounded` requires a real
  `GEMINI_API_KEY` and is otherwise unavailable offline, while `mock` works
  with no key.
- Source-quality scoring is **heuristic and not truth**; grounding metadata
  often lacks author/publish-date fields, which lowers scores.
- Evidence extraction only sees supplied source titles/snippets, never full
  page fetches; there is no autonomous crawler.
- Rate limiting is documented but not implemented.
- The SQLAlchemy session layer is synchronous (runs on worker threads) and has
  not been benchmarked under high concurrency.
- `InMemoryVectorStore` / `InMemoryGraphStore` / `InMemoryDocumentStore` are
  process-local, cleared on restart, and not shared across workers. SQL data
  survives when PostgreSQL is used; RAG and graph data do not yet.
- No Pinecone, Chroma, Qdrant, FAISS, Neo4j, or persistent GraphRAG integration.
- Category detection uses local pattern matching, not a trained model.
- Mock search uses deterministic records on reserved `*.example` domains and is
  never substituted after a real search failure.
- The browser UI is a local case workspace; its heavy document extraction and
  AI evidence classification run under `/api/v1`, and the UI "Run investigation"
  action uses the `SEARCH_PROVIDER` configured at startup.

---

## API examples

Curated curl examples for health, planning, agentic investigation, documents,
RAG search, and graph query are in [docs/api-examples.md](docs/api-examples.md).
Sample inputs live in [`examples/`](examples/):

- `examples/investigation-request.json` — a planning request
- `examples/sample-document.txt` — a small fictional TXT document
- `examples/api-request.json` — an agentic request
- `examples/demo.env` — the offline demo configuration

All sample data is fictional or public-domain style; nothing copyrighted or
confidential.

---

## License

**This repository currently has no explicit license.** Until a license is
chosen, the default copyright rules apply and the code cannot legally be treated
as open source for others to reuse. Pick a license (for example MIT or Apache-2.0)
and add a `LICENSE` file before publishing as open source.

## Versioning

The application version lives in `APP_VERSION` (default `0.6.0` in
`app/core/config.py` and `.env.example`). Note that a project-root `.env`
overrides the default at runtime: the committed files say `0.6.0`, while a local
`.env` pinned to `0.5.0` will win.

## Release checklist

See [docs/release-checklist.md](docs/release-checklist.md).
