# AI Investigation Engine

AI Investigation Engine is a FastAPI service that converts an investigation
query into a structured research plan. It supports both a deterministic planner
and a provider-independent, AI-style planning flow. The current AI provider is
a local deterministic mock, so development requires no API key, internet
connection, or paid model.

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
- Reusable prompt builders for future provider adapters.
- Deterministic fallback for provider failures or invalid model output.
- Provider-independent asynchronous search abstraction.
- Deterministic mock search data on reserved example domains.
- Explainable source-quality scoring with explicit caveats.
- Provenance-preserving evidence extraction and stance classification.
- Structured evidence summaries without final truth verdicts.
- Pytest and HTTP-level ASGI endpoint tests.

No external AI provider, retrieval system, search engine, database, agent, or
persistence layer is connected.

## Architecture

```mermaid
flowchart LR
    Client[API client] --> Routes[FastAPI v1 routes]

    Routes -->|/plan| Deterministic[InvestigationPlanner]
    Routes -->|/ai-plan| AIService[AIInvestigationService]

    AIService --> Factory[LLM provider factory]
    Factory --> Mock[MockLLMProvider]
    Mock --> Prompts[Reusable prompt builders]
    Mock --> Deterministic

    Mock --> Raw[JSON-compatible provider output]
    Raw --> Validation[Pydantic AIInvestigationPlan validation]
    Validation --> Response[Typed InvestigationResponse]

    AIService -. provider failure, timeout, or invalid schema .-> Deterministic
```

### Deterministic and AI-provider flows

| Flow | Endpoint | Implementation | Intended use |
| --- | --- | --- | --- |
| Deterministic | `POST /api/v1/investigations/plan` | Local `InvestigationPlanner` | Stable baseline and fallback |
| AI-style | `POST /api/v1/investigations/ai-plan` | Configured `LLMProvider` through `AIInvestigationService` | Provider-independent integration boundary |

Both flows return the same response envelope. The AI-style flow adds a research
objective, explicit assumptions, expected evidence types, and potential biases.
All provider output is validated before it reaches the API response.

### Current mock provider

`MockLLMProvider` implements the same asynchronous contract intended for future
real providers. It builds the future planning prompt, generates realistic
structured data locally, and returns JSON-compatible output. Its behavior is
deterministic and uses no network calls, API keys, model SDKs, or usage charges.

### Future provider adapters

Future OpenAI, Gemini, or Anthropic adapters should implement only
`LLMProvider` and translate provider-specific responses into the neutral
structured output contract. Vendor SDK objects, authentication, and error types
must remain inside their adapter modules. No real adapter is currently present.

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

### Provenance

Every evidence item retains the supplied source ID and URL, the exact relevant
passage, retrieval timestamp, extraction method, optional location, and a
SHA-256 content hash. The extractor validates every evidence source ID/URL pair
against the supplied normalized source list. It cannot silently create or cite
a source outside that list.

### Source-quality scoring is not truth

The current credibility service uses explainable metadata heuristics: source
type, author availability, publication date, HTTPS, publisher/domain
information, and reference or citation metadata. Its `high`, `moderate`, `low`,
and `unknown` levels estimate source quality only. They do not prove that a
statement is accurate, complete, unbiased, or true.

### Future research adapters

Real search providers can later implement `SearchProvider` without changing the
research service. A future LLM evidence extractor can implement
`EvidenceExtractor`, but it must preserve the same source-bound provenance
contract and validate structured output. No search SDK, scraper, or external
evidence model is currently connected.

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
│   │       ├── research_routes.py
│   │       └── routes.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── exceptions.py
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
│   │   ├── evidence.py
│   │   ├── investigation.py
│   │   ├── research.py
│   │   └── source.py
│   └── services/
│       ├── __init__.py
│       ├── ai_investigation_service.py
│       ├── evidence_summary_service.py
│       ├── investigation_service.py
│       ├── research_service.py
│       └── source_credibility_service.py
├── tests/
│   ├── __init__.py
│   ├── test_ai_provider.py
│   ├── test_ai_service.py
│   ├── test_api.py
│   ├── test_evidence_pipeline.py
│   ├── test_investigation_planner.py
│   ├── test_research_api.py
│   ├── test_search_provider.py
│   └── test_source_credibility.py
├── .env.example
├── .gitignore
├── README.md
├── requirements-dev.txt
└── requirements.txt
```

## Run locally

Activate the existing virtual environment, then start the API from the project
root:

```powershell
python -m uvicorn app.main:app --reload
```

Interactive OpenAPI documentation is available at:

- `http://127.0.0.1:8000/docs`
- `http://127.0.0.1:8000/redoc`

The application reads these optional environment variables:

| Variable | Default |
| --- | --- |
| `APP_NAME` | `AI Investigation Engine` |
| `APP_VERSION` | `0.4.0` |
| `ENVIRONMENT` | `development` |
| `DEBUG` | `false` |
| `LLM_PROVIDER` | `mock` |
| `LLM_MODEL` | `mock-investigator` |
| `LLM_TIMEOUT_SECONDS` | `60` |

## API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Basic service information |
| `GET` | `/health` | Health and environment status |
| `POST` | `/api/v1/investigations/plan` | Generate a deterministic investigation plan |
| `POST` | `/api/v1/investigations/ai-plan` | Generate a provider-backed AI-style plan |
| `POST` | `/api/v1/research/mock` | Run the offline mock research/evidence pipeline |
| `POST` | `/api/v1/evidence/summary` | Summarize evidence counts and unresolved conflicts |

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
same `status` and `plan` envelope and includes:

- `research_objective` with explicit success criteria.
- `assumptions` that require validation.
- Structured `research_angles` and prioritized `sub_questions`.
- `expected_evidence_types`.
- `potential_biases` with mitigations.

For the default `mock` provider, repeated requests with the same query and depth
produce the same response.

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

### Evidence summary request

Send a complete `ResearchResult` to `POST /api/v1/evidence/summary`. The response
contains supporting, contradicting, neutral, and insufficient counts; the
strongest supporting and contradicting items; and unresolved conflicts. It
intentionally contains no final truth verdict.

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

Source compilation can be checked with:

```powershell
python -m compileall app
```

## API-key security

- Never commit a real `.env` file or credentials.
- `.env.example` contains empty placeholders only.
- Supply future API keys through environment variables or a secret manager.
- Do not log API keys, authorization headers, or raw provider credentials.
- Keep provider authentication isolated inside future adapter modules.

## Current limitations

- The configured AI provider is currently a deterministic mock, not a real LLM.
- Search results use deterministic mock records on reserved example domains.
- Evidence extraction uses supplied mock snippets, not fetched page content.
- Category detection uses local pattern matching rather than a trained model.
- Prompt templates are prepared but are not sent to any external service.
- No web search, source retrieval, RAG, embeddings, or vector database.
- No persistence, authentication, background jobs, or audit history.
- No evidence collection, verification, scoring, or report synthesis.

## Planned roadmap

1. Expand offline evaluation fixtures for planner and evidence quality.
2. Add opt-in real LLM adapters behind `LLMProvider`.
3. Add opt-in real search adapters behind `SearchProvider`.
4. Add a structured real-model extractor behind `EvidenceExtractor`.
5. Add resilient provider telemetry without logging sensitive content.
6. Add persistence and asynchronous investigation jobs.
7. Add citation validation and evidence-grounded report synthesis.
