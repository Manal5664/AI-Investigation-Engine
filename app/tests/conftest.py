import os


# Keep the UI tests offline: mirror the settings applied by the top-level
# tests/conftest.py so `pytest app/tests` is deterministic even when a real
# .env file or provider API keys are present on the machine.
os.environ["APP_ENV_FILE"] = ""
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LLM_MODEL"] = "mock-investigator"
os.environ["EVIDENCE_PROVIDER"] = "mock"
os.environ["EVIDENCE_MODEL"] = "mock-evidence-extractor"
os.environ["EMBEDDING_PROVIDER"] = "mock"
os.environ["EMBEDDING_MODEL"] = "mock-embedding-v1"
os.environ["VECTOR_STORE_PROVIDER"] = "in_memory"
os.environ["PERSISTENCE_PROVIDER"] = "in_memory"
os.environ["GRAPH_STORE_PROVIDER"] = "in_memory"
os.environ["DOCUMENT_STORE_PROVIDER"] = "in_memory"
os.environ.pop("GEMINI_API_KEY", None)
