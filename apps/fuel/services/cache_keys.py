from __future__ import annotations

import hashlib
import json
from typing import Any


def build_trip_cache_key(payload: dict[str, Any]) -> str:
    """Return a stable Redis cache key for repeated trip searches."""
    normalized = {
        key: (value.strip().lower() if isinstance(value, str) else value)
        for key, value in sorted(payload.items())
    }
    raw = json.dumps(normalized, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"trip-plan:v1:{digest}"
