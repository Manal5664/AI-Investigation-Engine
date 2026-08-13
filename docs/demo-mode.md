# EvidenceAI - offline demo mode

The demo mode runs the entire stack with deterministic mock providers. It
requires no Gemini API key, makes no external or billable calls, and clearly
labels every result as mock data (`provider_used` / `model_used` in responses).
Nothing presented in demo mode is a real web citation.

## Configuration

`examples/demo.env` pins every provider to the offline implementation:

| Variable | Value | Meaning |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | No production fast-fail checks |
| `LLM_PROVIDER` | `mock` | Deterministic planning/LLM output |
| `SEARCH_PROVIDER` | `mock` | Reserved `*.example` domains only |
| `EVIDENCE_PROVIDER` | `mock` | Deterministic evidence extraction |
| `EMBEDDING_PROVIDER` | `mock` | Deterministic local embeddings |
| `GRAPH_EXTRACTION_PROVIDER` | `mock` | Deterministic entity/relation extraction |
| `VISION_PROVIDER` | `mock` | Deterministic image descriptions |
| `VECTOR_STORE_PROVIDER` | `in_memory` | Process-local vector store |
| `GRAPH_STORE_PROVIDER` | `in_memory` | Process-local graph store |
| `DOCUMENT_STORE_PROVIDER` | `in_memory` | Process-local document store |
| `PERSISTENCE_PROVIDER` | `in_memory` | Process-local persistence |
| `GEMINI_API_KEY` | unset | No key, no calls |

The file sets `APP_ENV_FILE` handling in mind: load it explicitly so a
personal `.env` (which may contain a key) is never consulted.

## Commands

Local Python (PowerShell):

```powershell
$env:APP_ENV_FILE = "examples/demo.env"
python -m uvicorn app.main:app
```

Local Python (bash):

```bash
export APP_ENV_FILE=examples/demo.env
python -m uvicorn app.main:app
```

Open `http://127.0.0.1:8000/dashboard` (browser UI) or
`http://127.0.0.1:8000/docs` (OpenAPI).

## What the demo exercises

Verified offline smoke test (25/25 checks passed):

- `GET /health`, `/health/live`, `/health/ready`, `/`
- Browser pages: `/dashboard`, `/investigate`, `/documents`, `/history`,
  `/rag`, `/graph`
- `POST /api/v1/investigations/plan` - deterministic planning
- `POST /api/v1/investigations/ai-plan` - mock provider planning
- `POST /api/v1/research/mock` - offline research + evidence pipeline
- `POST /api/v1/evidence/extract` - mock evidence extraction
- `POST /api/v1/rag/index`, `/api/v1/rag/search`, `/api/v1/rag/stats` - mock
  embedding RAG end to end
- `POST /api/v1/documents/upload` (TXT), `/api/v1/documents/list`
- `POST /api/v1/documents/{id}/graph` - graph mapping
- `POST /api/v1/documents/{id}/index` - page-granular vector indexing
- `POST /api/v1/documents/investigations` - document-grounded investigation
- `GET /api/graph` - live graph data
- `POST /api/v1/users`, `GET /api/v1/investigations` - in-memory persistence

## What the demo covers end to end

The agentic, end-to-end research, and web-research endpoints are wired to the
`SEARCH_PROVIDER` setting rather than a hard-coded provider, so with
`SEARCH_PROVIDER=mock` the full pipeline is part of the offline demo:

- `POST /api/v1/investigations/agentic`
- `POST /api/v1/investigations/research`
- `POST /api/v1/research/web`
- Browser UI "Run investigation" (`POST /api/investigations/run`)

All of them return clearly labeled `*.example` sources with
`provider_used: "mock"` and never reach a search engine.

Switching to live grounded search is configuration-only: set
`SEARCH_PROVIDER=gemini_grounded` and a real `GEMINI_API_KEY`. Without a key,
the `gemini_grounded` provider fails fast with a configuration error instead of
silently falling back to `mock`.

`POST /api/v1/research/mock` remains available as the explicit offline-only
pipeline.

## Labeling

Every demo response identifies its source:

- `provider_used: "mock"` / `model_used` on AI planning, evidence, RAG, and
  document investigation responses.
- Mock research returns sources only on reserved `*.example` domains.
- `fallback_used` distinguishes deterministic output from a configured model.
