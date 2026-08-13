# EvidenceAI - release checklist

Use this before publishing a release or tagging a version.

## Quality gates

- [ ] `python -m compileall app` passes
- [ ] `python -m pytest -q` is green (whole suite runs offline)
- [ ] `python -m pip check` reports no dependency conflicts
- [ ] `git diff --check` reports no whitespace errors
- [ ] GitHub Actions CI is green (tests + Docker build workflow)

## Hygiene

- [ ] No secrets committed: `git ls-files` contains no `.env`, `.pem`, or key files
- [ ] `.env` is in `.gitignore` and `.env.example` holds empty placeholders only
- [ ] Local databases (`*.db`, `*.sqlite*`) are ignored and not committed
- [ ] No accidental temporary files, screenshots junk, or logs in the tree
- [ ] `git status` reviewed; only intended files staged

## Packaging and docs

- [ ] README badges match reality (no fabricated badges)
- [ ] README links resolve (architecture, API examples, demo mode, screenshots)
- [ ] `docs/screenshots/` contains the referenced PNGs:
      `dashboard.png`, `new-investigation.png`, `investigation-result.png`,
      `documents.png`, `rag-search.png`, `graph.png`
- [ ] Screenshots show only demo/mock data or fictional examples

## Build and migrations

- [ ] `docker build -t evidenceai .` succeeds
- [ ] `docker compose config` is valid
- [ ] `docker compose up --build` starts PostgreSQL, runs `alembic upgrade head`,
      and the app becomes ready
- [ ] `alembic upgrade head` + `alembic check` pass against a scratch database

## Demo mode

- [ ] `$env:APP_ENV_FILE = "examples/demo.env"` starts the app with no API key
- [ ] Health, dashboard, investigation planning, documents, RAG, and graph
      respond offline (see `docs/demo-mode.md` for the verified list)
- [ ] Results are labeled as mock data; no fabricated real-world citations

## Versioning (optional)

- [ ] `APP_VERSION` in `app/core/config.py`, `.env.example`, and
      `examples/demo.env` are consistent
- [ ] Version bump matches the change size (docs-only: no bump needed)
- [ ] Tag/release created only after the above passes

## Post-release

- [ ] Confirm no secrets were added in the released commit
- [ ] Confirm CI passed on the tagged commit
