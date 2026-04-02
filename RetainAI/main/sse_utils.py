"""SSE framing helper for StreamingHttpResponse — JSON must be valid for browser JSON.parse."""

from __future__ import annotations

import json
import math
from typing import Any, Dict


def sanitize_for_json(obj: Any) -> Any:
    """
    Ensure values are JSON-serializable in a way JavaScript accepts.
    Python's json.dumps emits `NaN` / `Infinity` by default — those are NOT valid JSON and break EventSource clients.
    """
    if obj is None:
        return None
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, (int, str)):
        return obj
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(x) for x in obj]
    if hasattr(obj, "item"):
        try:
            return sanitize_for_json(obj.item())
        except Exception:
            return str(obj)
    if hasattr(obj, "isoformat"):
        try:
            return obj.isoformat()
        except Exception:
            return str(obj)
    return str(obj)


def format_sse(data: Dict[str, Any]) -> str:
    safe = sanitize_for_json(data)
    # separators compact; ensure_ascii=False keeps readable UTF-8 in JSON string escapes
    payload = json.dumps(safe, ensure_ascii=False, separators=(",", ":"))
    return f"data: {payload}\n\n"
