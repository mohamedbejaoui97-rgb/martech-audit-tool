"""Shared API key loader — single source of truth for all phases."""
import os

# Project root: cli/deep/../../ = martech-audit-tool/
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_ENV_PATH = os.path.join(_PROJECT_ROOT, "credentials", ".env")


def get_api_key():
    """Return Anthropic API key from env vars or credentials/.env file.

    Priority: ANTHROPIC_API_KEY env > CLAUDE_API_KEY env > .env file.
    Returns empty string if not found.
    """
    key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY", "")
    if key:
        return key
    if os.path.exists(_ENV_PATH):
        with open(_ENV_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k in ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY") and v:
                        return v
    return ""


def get_google_key():
    """Return Google API key from env vars or credentials/.env file."""
    key = os.environ.get("GOOGLE_API_KEY", "")
    if key:
        return key
    if os.path.exists(_ENV_PATH):
        with open(_ENV_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() == "GOOGLE_API_KEY" and v.strip():
                        return v.strip()
    return ""
