import os


# Keep all automated tests offline even when a developer has configured a
# project-local .env file for real Gemini integration.
os.environ["APP_ENV_FILE"] = ""
os.environ["LLM_PROVIDER"] = "mock"
os.environ["LLM_MODEL"] = "mock-investigator"
os.environ.pop("GEMINI_API_KEY", None)
