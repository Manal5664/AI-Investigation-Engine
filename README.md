# AI Investigation Engine

AI Investigation Engine is a FastAPI service that converts an investigation
query into a structured research plan. It supports both a deterministic planner
and a provider-independent AI planning flow. The offline `mock` provider remains
the default; an opt-in Google Gemini adapter can make real model calls when
explicitly configured with an API key and model name. A separate opt-in Gemini
Google Search grounding path returns normalized, citation-backed web sources.
An independently configured Gemini evidence adapter can classify only the
source material supplied to it and preserve validated provenance. Persisted
users, investigations, and documents can be stored in process memory by
default or in a SQLAlchemy-backed relational database, with an Alembic
migration set for the relational schema.

## Current features

- Strict Pydantic request and response schemas.
- Investigation depths: `quick`, `standard`, and `deep`.
- Deterministic classification into six investigation categories.
- Category-aware research angles.
- Structured, prioritized sub-questions.
- Versioned planning API under `/api/v1`.
- Consistent validation and application error responses.
- Environment-backed application settings without `pydantic-settings`.
- Vendor-neutral asynchronous `LLMProvider` abstraction.
- Local `MockLLMProvider` with schema-validated output.
- Official `google-genai` adapter with async structured JSON generation.
- Reusable prompt builders shared by mock and Gemini providers.
- Explicit provider/model/fallback metadata on AI planning responses.
- Labeled deterministic fallback for provider failures or invalid model output.
- Provider-independent asynchronous search abstraction.
- Deterministic mock search data on reserved example domains.
- Gemini Google Search grounding through the official `google-genai` SDK.
- Citation-annotation-only URL extraction, normalization, and deduplication.
- Grounded source provenance and source-quality heuristic assessment.
- Explainable source-quality scoring with explicit caveats.
- Provenance-preserving evidence extraction and stance classification.
- Strict Gemini evidence extraction with structured JSON and source allowlists.
- Conflict detection for opposing source claims without a truth verdict.
- Bounded end-to-end investigation research with explicit partial failures.
- Bounded agentic orchestration with research, evidence, critic, conflict, and
  synthesis agents plus a public replay log.
- Provider-neutral asynchronous embeddings, deterministic chunking, semantic
  retrieval, and duplicate-safe in-memory vector indexing.
- Optional RAG grounding in the agentic workflow through `use_rag`.
- Structured evidence summaries without final truth verdicts.
- Multipart document upload (PDF, DOCX, text/markdown, images) with type,
  size, and hash validation plus duplicate detection.
- Page-preserving extraction with a pluggable vision provider for image
  documents and scanned pages.
- Document content mapped into the shared knowledge graph as evidence and
  topic nodes with page/section provenance.
- Page-granular semantic indexing and retrieval of documents through the
  existing vector store.
- Document-grounded investigations that plan, gather excerpts, and synthesize
  a cited report strictly from stored documents.
- Pytest and HTTP-level ASGI endpoint tests.
- Persistence layer for users, investigations, and documents behind a
  provider-neutral repository interface.
- In-memory persistence by default for tests and development, plus an opt-in
  SQLAlchemy provider for PostgreSQL or SQLite.
- Alembic migrations for the relational schema, run against `DATABASE_URL`.
- HTTP endpoints for creating users, listing/detailing/deleting persisted
  investigations, and listing/deleting persisted documents.
- Agentic runs persist their full audit trail, sources, evidence items,
  conflicts, and synthesis report; uploaded documents persist to the same
  repository, which doubles as a fallback read source after store resets.

Gemini planning, Gemini Google Search grounding, Gemini evidence extraction,
and Gemini embeddings are the optional external integrations. No third-party
search SDK, autonomous crawler, external vector database, authentication layer,
or message bus is connected. Persistence itself is local (in memory or a
database the operator provisions); the service does not ship an authentication
layer.

## Architecture

```mermaid
flowchart LR
    Client[API client] --> Routes[FastAPI v1 routes]

    Routes -->|/plan| Deterministic[InvestigationPlanner]
    Routes -->|/ai-plan| AIService[AIInvestigationService]
    Routes -->|/research/web| WebService[WebResearchService]
    Routes -->|/evidence/extract| EvidenceService[EvidenceExtractionService]
    Routes -->|/investigations/research| Pipeline[Bounded Research Pipeline]

    AIService --> Factory[LLM provider factory]
    Factory --> Mock[MockLLMProvider]
    Factory --> Gemini[GeminiLLMProvider]
    Mock --> Prompts[Reusable prompt builders]
    Gemini --> Prompts
    Mock --> Deterministic

    Mock --> Raw[JSON-compatible provider output]
    Gemini --> Raw
    Raw --> Validation[Pydantic AIInvestigationPlan validation]
    Validation --> Response[Typed AIInvestigationResponse]

    AIService -. provider failure, timeout, or invalid schema .-> Deterministic

    WebService --> SearchFactory[Search provider factory]
    SearchFactory --> Grounded[GeminiGroundedSearchProvider]
    Grounded --> GoogleSearch[Gemini Google Search tool]
    GoogleSearch --> Citations[URL citation annotations]
    Citations --> Sources[Normalized, credibility-scored Sources]
    Sources --> EvidenceService
    EvidenceService --> EvidenceFactory[Evidence provider factory]
    EvidenceFactory --> GeminiEvidence[GeminiEvidenceExtractor]
    EvidenceFactory --> MockEvidence[MockEvidenceExtractor]
    Pipeline --> WebService
    Pipeline --> EvidenceService
    Pipeline --> Conflicts[EvidenceConflictService]
```

### RAG and semantic retrieval

```text
Sources
  ↓
Chunker
  ↓
Embedding Provider
  ↓
Vector Store
  ↓
Semantic Retriever
  ↓
Evidence / Agentic Investigation
```

An embedding is a numeric representation of text. Similar meanings tend to
produce vectors with higher cosine similarity, allowing a query to retrieve
relevant passages even when it does not repeat the source's exact wording.
Chunking keeps the retrieved context bounded, and RAG passes only the highest
ranking validated passages forward instead of every collected source passage.
This reduces irrelevant context; it does not prove that a retrieved passage is
correct.

`EmbeddingProvider` isolates model-specific embedding calls. The deterministic
`MockEmbeddingProvider` is the offline default, while
`GeminiEmbeddingProvider` uses the existing `google-genai` SDK,
`GEMINI_API_KEY`, and the configured `EMBEDDING_MODEL`. Model names are never
selected inside the Gemini adapter. `VectorStore` similarly isolates storage;
Phase 7 intentionally implements only `InMemoryVectorStore`.

