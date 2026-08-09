# AI Investigation Engine

AI Investigation Engine is a FastAPI service that converts an investigation
query into a structured research plan. It supports both a deterministic planner
and a provider-independent AI planning flow. The offline `mock` provider remains
the default; an opt-in Google Gemini adapter can make real model calls when
explicitly configured with an API key and model name. A separate opt-in Gemini
Google Search grounding path returns normalized, citation-backed web sources.

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
- Structured evidence summaries without final truth verdicts.
- Pytest and HTTP-level ASGI endpoint tests.

Gemini planning and Gemini Google Search grounding are the only optional
external integrations. No third-party search SDK, autonomous crawler, retrieval
system, database, agent, or persistence layer is connected.

## Architecture

```mermaid
flowchart LR
    Client[API client] --> Routes[FastAPI v1 routes]

    Routes -->|/plan| Deterministic[InvestigationPlanner]
    Routes -->|/ai-plan| AIService[AIInvestigationService]
    Routes -->|/research/web| WebService[WebResearchService]

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
```

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

### Grounded web research

`GeminiGroundedSearchProvider` implements the vendor-neutral `SearchProvider`
contract with Gemini's built-in Google Search tool. The adapter accepts URLs
only from `url_citation` annotations returned by grounding metadata. URLs in
model prose are ignored. Valid URLs are normalized, stripped of common tracking
parameters and fragments, deduplicated, capped by `max_results`, and converted
to typed `Source` records.

The web path stops after source normalization and credibility assessment. It
does not run the mock evidence extractor or make a truth determination. A future
real evidence extractor must preserve the same source-bound provenance contract.

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

Gemini-specific additions include `app/ai/gemini_provider.py`,
`app/research/search/gemini_grounded_provider.py`,
`app/services/web_research_service.py`, and the guarded scripts under
`scripts/`.

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
| `APP_VERSION` | `0.6.0` |
| `ENVIRONMENT` | `development` |
| `DEBUG` | `false` |
| `LLM_PROVIDER` | `mock` |
| `LLM_MODEL` | `mock-investigator` |
| `LLM_TIMEOUT_SECONDS` | `60` |
| `GEMINI_API_KEY` | unset |
| `SEARCH_PROVIDER` | `mock` |
| `SEARCH_MODEL` | `gemini-3.6-flash` |
| `SEARCH_MAX_RESULTS` | `5` |

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

## API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Basic service information |
| `GET` | `/health` | Health and environment status |
| `POST` | `/api/v1/investigations/plan` | Generate a deterministic investigation plan |
| `POST` | `/api/v1/investigations/ai-plan` | Generate a provider-backed AI-style plan |
| `POST` | `/api/v1/research/mock` | Run the offline mock research/evidence pipeline |
| `POST` | `/api/v1/research/web` | Run real Gemini Google Search grounding and normalize cited sources |
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
- Supply `GEMINI_API_KEY` through the environment or a secret manager.
- Do not log API keys, authorization headers, or raw provider credentials.
- Provider authentication remains isolated inside its adapter module.

## Current limitations

- Gemini planning and grounded web research are opt-in and may incur usage
  charges or quota consumption.
- The deterministic mock remains the default for offline development and tests.
- The mock endpoint still uses deterministic records on reserved domains.
- The web endpoint depends on Gemini returning usable citation annotations.
- Grounding metadata generally does not provide author or publication-date
  metadata, which lowers heuristic source-quality scores.
- Evidence extraction uses supplied mock snippets, not fetched page content.
- Category detection uses local pattern matching rather than a trained model.
- Prompt templates are sent externally only when `LLM_PROVIDER=gemini`.
- No autonomous crawling, page-content fetching, RAG, embeddings, or vector
  database.
- No persistence, authentication, background jobs, or audit history.
- No live external evidence collection, truth verification, or report synthesis.

## Planned roadmap

1. Expand offline evaluation fixtures for planner and evidence quality.
2. Add evaluation and observability for opt-in LLM adapters.
3. Add grounded-search evaluation fixtures and provider observability.
4. Add a structured real-model extractor behind `EvidenceExtractor`.
5. Add resilient provider telemetry without logging sensitive content.
6. Add persistence and asynchronous investigation jobs.
7. Add citation validation and evidence-grounded report synthesis.
