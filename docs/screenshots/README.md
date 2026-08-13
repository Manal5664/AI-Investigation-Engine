# Screenshots

This directory is intentionally empty. Screenshots are added by hand after
capturing the running app in offline demo mode; they are not fabricated.

Place PNG files here with these exact names. The README references them.

| File | What to capture |
| --- | --- |
| `dashboard.png` | `http://127.0.0.1:8000/dashboard` - dashboard with case counts and recent investigations |
| `new-investigation.png` | `http://127.0.0.1:8000/investigate` - new-case form |
| `investigation-result.png` | `http://127.0.0.1:8000/investigation/{id}` - case detail (status, evidence, report, log) |
| `documents.png` | `http://127.0.0.1:8000/documents` - document upload/search page |
| `rag-search.png` | `http://127.0.0.1:8000/rag` - evidence/retrieval search page |
| `graph.png` | `http://127.0.0.1:8000/graph` - relationship-graph page |

## How to capture

1. Start the app in demo mode:

   ```powershell
   $env:APP_ENV_FILE = "examples/demo.env"
   python -m uvicorn app.main:app
   ```

2. Run a mock investigation so the dashboard and history have data:

   ```powershell
   curl -X POST http://127.0.0.1:8000/api/v1/research/mock `
     -H "Content-Type: application/json" `
     -d '{"investigation_query": "Research renewable energy storage", "depth": "deep"}'
   ```

   Upload `examples/sample-document.txt` on the documents page, then map it into
   the graph and index it so `rag-search.png` and `graph.png` have content.

3. Capture each page (browser DevTools or your favorite tool). Prefer a
   viewport around 1440x900, default zoom.

4. Save PNGs into this folder with the exact filenames above. Keep file sizes
   reasonable (under ~500 KB each if possible).

## Rules

- Only capture the app running with mock providers (see `docs/demo-mode.md`).
- Do not paste fabricated citations or real-world claims into screenshots.
- Do not capture real API keys or personal data.
