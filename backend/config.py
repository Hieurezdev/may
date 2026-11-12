"""Read server configuration without exposing credentials to client code."""

import os
from pathlib import Path


def setting(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    if value:
        return value
    env = Path(__file__).resolve().parent.parent / ".env.local"
    if env.exists():
        for line in env.read_text().splitlines():
            key, separator, value = line.partition("=")
            if separator and key.strip() == name:
                return value.strip().strip("\"'") or None
    return None
