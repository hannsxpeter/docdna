import os

DATABASE_URL = os.environ["DATABASE_URL"]
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
REQUEST_TIMEOUT_SECONDS = int(os.environ.get("REQUEST_TIMEOUT_SECONDS", "30"))
FEATURE_PARTIAL_REFUNDS = os.environ.get("FEATURE_PARTIAL_REFUNDS", "0") == "1"
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "").split(",")