Every chunk carries its original source ID and URL, title, optional
section/location, character offsets, deterministic chunk ID, and SHA-256
content hash. Retrieval returns those same values. Before retrieved text reaches
the existing evidence agent, the orchestrator verifies the source ID/URL pair,
title, content hash, and verbatim membership in the normalized source content.
It never invents or repairs source provenance.

### Document management subsystem

```text
Upload (multipart)
  ↓
Validator (type, size, hash, duplicates)
  ↓
Extractor (text / pdf / docx / image + vision)
  ↓
In-Memory Document Store
  ├── Page-granular RAG indexing → Vector Store
  └── Graph mapping (evidence + topic nodes) → Graph Store
        ↓
Document-grounded investigation report
```

Uploads are validated by extension and detected MIME type, bounded by
`DOCUMENT_MAX_UPLOAD_BYTES`, `DOCUMENT_MAX_PAGES`, and
`DOCUMENT_MAX_PER_REQUEST`, and deduplicated by SHA-256 content hash. PDF and
DOCX extraction reads only the package's own text/content streams; no embedded
scripts, macros, or network resources are executed. Image documents are passed
to a `VisionProvider` (`VISION_PROVIDER=mock` for deterministic offline output,
`gemini` for a real multimodal model) that returns a description, visible text,
and recognized objects.

Every extracted page becomes an `evidence` node in the shared graph, chained to
consecutive pages, with optional `topic` section nodes linked to their page.
Documents can also be indexed page-by-page into the existing vector store, so
`DocumentRAGService` recalls `(document_id, page_number)` pairs for a query. A
document-grounded investigation reuses the deterministic planner, gathers the
most relevant excerpts plus graph-derived notes, and asks a configured report
generator to synthesize findings that quote those excerpts. The report always
reports `provider_used`, `model_used`, and `fallback_used`.

When `EVIDENCE_INCLUDE_DOCUMENTS=true`, the evidence pipeline is wrapped with
`PageAwareEvidenceExtractor`: page excerpts from stored documents (RAG-ranked
when embeddings are configured) are converted to page-granular `Source`
records and passed to the configured evidence extractor alongside web sources.

### Persistence subsystem

```text
Routes / services
      ↓  (async)
DocumentPersistenceGateway ── InvestigationPersistenceService
      ↓                                 ↓
Unit of Work (transaction boundary)
      ↓
Repositories (users, investigations, documents, sources, evidence)
      ↓
In-Memory Repositories (default)   |   SQLAlchemy Repositories (opt-in)
                                    ↓
                           users, investigations, investigation_steps,
                           sources, evidence_items, conflicts,
                           investigation_reports, documents, document_pages
```

`PERSISTENCE_PROVIDER` selects the backing store:

- `in_memory` (default) keeps every entity in process memory. This is the
  offline development and test fallback and requires no database.
- `sqlalchemy` persists to the relational database named by `DATABASE_URL`.
  PostgreSQL is intended for real use; SQLite works for local development.

Repository implementations return and accept typed records from
`app/schemas/persistence.py`; the SQLAlchemy implementations map those records
to/from ORM models (`app/database/models`) and never leak sessions or ORM
objects into routes. Every write goes through a unit of work that commits on
success and rolls back on failure. Async callers use
`DocumentPersistenceGateway` and the persistence routes, which marshal
synchronous SQLAlchemy work onto a worker thread via `asyncio.to_thread`.

The relational schema is owned by Alembic. Generate or refresh migrations with:

```powershell
$env:DATABASE_URL="sqlite:///./ai_investigation.db"
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

`alembic check` verifies that the schema and the models are in sync.
`reset_persistence()` clears the in-memory provider between automated tests.

### Browser UI workspace

The same FastAPI process serves a browser UI for case management. The UI is a
thin layer over the real engine — every page and JSON endpoint reads live data
from the pluggable `PERSISTENCE_PROVIDER` and the document/vector/graph stores
that back `/api/v1`. There is no separate UI database or background worker.

```text
Browser (Jinja2 templates + vanilla JS)
      ↓
UI routes (app/api/ui_routes.py)
      ├── Pages      /dashboard, /investigate, /documents, /history,
      │              /rag, /graph, /investigation/{id}, export
      ├── JSON API   /api/dashboard (aggregate), /api/graph,
      │              /api/investigations/run
      └── Live reads real engine stores (repositories, document/vector/graph
          stores) and reuses the /api/v1 endpoints for list/detail/delete,
          document upload, and RAG search
```

The `/api/dashboard` endpoint aggregates counts, a 14-day trend, and recent
investigations straight from the persistence repository. Submitting the
"Run investigation" form calls `/api/investigations/run`, which mirrors the
`/api/v1/investigations/agentic` agentic flow and then persists the result, so
the browser can navigate straight to the new `/investigation/{id}` page.
Results can be exported per investigation as CSV or JSON.

### Deterministic and AI-provider flows

| Flow | Endpoint | Implementation | Intended use |
| --- | --- | --- | --- |
| Deterministic | `POST /api/v1/investigations/plan` | Local `InvestigationPlanner` | Stable baseline and fallback |
| AI-style | `POST /api/v1/investigations/ai-plan` | Configured `LLMProvider` through `AIInvestigationService` | Provider-independent integration boundary |

Both flows preserve the `status` and `plan` envelope. The AI-style response also
identifies `provider_used`, `model_used`, and `fallback_used`. Its plan adds a
research objective, explicit assumptions, expected evidence types, and
potential biases. All provider output is validated before it reaches the API
response.

### Current mock provider

`MockLLMProvider` implements the same asynchronous contract intended for future
real providers. It builds the future planning prompt, generates realistic
structured data locally, and returns JSON-compatible output. Its behavior is
deterministic and uses no network calls, API keys, model SDKs, or usage charges.

### Optional Gemini provider

`GeminiLLMProvider` uses the official `google-genai` SDK and the same
vendor-neutral `LLMProvider` contract. It sends the existing planning prompt
through the SDK's asynchronous API, requests `application/json` with the
`AIInvestigationPlan` JSON schema, and validates the returned JSON with
Pydantic. Empty, malformed, schema-invalid, timed-out, and provider-error
responses are never treated as successful AI output.

When fallback is needed, the API reports `provider_used: "deterministic"` and
`fallback_used: true`, along with a sanitized `provider_error`. It does not label
the locally generated plan as Gemini output.

### Future provider adapters

Future OpenAI or Anthropic adapters should implement only `LLMProvider` and
translate provider-specific responses into the neutral structured output
contract. Vendor SDK objects, authentication, and error types remain inside
their adapter modules.

## Research and evidence pipeline

```mermaid
flowchart TD
    Query[Investigation query]
    Planner[Investigation Planner]
    Search[Search Provider]
    Results[Typed Search Results]
    Sources[Normalized Sources]
    Credibility[Credibility Assessment]
    Extraction[Evidence Extraction]
    Classification[Evidence Classification]
    ResearchResult[Research Result]
    Summary[Evidence Summary]

    Query --> Planner
    Planner --> Search
    Search --> Results
    Results --> Sources
    Sources --> Credibility
    Credibility --> Extraction
    Extraction --> Classification
    Classification --> ResearchResult
    ResearchResult --> Summary
