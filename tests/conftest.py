import os


# Keep all automated tests offline even when a developer has configured a
# project-local .env file for real Gemini integration.
os.environ["APP_ENV_FILE"] = ""
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LLM_MODEL"] = "mock-investigator"
os.environ["EVIDENCE_PROVIDER"] = "mock"
os.environ["EVIDENCE_MODEL"] = "mock-evidence-extractor"
os.environ["EMBEDDING_PROVIDER"] = "mock"
os.environ["EMBEDDING_MODEL"] = "mock-embedding-v1"
os.environ["VECTOR_STORE_PROVIDER"] = "in_memory"
os.environ.pop("GEMINI_API_KEY", None)
