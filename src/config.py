import os
from dotenv import load_dotenv

# Load .env.local (repo root). Safe if file doesn't exist.
load_dotenv(".env.local")

def env(key: str, default: str | None = None) -> str:
    val = os.getenv(key, default)
    if val is None or val == "":
        raise RuntimeError(f"Missing required env var: {key}")
    return val

def env_int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))

def env_float(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))

# Google Cloud
PROJECT_ID = env("PROJECT_ID")

# Document AI
LOCATION = env("LOCATION")
PROCESSOR_ID = env("PROCESSOR_ID")
MAX_PAGES_SYNC = env_int("MAX_PAGES_SYNC", 15)

# Vertex / Gemini
VERTEX_LOCATION = env("VERTEX_LOCATION")
GEMINI_MODEL = env("GEMINI_MODEL")
GEMINI_TEMPERATURE = env_float("GEMINI_TEMPERATURE", 0.0)
GEMINI_MAX_OUTPUT_TOKENS = env_int("GEMINI_MAX_OUTPUT_TOKENS", 2048)
GEMINI_RESPONSE_MIME_TYPE = os.getenv("GEMINI_RESPONSE_MIME_TYPE", "application/json")

# Local folders
RAW_DIR = env("RAW_DIR")
EXTRACTED_DIR = env("EXTRACTED_DIR")
ENRICHED_DIR = env("ENRICHED_DIR")
RAWDOC_DIR = env("RAWDOC_DIR")

# Batch delays
BATCH_MIN_DELAY = env_float("BATCH_MIN_DELAY", 1.0)
BATCH_MAX_DELAY = env_float("BATCH_MAX_DELAY", 2.0)