```

### Bounded agentic workflow

```mermaid
flowchart TD
    User[User Query] --> Orchestrator[Investigation Orchestrator]
    Orchestrator --> Planner[Planner]
    Orchestrator --> ResearchAgent[Research Agent]
    Orchestrator --> EvidenceAgent[Evidence Agent]
    Orchestrator --> ConflictDetector[Conflict Detector]
    Orchestrator --> Critic[Devil's Advocate Agent]
    Orchestrator --> Synthesis[Synthesis Agent]
    Synthesis --> Result[Evidence-grounded result + replay log]
```

The agents are application-level services, not autonomous processes. A request
can execute at most two primary sub-questions, three sources per question, two
critic rounds, and three sources per critic query. There is no recursion,
self-scheduling, or open-ended tool loop.

The critic deliberately looks for strong evidence against the current leading
interpretation. It records assumptions that may be wrong, deduplicates known
source URLs, and treats a search that finds no opposing evidence as a gap rather
than confirmation or contradiction. The synthesis reports confidence in the
completeness and consistency of the evidence picture, never the probability
that a claim is true.

Every orchestrator action appends a typed replay step with timestamps,
provider/model metadata, concise action summaries, counts, warnings/errors, and
source/evidence references. The replay log contains no hidden chain-of-thought
or private model reasoning. Provider failures produce partial output whenever
validated sources or evidence remain, and mock sources are never substituted
after a real research failure.

### Provenance

Every evidence item retains the supplied source ID and URL, the exact relevant
passage, retrieval timestamp, extraction method, model identifier, rationale,
optional location, and a SHA-256 content hash. The Gemini extractor validates
every evidence source ID/URL pair and requires the passage to be a verbatim
substring of supplied source material. Unknown, changed, duplicated, or omitted
sources fail the extraction; they are never silently dropped or fabricated.

### Source-quality scoring is not truth

The current credibility service uses explainable metadata heuristics: source
type, author availability, publication date, HTTPS, publisher/domain
information, and reference or citation metadata. Its `high`, `moderate`, `low`,
and `unknown` levels estimate source quality only. They do not prove that a
statement is accurate, complete, unbiased, or true.

### Grounded web research

`GeminiGroundedSearchProvider` implements the vendor-neutral `SearchProvider`
contract with Gemini's built-in Google Search tool. The adapter accepts URLs
only from `url_citation` annotations returned by grounding metadata. URLs in
model prose are ignored. Valid URLs are normalized, stripped of common tracking
parameters and fragments, deduplicated, capped by `max_results`, and converted
to typed `Source` records.

The standalone web path stops after source normalization and credibility
assessment. It does not run an evidence extractor or make a truth determination.
The end-to-end investigation path passes those normalized sources to the
configured evidence extractor and never substitutes mock search sources after a
real search failure.

## Project structure

```text
AI-Investigation-Engine/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── ai/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── factory.py
│   │   ├── mock_provider.py
│   │   └── prompts.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       ├── documents_routes.py
│   │       ├── persistence_routes.py
│   │       ├── research_routes.py
│   │       └── routes.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   ├── exceptions.py
│   │   ├── logging.py
│   │   └── middleware.py
│   ├── database/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── mapping.py
│   │   ├── persistence_gateway.py
│   │   ├── provider.py
│   │   ├── session.py
│   │   ├── uow.py
│   │   ├── models/
│   │   │   ├── conflict.py
│   │   │   ├── document.py
│   │   │   ├── document_page.py
│   │   │   ├── evidence_item.py
│   │   │   ├── investigation.py
│   │   │   ├── investigation_report.py
│   │   │   ├── investigation_step.py
│   │   │   ├── source.py
│   │   │   └── user.py
│   │   └── repositories/
│   │       ├── base.py
│   │       ├── inmemory.py
│   │       └── sqlalchemy.py
│   ├── documents/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── factory.py
│   │   ├── mappers.py
│   │   ├── models.py
│   │   ├── reporting.py
│   │   ├── reporting_factory.py
│   │   ├── store.py
│   │   ├── validators.py
│   │   ├── extractors/
│   │   └── vision/
│   ├── evidence/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   └── mock_extractor.py
│   ├── research/
│   │   ├── __init__.py
│   │   └── search/
│   │       ├── __init__.py
│   │       ├── base.py
│   │       ├── factory.py
│   │       └── mock_provider.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── common.py
│   │   ├── documents.py
│   │   ├── evidence.py
│   │   ├── investigation.py
│   │   ├── research.py
│   │   └── source.py
│   └── services/
│       ├── __init__.py
│       ├── ai_investigation_service.py
│       ├── document_graph_service.py
│       ├── document_ingestion_service.py
│       ├── document_investigation_service.py
│       ├── document_rag_service.py
│       ├── evidence_summary_service.py
│       ├── investigation_persistence_service.py
│       ├── investigation_service.py
│       ├── research_service.py
│       └── source_credibility_service.py
├── ui/
│   ├── __init__.py
│   ├── database.py
│   └── worker.py
├── static/
│   ├── css/app.css
│   └── js/{app,api,dashboard,investigate,investigation,documents,history,rag,graph}.js
├── templates/
│   ├── base.html
│   └── {dashboard,investigate,documents,history,rag,graph,investigation,error}.html
├── tests/
│   └── test_api.py
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       └── <initial persistence schema>
├── alembic.ini
├── tests/
│   ├── __init__.py
│   ├── test_ai_provider.py
│   ├── test_ai_service.py
│   ├── test_api.py
│   ├── test_agentic_workflow.py
│   ├── test_database_persistence.py
│   ├── test_documents.py
│   ├── test_evidence_pipeline.py
│   ├── test_investigation_planner.py
│   ├── test_research_api.py
│   ├── test_search_provider.py
│   └── test_source_credibility.py
├── .env.example
├── .gitignore
├── Dockerfile
├── compose.yaml
├── .github/
│   └── workflows/
│       └── test.yml
├── README.md
├── requirements-dev.txt
└── requirements.txt
```

Gemini-specific additions include `app/ai/gemini_provider.py`,
`app/research/search/gemini_grounded_provider.py`,
`app/evidence/gemini_extractor.py`, `app/evidence/factory.py`,
`app/services/evidence_conflict_service.py`,
`app/services/investigation_research_service.py`, and the guarded scripts under
`scripts/`. The bounded Phase 6 workflow lives in `app/agents/`, with its public
state and replay schemas in `app/schemas/agentic.py`.
Phase 7 retrieval code lives in `app/rag/`, with typed public schemas in
`app/schemas/rag.py`, HTTP routes in `app/api/v1/rag_routes.py`, and indexing
and retrieval application services under `app/services/`.
The document management subsystem lives in `app/documents/` with page-aware
graph mapping, page-granular RAG indexing, vision-backed image extraction, and
document-grounded investigation services wired through
`app/api/v1/documents_routes.py`.

## Run locally

Activate the existing virtual environment, then start the API from the project
root:

```powershell
python -m uvicorn app.main:app --reload
```

The same process serves the browser UI. Open `http://127.0.0.1:8000/dashboard`
to land on the case-management dashboard, or start from
`http://127.0.0.1:8000/`.

Interactive OpenAPI documentation is available at:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/redoc`

The application reads these optional environment variables:

| Variable | Default |
| --- | --- |
| `APP_NAME` | `AI Investigation Engine` |
| `APP_VERSION` | `0.6.0` |
| `ENVIRONMENT` | `development` |
| `DEBUG` | `false` |
| `LLM_PROVIDER` | `mock` |
| `LLM_MODEL` | `mock-investigator` |
| `LLM_TIMEOUT_SECONDS` | `60` |
| `GEMINI_API_KEY` | unset |
| `EVIDENCE_PROVIDER` | `mock` |
| `EVIDENCE_MODEL` | `gemini-3.6-flash` |
| `SEARCH_PROVIDER` | `mock` |
| `SEARCH_MODEL` | `gemini-3.6-flash` |
| `SEARCH_MAX_RESULTS` | `5` |
| `EMBEDDING_PROVIDER` | `mock` |
| `EMBEDDING_MODEL` | `mock-embedding-v1` |
| `VECTOR_STORE_PROVIDER` | `in_memory` |
| `RAG_CHUNK_SIZE` | `1000` |
| `RAG_CHUNK_OVERLAP` | `200` |
| `DOCUMENT_STORE_PROVIDER` | `in_memory` |
| `DOCUMENT_MAX_UPLOAD_BYTES` | `10485760` |
| `DOCUMENT_MAX_PAGES` | `50` |
| `DOCUMENT_MAX_PER_REQUEST` | `10` |
| `VISION_PROVIDER` | `mock` |
| `VISION_MODEL` | `gemini-3.6-flash` |
| `EVIDENCE_INCLUDE_DOCUMENTS` | `false` |
| `PERSISTENCE_PROVIDER` | `in_memory` |
| `DATABASE_URL` | unset |
| `DATABASE_ECHO` | `false` |
| `HOST` | `127.0.0.1` |
| `PORT` | `8000` |
| `LOG_LEVEL` | `INFO` |
| `LOG_JSON` | `false` |
| `CORS_ALLOWED_ORIGINS` | empty |

The application loads a project-root `.env` file when present. Explicit process
environment variables take precedence. Set `APP_ENV_FILE` to another path to
load a different file, or to an empty value to disable file loading. Keep the
offline defaults for normal development. To enable Gemini in the current
PowerShell process:

```powershell
$env:LLM_PROVIDER="gemini"
$env:LLM_MODEL="gemini-3.6-flash"
$env:GEMINI_API_KEY="<your-api-key>"
python -m uvicorn app.main:app --reload
```

The model identifier is configuration, not provider code. Re-check Google's
model lifecycle documentation before production deployment.

Run the optional one-request integration check only when the key is present:

```powershell
$env:GEMINI_API_KEY="<your-api-key>"
$env:LLM_MODEL="gemini-3.6-flash"
python -m scripts.test_gemini
```

Run one real grounded web-research request:

```powershell
python -m scripts.test_web_research
```

Run one deliberately small real end-to-end investigation (one quick
sub-question and at most two sources):

```powershell
$env:EVIDENCE_PROVIDER="gemini"
$env:EVIDENCE_MODEL="gemini-3.6-flash"
python -m scripts.test_real_investigation
```

Run one small real agentic investigation with one primary question, two sources,
and one critic round:

```powershell
python -m scripts.test_agentic_investigation
```

Run one real document management experiment (upload a generated DOCX, map it
into the graph, index it into the vector store, and run a document-grounded
investigation):

```powershell
python -m scripts.test_document_experiment
```

Run the optional real Gemini embedding smoke test with one configured model and
two tiny strings:

```powershell
$env:EMBEDDING_PROVIDER="gemini"
$env:EMBEDDING_MODEL="<supported-embedding-model>"
python -m scripts.test_gemini_embeddings
```

All real scripts require `GEMINI_API_KEY`. They never print the key. Model and
grounded-search usage may consume quota or incur charges, so these scripts are
opt-in and are never run by the automated test suite.

## Production and deployment

### Environment separation

Set `ENVIRONMENT` to `development`, `testing`, or `production`. Production
enforces safe configuration at startup and fails fast (the process exits)
when any of the following is wrong:

- `PERSISTENCE_PROVIDER` is not `sqlalchemy` (in-memory persistence is
  process-local and cleared on restart, so it is rejected in production).
- `DATABASE_URL` is missing or points at SQLite (PostgreSQL is required).
- `DEBUG=true`.
- A Gemini-backed provider is selected (`LLM_PROVIDER`, `EVIDENCE_PROVIDER`,
  `SEARCH_PROVIDER`, `EMBEDDING_PROVIDER`, `VISION_PROVIDER`, or
  `GRAPH_EXTRACTION_PROVIDER` is `gemini`/`gemini_grounded`) without
  `GEMINI_API_KEY`.

Development and testing stay unconstrained: the in-memory persistence and mock
AI providers remain available so local work and the offline test suite need no
database or API key. `GEMINI_API_KEY` is required only when a Gemini provider is
actually selected.

### Local development (unchanged)

```powershell
python -m uvicorn app.main:app --reload
```

### Production server

A thin launcher reads `HOST` and `PORT` from the environment
(platforms commonly inject `PORT`):

```powershell
python -m scripts.run
```

Equivalent direct command:

```powershell
python -m uvicorn app.main:app --host 0.0.0.0 --port "${env:PORT}"
```

Run a single worker: the vector and graph stores are process-local (see
Limitations), so multiple uvicorn workers would not share them. Scale out
behind a load balancer only when persistent vector/graph stores exist.

### Docker image

```powershell
docker build -t evidenceai .
```

Run it (PostgreSQL must already be reachable and migrated):

```powershell
docker run -d -p 8000:8000 `
  -e ENVIRONMENT=production `
  -e PERSISTENCE_PROVIDER=sqlalchemy `
  -e DATABASE_URL="postgresql+psycopg://investigator:PASSWORD@dbhost:5432/ai_investigation" `
  -e GEMINI_API_KEY="<your-key>" `
  evidenceai
```

The image is `python:3.12-slim`, installs runtime dependencies only, runs as a
non-root `appuser`, exposes port `8000`, and includes a liveness healthcheck.
No API keys are baked into the image; supply them through the environment or a
secret manager.

### Docker Compose (local production-like stack)

```powershell
docker compose up --build
```

`compose.yaml` starts PostgreSQL plus the app and a one-shot `migrate` service
that runs `alembic upgrade head` before the app starts. A named volume
(`postgres_data`) keeps the database across restarts. Default credentials in
the compose file are development-only placeholders; supply real secrets through
the environment, for example:

```powershell
$env:POSTGRES_PASSWORD="<real-password>"
$env:GEMINI_API_KEY="<real-key>"
docker compose up --build
```

Production secrets must always be supplied externally — never commit them.

### Database migrations

Run migrations before starting the application:

```powershell
$env:DATABASE_URL="postgresql+psycopg://investigator:PASSWORD@dbhost:5432/ai_investigation"
alembic upgrade head
```

Migration workflow:

```powershell
alembic revision --autogenerate -m "description"
alembic upgrade head
```

`alembic check` verifies the schema and models are in sync. In Docker Compose
the `migrate` service executes `alembic upgrade head` as a controlled step
before any web worker starts, so workers never race one another applying
migrations. `postgres://` and `postgresql://` URLs are automatically normalized
to the bundled `psycopg` driver.

### Health endpoints

| Method | Path | Semantics |
| --- | --- | --- |
| `GET` | `/health` | Backward-compatible service health and environment |
| `GET` | `/health/live` | Process/application is alive; no external dependencies |
| `GET` | `/health/ready` | Ready to serve; checks the configured persistence (a cheap `SELECT 1` for SQLAlchemy), returns `503` when not ready |

Health responses never expose secrets, API keys, or the full `DATABASE_URL`.

### Logging and request IDs

The `app` logger namespace is configured once at startup. Set `LOG_LEVEL`
(`DEBUG`/`INFO`/`WARNING`/`ERROR`) and `LOG_JSON=true` for single-line JSON
records suitable for log aggregators. Every HTTP request is logged with
method, path, status, duration (ms), and a request ID.

`X-Request-ID` is accepted when it is a safe value (letters, digits, `.`, `_`,
`:`, `-`, up to 128 characters); anything unsafe or oversized is replaced with
a generated ID. The ID is returned on every response and stored on
`request.state.request_id`. Logs never include query strings, bodies, API keys,
authorization values, database credentials, or full investigation contents.

### Security

- CORS is disabled by default (the browser UI is served same-origin by this
  FastAPI application). If CORS is needed, set `CORS_ALLOWED_ORIGINS` to an
  explicit comma-separated origin list; production never defaults to `*`.
- Every response carries `X-Content-Type-Options: nosniff`,
  `Referrer-Policy: same-origin`, `X-Frame-Options: DENY`, and a
  `Content-Security-Policy` tuned for the CDN-based frontend (jsDelivr
  scripts, Google Fonts, Bootstrap Icons, inline styles/scripts).
  `script-src` and `style-src` include `'unsafe-inline'` because the existing
  templates use inline scripts and styles; removing that directive requires
  frontend changes (nonces/hashes) and is out of scope for this phase.
- Uploads are validated server-side: per-request count, per-file byte cap
  enforced before the whole body is read, allowed MIME types/extensions,
  filename sanitization (directory components and control characters are
  stripped), and SHA-256 duplicate detection. Browser-side validation is never
  trusted.
- Production error responses are generic and never expose Python tracebacks,
  internal file paths, or configuration values. When `DEBUG=true` (development
  only) the exception type and message are included for convenience.

### Rate limiting

No in-process or external rate limiter is implemented yet. For a
production-facing deployment, add rate limiting in front of the expensive
endpoints:

- `POST /api/v1/investigations/agentic` and `/api/v1/investigations/research`
  (bounded but multi-call agentic workflows).
- `POST /api/v1/research/web` (Gemini Google Search grounding is billed per
  query executed).
- `POST /api/v1/evidence/extract` (Gemini evidence calls).
- `POST /api/v1/rag/index`, `/api/v1/documents/*/index`, and document uploads
  (memory and compute).
- `/api/v1/investigations/ai-plan` (Gemini LLM calls).

Prefer a gateway/proxy limiter (or a shared store such as Redis) so limits hold
across multiple workers; a process-local limiter would be incorrect when the
app is scaled horizontally. Existing provider quota/retry behavior is preserved.

### Deployment target guidance

The Docker image is portable. A simple target for this FastAPI + PostgreSQL
application is **Railway** or **Render** (managed PostgreSQL, environment
variables, and Docker deploys with zero extra code), or **Fly.io** /
**Google Cloud Run** if a managed container platform is preferred. On any
platform: provision PostgreSQL, set `DATABASE_URL`, run `alembic upgrade head`
as a release step, set `ENVIRONMENT=production` and
`PERSISTENCE_PROVIDER=sqlalchemy`, and inject `GEMINI_API_KEY` from a secret
manager. This repository ships no vendor-specific deployment code so the same
image can move between targets. No cloud deployment is currently provisioned by
this project.

## API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Basic service information |
| `GET` | `/health` | Health and environment status |
| `GET` | `/health/live` | Liveness probe (no external dependencies) |
| `GET` | `/health/ready` | Readiness probe (checks persistence; `503` when not ready) |
| `POST` | `/api/v1/investigations/plan` | Generate a deterministic investigation plan |
| `POST` | `/api/v1/investigations/ai-plan` | Generate a provider-backed AI-style plan |
| `POST` | `/api/v1/investigations/research` | Run bounded grounded research, evidence extraction, conflict detection, and summary |
| `POST` | `/api/v1/investigations/agentic` | Run the bounded research/evidence/critic/synthesis workflow with replay metadata |
| `POST` | `/api/v1/research/mock` | Run the offline mock research/evidence pipeline |
| `POST` | `/api/v1/research/web` | Run real Gemini Google Search grounding and normalize cited sources |
| `POST` | `/api/v1/evidence/extract` | Extract strictly source-grounded evidence with the configured evidence provider |
| `POST` | `/api/v1/evidence/summary` | Summarize evidence counts and unresolved conflicts |
| `POST` | `/api/v1/rag/index` | Chunk, embed, and index normalized source content |
| `POST` | `/api/v1/rag/search` | Retrieve the highest-cosine matching source chunks |
| `GET` | `/api/v1/rag/stats` | Inspect non-secret in-memory vector-store statistics |
| `POST` | `/api/v1/documents/upload` | Upload one or more documents (multipart `files`) |
| `GET` | `/api/v1/documents/store` | Inspect document-store statistics |
| `GET` | `/api/v1/documents/list` | List stored documents (optional `kind`, `limit`, `offset`) |
| `GET` | `/api/v1/documents/{document_id}` | Fetch one document's extracted content |
| `POST` | `/api/v1/documents/delete` | Delete stored documents by ID |
| `POST` | `/api/v1/documents/{document_id}/graph` | Map a document's pages/sections into the graph store |
| `POST` | `/api/v1/documents/{document_id}/index` | Index a document's pages into the vector store |
| `POST` | `/api/v1/documents/investigations` | Run a document-grounded investigation |
| `POST` | `/api/v1/users` | Create a user (409 on duplicate email) |
| `GET` | `/api/v1/users/{user_id}` | Fetch one persisted user |
| `GET` | `/api/v1/investigations` | List persisted investigations (optional `limit`, `offset`) |
| `GET` | `/api/v1/investigations/{investigation_id}` | Fetch a persisted investigation with steps, sources, evidence, conflicts, and report |
| `DELETE` | `/api/v1/investigations/{investigation_id}` | Delete a persisted investigation |
| `GET` | `/api/v1/documents` | List persisted documents (optional `kind`, `limit`, `offset`) |
| `DELETE` | `/api/v1/documents/{document_id}` | Delete a persisted document from the repository and the store |

### UI endpoints (browser case workspace)

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/dashboard` | Dashboard page (charts + recent cases) |
| `GET` | `/investigate` | New-case form page |
| `GET` | `/documents` | Document upload/search page |
| `GET` | `/history` | Case history page |
| `GET` | `/rag` | Evidence search page |
| `GET` | `/graph` | Case relationship-graph page |
| `GET` | `/investigation/{id}` | Case detail page (status, evidence, report, entities, log) |
| `GET` | `/investigation/{id}/export?format=csv\|json` | Export one case |
| `GET` | `/api/dashboard` | Dashboard statistics and chart data |
| `POST` | `/api/investigations` | Enqueue a new investigation (`title`, `description`, `notes`, `timeline_start`, `timeline_end`) |
| `GET` | `/api/investigations` | List investigations |
| `GET` | `/api/investigations/{id}` | Fetch one investigation |
| `DELETE` | `/api/investigations/{id}` | Delete one investigation |
| `GET` | `/api/investigations/{id}/status` | Status, progress, and current stage |
| `POST` | `/api/investigations/{id}/rerun` | Clear results and re-enqueue |
| `GET` | `/api/investigations/{id}/evidence` | Evidence items |
| `GET` | `/api/investigations/{id}/events` | Pipeline event log |
| `GET` | `/api/investigations/{id}/entities` | Extracted entities |
| `GET` | `/api/investigations/{id}/report` | Final report |
| `GET` | `/api/investigations/{id}/graph` | Graph nodes and edges |
| `GET` | `/api/documents?q=` | List/search documents |
| `POST` | `/api/documents/upload` | Upload documents (multipart `files`, `doc_type`, optional `titles`) |
| `DELETE` | `/api/documents/{id}` | Delete one document |
| `POST` | `/api/rag/search` | Retrieve relevant document chunks for a query |

These endpoints are excluded from the OpenAPI schema; the `/api/v1` surface
above remains the machine-facing API.

### Planning request

```json
{
  "query": "Research renewable energy storage",
  "depth": "standard"
}
```

`depth` is optional and defaults to `standard`.

### Planning response

```json
{
  "status": "investigation_planned",
  "plan": {
    "query": "Research renewable energy storage",
    "depth": "standard",
    "category": "research_topic",
    "research_angles": [
      {
        "angle": "definitions_and_scope",
        "description": "Clarify key terms, entities, timeframe, and investigation boundaries."
      },
      {
        "angle": "source_credibility",
        "description": "Assess source authority, independence, methodology, and potential bias."
      },
      {
        "angle": "historical_context",
        "description": "Establish the background and timeline needed to interpret the topic."
      },
      {
        "angle": "supporting_evidence",
        "description": "Identify reliable evidence that supports the central assertions."
      },
      {
        "angle": "contradicting_evidence",
        "description": "Actively look for evidence that challenges or weakens the assertions."
      }
    ],
    "sub_questions": [
      {
        "id": "sq-01",
        "question": "Which terms, entities, timeframe, and scope must be defined for \"Research renewable energy storage\"?",
        "purpose": "Clarify key terms, entities, timeframe, and investigation boundaries.",
        "priority": 1
      },
      {
        "id": "sq-02",
        "question": "Which primary or authoritative sources are best suited to investigate \"Research renewable energy storage\", and why?",
        "purpose": "Assess source authority, independence, methodology, and potential bias.",
        "priority": 2
      },
      {
        "id": "sq-03",
        "question": "What historical context and timeline are necessary to understand \"Research renewable energy storage\"?",
        "purpose": "Establish the background and timeline needed to interpret the topic.",
        "priority": 3
      },
      {
        "id": "sq-04",
        "question": "What reliable evidence supports the central assertions in \"Research renewable energy storage\"?",
        "purpose": "Identify reliable evidence that supports the central assertions.",
        "priority": 4
      },
      {
        "id": "sq-05",
        "question": "What credible evidence contradicts or weakens the assertions in \"Research renewable energy storage\"?",
        "purpose": "Actively look for evidence that challenges or weakens the assertions.",
        "priority": 5
      }
    ]
  }
}
```

### Validation errors

Invalid input returns HTTP `422` with a consistent error body:

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

The query is trimmed, must be a string, and must contain at least five
characters. Additional request fields are rejected. Depth must be `quick`,
`standard`, or `deep`.

### AI-style planning request

```json
{
  "query": "Compare solar power versus wind power",
  "depth": "quick"
}
```

Send this body to `POST /api/v1/investigations/ai-plan`. The response keeps the
`status` and `plan` envelope and includes:

- `research_objective` with explicit success criteria.
- `assumptions` that require validation.
- Structured `research_angles` and prioritized `sub_questions`.
- `expected_evidence_types`.
- `potential_biases` with mitigations.
- `provider_used`, `model_used`, and `fallback_used` metadata.
- An optional sanitized `provider_error` when fallback was required.

For the default `mock` provider, repeated requests with the same query and depth
produce the same response.

### Grounded web research request

```json
{
  "query": "What are the latest official developments in long-duration energy storage?",
  "max_results": 5
}
```

Send this body to `POST /api/v1/research/web`. The response contains the query,
`provider_used`, `model_used`, normalized and credibility-scored `sources`, a
`grounded_summary`, citation annotations and search-query metadata, and
warnings. A citation includes its normalized source URL, source title, optional
cited text and offsets, and the normalized source ID.

If Gemini returns no usable `url_citation` metadata, `sources` and citations are
empty and the response includes an explicit warning. The service never derives
a source URL from generated prose.

Gemini 3 Google Search grounding is billed per search query executed by the
model, and one API request can execute multiple billable queries. Review the
[official grounding pricing guidance](https://ai.google.dev/gemini-api/docs/google-search#pricing)
and project quota before enabling the web endpoint.

### Mock research request

```json
{
  "investigation_query": "Research renewable energy storage",
  "sub_question": "Which primary sources describe long-duration storage?",
  "max_results": 3,
  "depth": "deep"
}
```

Send this body to `POST /api/v1/research/mock`. `sub_question` is optional; when
it is omitted, the research service selects the highest-priority sub-question
from the generated investigation plan.

The response is a typed `ResearchResult` containing:

- The investigation query, depth, and selected sub-question.
- Normalized sources with metadata and credibility assessments.
- Evidence items with stance, strength, and complete provenance.
- Counts for `supports`, `contradicts`, `neutral`, and `insufficient`.
- Warnings about low-quality sources and heuristic limitations.

### Evidence extraction request

```json
{
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
      "metadata": {},
      "credibility": null,
      "author": null,
      "publisher": null,
      "published_at": null
    }
  ]
}
```

Send this body to `POST /api/v1/evidence/extract`. `EVIDENCE_PROVIDER=mock`
selects the labeled deterministic development extractor;
`EVIDENCE_PROVIDER=gemini` selects `GeminiEvidenceExtractor` and additionally
requires `EVIDENCE_MODEL` and `GEMINI_API_KEY`. Gemini receives only the supplied
title/snippet material. Its structured response must preserve every source ID
and URL and copy each passage verbatim. Any unknown source or fabricated passage
causes a typed provider error instead of a partial evidence list.

The response contains `provider_used`, `model_used`, typed `evidence_items`,
`stance_counts`, and warnings. Stances are `supports`, `contradicts`, `neutral`,
or `insufficient`; strengths are `strong`, `moderate`, `weak`, or `unknown`.
Missing evidence is classified as `insufficient`, never as contradiction.

### End-to-end investigation research request

```json
{
  "query": "Research long-duration energy storage performance",
  "depth": "quick",
  "max_sub_questions": 1,
  "max_sources_per_question": 2
}
```

Send this body to `POST /api/v1/investigations/research`. The service creates a
deterministic plan, selects the highest-priority questions, performs real Gemini
grounded search, normalizes and scores returned sources, invokes the configured
evidence extractor, detects opposing source claims, and produces an evidence
summary without a truth verdict.

Cost controls are enforced by request validation: `max_sub_questions` defaults
to 2 and cannot exceed 2; `max_sources_per_question` defaults to 3 and cannot
exceed 3. Grounded-search retry behavior is separately bounded to three attempts.
If web research is rate-limited, the response status is `partial` when earlier
questions completed or `failed` when none completed, with typed retry metadata.
No mock sources are substituted.

### Agentic investigation request

```json
{
  "query": "Research long-duration energy storage performance",
  "depth": "quick",
  "max_sub_questions": 1,
  "max_sources_per_question": 2,
  "run_critic": true,
  "max_critic_rounds": 1,
  "use_rag": false
}
```

Send this body to `POST /api/v1/investigations/agentic`. The orchestrator runs a
finite planner -> research -> evidence -> conflict -> critic -> synthesis
sequence. Primary research is limited to 2 sub-questions and 3 sources per
question. The critic defaults to one research round, has a hard maximum of 2,
and can request at most 3 sources per round. It challenges the current leading
interpretation; a failed search or lack of opposing evidence is recorded as an
evidence gap rather than a contradiction.

`use_rag` defaults to `false`, preserving the Phase 6 execution path. When it
is `true`, each primary question's usable normalized source content is chunked
and indexed, the sub-question retrieves its most relevant chunks, and only
chunks that pass provenance validation are supplied to evidence extraction. The
replay log adds explicit RAG indexing and retrieval steps.

The response contains the complete typed state plus an ordered `audit_trail`.
Each audit step exposes status, timestamps, provider/model metadata, concise
action summaries, evidence references, counts, warnings, and typed errors. It
does not expose private model reasoning. Successful work is retained when a
later question, source extraction, critic search, or provider call fails, so the
result can be `partial` without fabricated replacement sources. Synthesis
confidence describes the completeness and consistency of the evidence picture;
it is not a probability that the investigated claim is true, and no binary
truth verdict is returned.

### Evidence summary request

Send a complete `ResearchResult` to `POST /api/v1/evidence/summary`. The response
contains supporting, contradicting, neutral, and insufficient counts; the
strongest supporting and contradicting items; and unresolved conflicts. It
intentionally contains no final truth verdict.

### Document upload request

Send multipart form data with one or more files under the `files` key to
`POST /api/v1/documents/upload`:

```text
files: report.pdf     (application/pdf)
files: notes.txt      (text/plain)
```

Accepted extensions are `.pdf`, `.docx`, `.txt`, `.md`, `.png`, `.jpg`, and
`.jpeg`. The response reports each ingested document, its page and character
counts, and whether the content was a duplicate. Re-uploading identical bytes
returns the existing document with `duplicate: true`.

### Document-grounded investigation request

```json
{
  "query": "What compliance problems did the bidders face?",
  "depth": "standard",
  "document_ids": ["doc-5287eebdb3b04812a2cb85ea4e8a3017"],
  "use_rag": true,
  "use_graph": true
}
```

Send this body to `POST /api/v1/documents/investigations`. The service plans the
investigation, recalls the most relevant document pages (`use_rag`) and graph
neighbors (`use_graph`), and asks the configured report generator for findings
that quote the excerpts. The response is `no_documents` when no matching
documents are stored. With `LLM_PROVIDER=mock` the deterministic generator
extracts excerpt summaries; with `LLM_PROVIDER=gemini` a live model synthesizes
the report. `fallback_used` distinguishes mock output from a configured model.

## Tests and verification

Install runtime dependencies only:

```powershell
python -m pip install -r requirements.txt
```

For development and tests, use the separate dependency file:

```powershell
python -m pip install -r requirements-dev.txt
```

Run the test suite:

```powershell
python -m pytest
```

The service tests live under `tests/` and the browser-UI tests under
`app/tests/` (both force the in-memory provider and mock providers so the
suite runs fully offline).

Source compilation can be checked with:

```powershell
python -m compileall app
```

Dependency consistency can be checked with `python -m pip check`. The
persistence suite covers the in-memory provider end to end (users,
documents, and agentic investigation persistence) and exercises the
SQLAlchemy repositories against an in-memory SQLite database. To verify the
relational schema matches the models:

```powershell
$env:DATABASE_URL="sqlite:///./ai_investigation.db"
alembic upgrade head
alembic check
```

## API-key security

- Never commit a real `.env` file or credentials.
- `.env.example` contains empty placeholders only.
- Supply `GEMINI_API_KEY` through the environment or a secret manager.
- Do not log API keys, authorization headers, or raw provider credentials.
- Provider authentication remains isolated inside its adapter module.

## Current limitations

- Gemini planning, grounded web research, and evidence extraction are opt-in
  and may incur usage charges or quota consumption.
- The deterministic mock remains the default for offline development and tests.
- The mock endpoint still uses deterministic records on reserved domains.
- The web endpoint depends on Gemini returning usable citation annotations.
- Grounding metadata generally does not provide author or publication-date
  metadata, which lowers heuristic source-quality scores.
- Evidence extraction can use only supplied source titles/snippets; it does not
  fetch full page content. A classification is limited by that supplied text.
- Category detection uses local pattern matching rather than a trained model.
- Planning prompts are sent externally only when `LLM_PROVIDER=gemini`;
  evidence prompts are sent externally only when `EVIDENCE_PROVIDER=gemini`.
- RAG can index only the normalized content supplied to it. The current research
  providers usually supply titles/snippets rather than complete documents.
- `InMemoryVectorStore` is process-local, is cleared on restart, is not shared
  across workers, and is unsuitable as durable production storage. A future
  phase can add a persistent vector database behind the existing interface.
- No Pinecone, Chroma, Qdrant, FAISS, Neo4j, or GraphRAG integration is included.
- No autonomous crawling or page-content fetching.
- Persistence defaults to the process-local `in_memory` provider, which is
  cleared on restart and not shared across workers. The opt-in SQLAlchemy
  provider supports PostgreSQL and SQLite; a real deployment should provision
  a database, run `alembic upgrade head`, and set `PERSISTENCE_PROVIDER=sqlalchemy`.
- The SQLAlchemy session layer is synchronous and runs on worker threads;
  it has not been benchmarked under high concurrency.
- `reset_persistence()` is a test/development helper and clears the in-memory
  provider only.
- No authentication, authorization, or user sessions are included; the users
  endpoint persists identity records only.
- `InMemoryDocumentStore` is process-local, is cleared on restart, and is not
  shared across workers. Uploaded documents now also persist through the
  repository layer, so the in-memory store can be repopulated from the
  persistence provider on restart.
- Vision-based reading (`VISION_PROVIDER=gemini`) sends image bytes to the
  configured Gemini model and may incur usage charges; it is never used by the
  automated test suite.
- Synthesis is bounded and evidence-grounded; it does not perform autonomous
  truth verification or return an absolute truth verdict.
- The browser UI is a local case workspace. Its worker runs a deterministic
  offline mock pipeline (no model calls), its SQLite store is single-process,
  and its upload handling indexes plain text — it does not perform the heavy
  document extraction or AI evidence classification available under `/api/v1`.

### Data persistence and backup (production deployment)

Be explicit about what survives restarts before running a production deployment:

- **SQL data survives** when PostgreSQL is used: users, investigations, audit
  steps, sources, evidence items, conflicts, reports, and uploaded document
  metadata/content persist in the relational database via
  `PERSISTENCE_PROVIDER=sqlalchemy`. Back up the PostgreSQL volume or database
  with your provider's standard tooling.
- **RAG/vector data does not survive restarts yet.** The current
  `InMemoryVectorStore` holds embeddings only in process memory; it is cleared
  on restart and is not shared across workers. Persistent vector storage is a
  future enhancement behind the existing `VectorStore` interface.
- **Graph data does not survive restarts yet.** The current `InMemoryGraphStore`
  is also process-local. Persistent graph storage is a future enhancement
  behind the existing `GraphStore` interface.
- **Document uploads survive** through the SQLAlchemy repository layer, which
  doubles as the read source when the in-memory document store is empty.
- Run the app with a single uvicorn worker so the process-local vector and graph
  stores stay consistent. Multi-worker scaling requires persistent stores.

### Known production caveats

- The Content-Security-Policy includes `'unsafe-inline'` for `script-src` and
  `style-src` to keep the CDN-based templates working; tightening it needs
  nonces/hashes for inline scripts and is out of scope for this phase.
- Rate limiting is documented but not implemented (see Production and
  deployment); provider quota/retry behavior is unchanged.
- No authentication or authorization layer exists; put the service behind an
  authenticating reverse proxy for any public-facing deployment.
- The agentic and research endpoints (`POST /api/v1/investigations/agentic`,
  `/api/v1/investigations/research`, `POST /api/v1/research/web`) always use
  Gemini grounded search and require `GEMINI_API_KEY`; the `SEARCH_PROVIDER`
  environment variable does not change these endpoints. Other research entry
  points (mock and deterministic web) remain available for offline work.

## Planned roadmap

1. Expand offline evaluation fixtures for planner and evidence quality.
2. Add evaluation and observability for opt-in LLM adapters.
3. Add grounded-search evaluation fixtures and provider observability.
4. Add resilient provider telemetry without logging sensitive content.
5. Add full-page content acquisition with explicit policy controls.
6. Add asynchronous investigation jobs and background execution.
7. Add citation validation and evidence-grounded report synthesis.
8. Add an optional persistent vector-store adapter and reindexing lifecycle.
