# AI Investigation Engine

AI Investigation Engine is a deterministic FastAPI service that converts an
investigation query into a structured research plan. The current implementation
is intentionally local and provider-independent so an LLM can be introduced
later without coupling the API or domain models to a specific vendor.

## Current features

- Strict Pydantic request and response schemas.
- Investigation depths: `quick`, `standard`, and `deep`.
- Deterministic classification into six investigation categories.
- Category-aware research angles.
- Structured, prioritized sub-questions.
- Versioned planning API under `/api/v1`.
- Consistent validation and application error responses.
- Environment-backed application settings without `pydantic-settings`.
- Pytest-compatible planner and ASGI endpoint tests.

No external AI provider, retrieval system, search engine, database, agent, or
persistence layer is connected.

## Project structure

```text
AI-Investigation-Engine/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py
│   │   └── v1/
│   │       ├── __init__.py
│   │       └── routes.py
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py
│   │   └── exceptions.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── common.py
│   │   └── investigation.py
│   └── services/
│       ├── __init__.py
│       └── investigation_service.py
├── tests/
│   ├── __init__.py
│   ├── test_api.py
│   └── test_investigation_planner.py
├── .gitignore
├── README.md
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
| `APP_VERSION` | `0.2.0` |
| `ENVIRONMENT` | `development` |
| `DEBUG` | `false` |

## API endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Basic service information |
| `GET` | `/health` | Health and environment status |
| `POST` | `/api/v1/investigations/plan` | Generate an investigation plan |

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

## Tests and verification

The tests are compatible with pytest:

```powershell
python -m pytest
```

`pytest` and HTTP test-client packages are not runtime dependencies and may not
be installed in every local environment. Source compilation can always be
checked with:

```powershell
python -m compileall app
```

## Current limitations

- Plans are generated from deterministic templates, not an LLM.
- Category detection uses local pattern matching rather than a trained model.
- No web search, source retrieval, RAG, embeddings, or vector database.
- No persistence, authentication, background jobs, or audit history.
- No evidence collection, verification, scoring, or report synthesis.

## Planned roadmap

1. Introduce a provider-neutral LLM planner interface and local/mock provider.
2. Add evaluation fixtures for planner quality and category detection.
3. Add source retrieval and evidence provenance behind explicit interfaces.
4. Add persistence and asynchronous investigation jobs.
5. Add evidence scoring, citation validation, and report synthesis.
