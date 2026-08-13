# EvidenceAI - API examples

The examples below use placeholder data and are safe to run against the
offline demo configuration (see `examples/demo.env`). Endpoints marked
"requires Gemini" need `GEMINI_API_KEY` and may consume quota or incur charges.

Base URL: `http://127.0.0.1:8000`

## Health

```bash
curl http://127.0.0.1:8000/health
# {"status":"healthy","environment":"development"}

curl http://127.0.0.1:8000/health/live
# {"status":"alive"}

curl http://127.0.0.1:8000/health/ready
# {"status":"ready","persistence_provider":"in_memory","checks":[{"name":"persistence_provider","ok":true,"detail":"in_memory"}]}
```

## Investigation planning (deterministic, offline)

```bash
curl -X POST http://127.0.0.1:8000/api/v1/investigations/plan \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Research renewable energy storage",
    "depth": "standard"
  }'
```

The response is a typed plan: `status`, `category`, `research_angles`, and
prioritized `sub_questions`.

## AI-style planning (mock provider, offline)

```bash
curl -X POST http://127.0.0.1:8000/api/v1/investigations/ai-plan \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Compare solar power versus wind power",
    "depth": "quick"
  }'
```

With `LLM_PROVIDER=mock` this runs fully offline and reports
`"provider_used":"mock"`. With `LLM_PROVIDER=gemini` it calls the Gemini API.

## Mock research + evidence pipeline (offline)

```bash
curl -X POST http://127.0.0.1:8000/api/v1/research/mock \
  -H "Content-Type: application/json" \
  -d '{
    "investigation_query": "Research renewable energy storage",
    "sub_question": "Which primary sources describe long-duration storage?",
    "max_results": 3,
    "depth": "deep"
  }'
```

Returns normalized sources (on reserved `*.example` domains), evidence items
with full provenance, and stance counts. No network calls are made.

## Agentic investigation

The agentic, end-to-end research, and web-research endpoints select their
search provider through `SEARCH_PROVIDER`. With `SEARCH_PROVIDER=mock` (the
demo default) they run fully offline on reserved `*.example` domains; with
`SEARCH_PROVIDER=gemini_grounded` they use live grounded search and require
`GEMINI_API_KEY`:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/investigations/agentic \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Research long-duration energy storage performance",
    "depth": "quick",
    "max_sub_questions": 1,
    "max_sources_per_question": 2,
    "run_critic": true,
    "max_critic_rounds": 1,
    "use_rag": true,
    "use_graph_rag": true
  }'
```

The response contains the full typed state plus an ordered `audit_trail`.
Confidence describes the completeness of the evidence picture; no binary truth
verdict is returned.

## Evidence extraction (mock provider, offline)

```bash
curl -X POST http://127.0.0.1:8000/api/v1/evidence/extract \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Long-duration storage improved discharge duration",
    "sub_question": "Does the supplied source support the duration claim?",
    "sources": [
      {
        "source_id": "source-001",
        "title": "Official storage trial report",
        "url": "https://agency.example/storage/report",
        "domain": "agency.example",
        "retrieved_at": "2026-08-11T12:00:00Z",
        "source_type": "government",
        "snippet": "The trial reported a twelve-hour discharge duration.",
        "metadata": {}
      }
    ]
  }'
```

## Documents (upload, graph map, RAG index - all offline)

Upload a text file:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/upload \
  -F "files=@examples/sample-document.txt;type=text/plain" \
  -F "doc_type=other"
```

The response reports each document's `document_id`, page and character counts,
and a `duplicate` flag. Re-uploading identical bytes returns the existing
document with `"duplicate": true`.

Map the document into the knowledge graph:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/doc-<DOCUMENT_ID>/graph \
  -H "Content-Type: application/json" \
  -d '{"document_id": "doc-<DOCUMENT_ID>"}'
```

Index its pages into the vector store:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/documents/doc-<DOCUMENT_ID>/index \
  -H "Content-Type: application/json" \
  -d '{"embedding_provider": "mock"}'
```

## RAG search

Index normalized source content:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/rag/index \
  -H "Content-Type: application/json" \
  -d '{
    "sources": [
      {
        "source_id": "source-001",
        "source_url": "https://agency.example/storage/report",
        "title": "Official storage trial report",
        "content": "The trial reported a twelve-hour discharge duration using a grid-scale battery."
      }
    ]
  }'
```

Retrieve the most relevant chunks:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/rag/search \
  -H "Content-Type: application/json" \
  -d '{"query": "twelve-hour discharge duration", "top_k": 3}'
```

```bash
curl http://127.0.0.1:8000/api/v1/rag/stats
```

## Graph query

The browser UI exposes live graph data (nodes, edges, stats):

```bash
curl http://127.0.0.1:8000/api/graph
```

```bash
curl http://127.0.0.1:8000/api/v1/graph/stats   # note: see limitation below
```

Limitation: `app/api/v1/graph_routes.py` defines `/api/v1/graph/build`,
`/api/v1/graph/query`, `/api/v1/graph-rag/search`, and `/api/v1/graph/stats`,
but the module is not currently wired into the router. GraphRAG runs inside the
agentic workflow via `use_graph_rag`; the live graph data endpoint today is
`GET /api/graph`.

## Persistence (offline, in-memory provider)

```bash
curl -X POST http://127.0.0.1:8000/api/v1/users \
  -H "Content-Type: application/json" \
  -d '{"email": "demo@example.com", "display_name": "Demo User"}'

curl http://127.0.0.1:8000/api/v1/users/<USER_ID>

curl http://127.0.0.1:8000/api/v1/investigations
```

With `PERSISTENCE_PROVIDER=in_memory` (the demo default) this data lives in the
process and is cleared on restart. Set `PERSISTENCE_PROVIDER=sqlalchemy` with a
`DATABASE_URL` and run `alembic upgrade head` for durable storage.

## Validation error shape

Invalid input returns HTTP 422 with a consistent error body:

```json
{
  "code": "validation_error",
  "message": "Request validation failed",
  "details": [
    {
      "field": "query",
      "message": "String should have at least 5 characters",
      "type": "string_too_short"
    }
  ]
}
```
